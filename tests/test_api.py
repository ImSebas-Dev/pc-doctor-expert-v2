"""Pruebas de la API contra una base PostgreSQL real (DATABASE_URL, ADMIN_CORREO y ADMIN_CLAVE ya instalados)."""
import os
import time
import unittest
import uuid

from app import crear_app
from sistema import seguridad

ADMIN = (os.environ["ADMIN_CORREO"], os.environ["ADMIN_CLAVE"])
CLAVE = "Clave-Segura-2026"
U01 = {"sintoma_principal": "apagado_reinicio", "temperatura_elevada": "verdadero", "ventilador_anormal": "falso",
       "calor_cpu": "verdadero", "calor_gpu": "falso", "calor_flujo": "falso"}
RAM = {"capacidad_gb": 8, "tipo": "DDR4", "frecuencia_mhz": 3200, "marca": "Kingston"}
DISCO = {"tipo": "SSD NVMe", "capacidad_gb": 512, "modelo": "Samsung 970", "es_sistema": True}
EQUIPO = {"nombre": "Portátil", "sistema_operativo": "Windows 11", "procesador": "Intel Core i7", "cpu_nucleos": 8, "gpu": "NVIDIA GTX 1660", "gpu_dedicada": True,
          "ram": [RAM, RAM], "discos": [DISCO]}


def equipo(nombre="Equipo", **cambios):
    return {**EQUIPO, "nombre": nombre, **cambios}


class Cliente:
    def __init__(self, app):
        self.c, self.csrf = app.test_client(), None
        self.csrf = self.c.get("/api/sesion").get_json()["csrf"]

    def pedir(self, metodo, ruta, datos=None, csrf=True):
        cab = {"X-CSRF-Token": self.csrf} if csrf else {}
        r = getattr(self.c, metodo)(ruta, json=datos, headers=cab) if datos is not None or metodo != "get" else self.c.get(ruta)
        if r.is_json and isinstance(r.get_json(), dict) and "csrf" in r.get_json():
            self.csrf = r.get_json()["csrf"]
        return r


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = crear_app({"TESTING": True})

    def setUp(self):
        for lim in (seguridad.fallos_por_ip, seguridad.fallos_por_correo, seguridad.registros_por_ip):
            lim._h.clear()

    def usuario_nuevo(self):
        cl = Cliente(self.app)
        r = cl.pedir("post", "/api/registro", {"nombre": "Ana Prueba", "correo": f"{uuid.uuid4().hex[:10]}@prueba.test", "clave": CLAVE})
        self.assertEqual(r.status_code, 201, r.get_json())
        return cl

    def admin(self):
        cl = Cliente(self.app)
        r = cl.pedir("post", "/api/login", {"correo": ADMIN[0], "clave": ADMIN[1]})
        self.assertEqual(r.status_code, 200, r.get_json())
        return cl


class Seguridad(Base):
    def test_cabeceras(self):
        r = self.app.test_client().get("/")
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.app.test_client().get("/api/sesion").headers["Cache-Control"], "no-store")

    def test_sin_sesion_401_y_csrf_403(self):
        cl = Cliente(self.app)
        self.assertEqual(cl.pedir("get", "/api/equipos").status_code, 401)
        self.assertEqual(cl.pedir("post", "/api/login", {"correo": "a@b.co", "clave": "x"}, csrf=False).status_code, 403)
        self.assertEqual(cl.c.post("/api/login", data="x", headers={"X-CSRF-Token": cl.csrf}).status_code, 415)

    def test_login_generico_y_limite(self):
        cl = Cliente(self.app)
        a = cl.pedir("post", "/api/login", {"correo": ADMIN[0], "clave": "mala-clave-1"})
        b = cl.pedir("post", "/api/login", {"correo": "noexiste@prueba.test", "clave": "mala-clave-1"})
        self.assertEqual((a.status_code, b.status_code), (401, 401))
        self.assertEqual(a.get_json(), b.get_json())
        for _ in range(4):
            cl.pedir("post", "/api/login", {"correo": ADMIN[0], "clave": "mala-clave-1"})
        self.assertEqual(cl.pedir("post", "/api/login", {"correo": ADMIN[0], "clave": ADMIN[1]}).status_code, 429)

    def test_inyeccion_sql_no_rompe(self):
        r = Cliente(self.app).pedir("post", "/api/login", {"correo": "' OR 1=1 --", "clave": "x' OR '1'='1"})
        self.assertEqual(r.status_code, 401)

    def test_politica_de_clave_y_duplicados(self):
        cl = Cliente(self.app)
        base = {"nombre": "Ana", "correo": f"{uuid.uuid4().hex[:8]}@prueba.test"}
        self.assertEqual(cl.pedir("post", "/api/registro", {**base, "clave": "corta"}).status_code, 422)
        self.assertEqual(cl.pedir("post", "/api/registro", {**base, "clave": "1234567890"}).status_code, 422)
        self.assertEqual(cl.pedir("post", "/api/registro", {**base, "clave": CLAVE}).status_code, 201)
        self.assertEqual(Cliente(self.app).pedir("post", "/api/registro", {**base, "clave": CLAVE}).status_code, 422)

    def test_sesion_expira_por_inactividad(self):
        cl = self.usuario_nuevo()
        self.assertEqual(cl.pedir("get", "/api/equipos").status_code, 200)
        with cl.c.session_transaction() as s:
            s["ult"] = int(time.time()) - seguridad.INACTIVIDAD - 5
        self.assertEqual(cl.pedir("get", "/api/equipos").status_code, 401)

    def test_cuerpo_demasiado_grande(self):
        cl = Cliente(self.app)
        self.assertEqual(cl.pedir("post", "/api/login", {"correo": "a" * 40000, "clave": "x"}).status_code, 413)


class ControlDeAcceso(Base):
    def test_un_usuario_no_ve_lo_de_otro(self):
        a, b = self.usuario_nuevo(), self.usuario_nuevo()
        eq = a.pedir("post", "/api/equipos", EQUIPO).get_json()["equipo"]
        self.assertEqual(b.pedir("get", "/api/equipos").get_json()["equipos"], [])
        self.assertEqual(b.pedir("put", f"/api/equipos/{eq['id']}", EQUIPO).status_code, 404)
        self.assertEqual(b.pedir("delete", f"/api/equipos/{eq['id']}", {}).status_code, 404)
        self.assertEqual(b.pedir("post", "/api/diagnosticos/paso", {"equipo_id": eq["id"], "respuestas": []}).status_code, 404)
        did = self.diagnosticar(a, eq["id"])
        self.assertEqual(b.pedir("get", f"/api/diagnosticos/{did}").status_code, 404)

    def test_rutas_admin_solo_para_admin(self):
        u = self.usuario_nuevo()
        for ruta in ("usuarios", "hipotesis", "reglas", "pruebas"):
            self.assertEqual(u.pedir("get", f"/api/admin/{ruta}").status_code, 403, ruta)
        self.assertEqual(u.pedir("post", "/api/admin/pruebas", {}).status_code, 403)

    def diagnosticar(self, cl, equipo_id):
        respuestas = []
        for _ in range(12):
            p = cl.pedir("post", "/api/diagnosticos/paso", {"equipo_id": equipo_id, "respuestas": respuestas}).get_json()
            if p["terminado"]:
                break
            h = p["pregunta"]["hecho"]
            respuestas.append({"hecho": h, "valor": U01.get(h)})
        self.assertTrue(p["terminado"])
        self.assertEqual(p["ranking"][0]["codigo"], "P01")
        r = cl.pedir("post", "/api/diagnosticos", {"equipo_id": equipo_id, "respuestas": respuestas})
        self.assertEqual(r.status_code, 201)
        return r.get_json()["id"]


class Funcionalidad(Base):
    def test_equipos_crud_y_validacion(self):
        u = self.usuario_nuevo()
        def intentar(**cambios):
            return u.pedir("post", "/api/equipos", {**EQUIPO, **cambios})
        self.assertEqual(intentar(ram=[]).status_code, 422)
        self.assertEqual(intentar(discos=[]).status_code, 422)
        self.assertEqual(intentar(cpu_nucleos=True).status_code, 422)
        self.assertEqual(intentar(ram=[{**RAM, "tipo": "DDR9"}]).status_code, 422)
        self.assertEqual(intentar(ram=[RAM] * 9).status_code, 422)
        mezcla = intentar(ram=[RAM, {**RAM, "tipo": "DDR5"}])
        self.assertEqual((mezcla.status_code, mezcla.get_json()["campo"]), (422, "ram.0.tipo"))
        self.assertIn("compatibles", mezcla.get_json()["error"])
        self.assertEqual(intentar(discos=[{**DISCO, "es_sistema": False}]).status_code, 422)
        self.assertEqual(intentar(discos=[DISCO, DISCO]).status_code, 422)
        eq = u.pedir("post", "/api/equipos", EQUIPO).get_json()["equipo"]
        self.assertEqual((eq["resumen"]["ram_total_gb"], eq["resumen"]["ram_modulos"], eq["resumen"]["avisos"]), (16, 2, []))
        self.assertEqual(u.pedir("post", "/api/equipos", EQUIPO).status_code, 422)
        nuevo = {**EQUIPO, "ram": [RAM, {"capacidad_gb": 16, "tipo": "DDR4", "frecuencia_mhz": 2666, "marca": "Crucial"}, {**RAM, "marca": ""}],
                 "discos": [DISCO, {"tipo": "HDD", "capacidad_gb": 2000, "es_sistema": False}]}
        r = u.pedir("put", f"/api/equipos/{eq['id']}", nuevo).get_json()["equipo"]
        self.assertEqual((r["resumen"]["ram_total_gb"], r["resumen"]["frecuencia_efectiva_mhz"], len(r["discos"])), (32, 2666, 2))
        self.assertTrue(any("2666" in a for a in r["resumen"]["avisos"]) and any("capacidades" in a for a in r["resumen"]["avisos"]))
        self.assertIn("2 TB", r["discos"][1]["etiqueta"])
        self.assertEqual(u.pedir("get", "/api/equipos").get_json()["equipos"][0]["ram"][1]["marca"], "Crucial")
        self.assertEqual(u.pedir("delete", f"/api/equipos/{eq['id']}", {}).status_code, 204)

    def diagnosticar_con(self, cl, equipo_id, dado, maximo=12):
        """Usuario simulado: responde lo indicado y «No» a lo demás. dado[hecho] = valor, o (valor, [posiciones de disco]) en preguntas por disco."""
        respuestas = []
        for _ in range(maximo):
            p = cl.pedir("post", "/api/diagnosticos/paso", {"equipo_id": equipo_id, "respuestas": respuestas}).get_json()
            if p["terminado"]:
                return p, respuestas
            q = p["pregunta"]
            v = dado.get(q["hecho"], "falso")
            if q["tipo"] == "varios":
                valor, pos = v if isinstance(v, tuple) else (v, [])
                r = {"hecho": q["hecho"], "valor": valor}
                if valor == "verdadero":
                    r["detalle"] = [q["opciones"][i]["valor"] for i in pos]
                respuestas.append(r)
            else:
                respuestas.append({"hecho": q["hecho"], "valor": v if v in [o["valor"] for o in q["opciones"]] else None})
        self.fail("el diagnóstico no terminó")

    def test_los_componentes_cambian_el_diagnostico(self):
        u = self.usuario_nuevo()
        poca = u.pedir("post", "/api/equipos", equipo("Poca RAM", ram=[{**RAM, "capacidad_gb": 2}, {**RAM, "capacidad_gb": 2}])).get_json()["equipo"]
        mucha = u.pedir("post", "/api/equipos", equipo("Mucha RAM", ram=[{**RAM, "capacidad_gb": 16}, {**RAM, "capacidad_gb": 16}])).get_json()["equipo"]
        caso = {"sintoma_principal": "lentitud", "ram_saturada": "verdadero"}
        self.assertEqual(self.diagnosticar_con(u, poca["id"], caso)[0]["ranking"][0]["codigo"], "P07")
        self.assertEqual(self.diagnosticar_con(u, mucha["id"], caso)[0]["ranking"][0]["codigo"], "P30")

    def test_disco_del_sistema_gpu_y_nucleos(self):
        u = self.usuario_nuevo()
        hdd = u.pedir("post", "/api/equipos", equipo("Con HDD", discos=[{**DISCO, "tipo": "HDD", "capacidad_gb": 1000}])).get_json()["equipo"]
        top = lambda e, caso: self.diagnosticar_con(u, e["id"], caso)[0]["ranking"][0]["codigo"]
        self.assertEqual(top(hdd, {"sintoma_principal": "lentitud", "lentitud_al_iniciar": "verdadero"}), "P27")
        integrada = u.pedir("post", "/api/equipos", equipo("Integrada", gpu="Intel UHD", gpu_dedicada=False)).get_json()["equipo"]
        self.assertEqual(top(integrada, {"sintoma_principal": "lentitud", "gpu_saturada": "verdadero"}), "P28")
        self.assertEqual(top(u.pedir("post", "/api/equipos", equipo("Dedicada")).get_json()["equipo"], {"sintoma_principal": "lentitud", "gpu_saturada": "verdadero"}), "P12")
        basico = u.pedir("post", "/api/equipos", equipo("Dos nucleos", cpu_nucleos=2)).get_json()["equipo"]
        self.assertEqual(top(basico, {"sintoma_principal": "lentitud", "cpu_saturada": "verdadero"}), "P29")

    def test_varios_discos_se_preguntan_por_disco(self):
        u = self.usuario_nuevo()
        uno = u.pedir("post", "/api/equipos", equipo("Un disco")).get_json()["equipo"]
        dos = u.pedir("post", "/api/equipos", equipo("Dos discos", discos=[DISCO, {"tipo": "HDD", "capacidad_gb": 1000, "modelo": "WD Blue", "es_sistema": False}])).get_json()["equipo"]
        caso = {"sintoma_principal": "lentitud", "disco_lleno": ("verdadero", [1])}
        # con un solo disco la pregunta es de sí o no; con varios, se elige en qué discos
        for eq, tipo in ((uno, "una"), (dos, "varios")):
            respuestas = [{"hecho": "sintoma_principal", "valor": "lentitud"}]
            for _ in range(10):
                p = u.pedir("post", "/api/diagnosticos/paso", {"equipo_id": eq["id"], "respuestas": respuestas}).get_json()
                if p["terminado"] or p["pregunta"]["hecho"] == "disco_lleno":
                    break
                respuestas.append({"hecho": p["pregunta"]["hecho"], "valor": "falso" if "falso" in [o["valor"] for o in p["pregunta"]["opciones"]] else None})
            self.assertEqual(p["pregunta"]["tipo"], tipo)
        self.assertEqual(len(p["pregunta"]["opciones"]), 2)
        ajeno = self.usuario_nuevo().pedir("post", "/api/equipos", equipo("Ajeno", discos=[DISCO, {"tipo": "HDD", "capacidad_gb": 500, "es_sistema": False}])).get_json()["equipo"]
        base = {"equipo_id": dos["id"]}
        mal = lambda r: u.pedir("post", "/api/diagnosticos/paso", {**base, "respuestas": respuestas + [r]}).status_code
        self.assertEqual(mal({"hecho": "disco_lleno", "valor": "verdadero"}), 422)                       # falta indicar el disco
        self.assertEqual(mal({"hecho": "disco_lleno", "valor": "verdadero", "detalle": [ajeno["discos"][1]["id"]]}), 422)   # disco de otra persona
        self.assertEqual(mal({"hecho": "disco_lleno", "valor": "falso", "detalle": [dos["discos"][0]["id"]]}), 422)
        p, resp = self.diagnosticar_con(u, dos["id"], caso)
        did = u.pedir("post", "/api/diagnosticos", {"equipo_id": dos["id"], "respuestas": resp}).get_json()["id"]
        d = u.pedir("get", f"/api/diagnosticos/{did}").get_json()
        self.assertEqual(d["hipotesis"][0]["codigo"], "P09")
        self.assertEqual(next(e for e in d["evidencias"] if "10 %" in e["texto"] and not e["derivada"] and not e["equipo"])["detalle"], "Disco 2")
        self.assertTrue(any(e["equipo"] for e in d["evidencias"]))
        respondidas = [e["texto"] for e in d["evidencias"] if not e["derivada"] and not e["equipo"]]      # lo que la persona contestó
        self.assertEqual(len(respondidas), sum(r["valor"] is not None for r in resp))   # «No sé» no queda como evidencia

    def test_diagnostico_completo_con_explicacion(self):
        u = self.usuario_nuevo()
        eq = u.pedir("post", "/api/equipos", EQUIPO).get_json()["equipo"]
        did = ControlDeAcceso.diagnosticar(self, u, eq["id"])
        d = u.pedir("get", f"/api/diagnosticos/{did}").get_json()
        self.assertTrue(d["concluyente"])
        self.assertEqual(len(d["hipotesis"]), 5)
        self.assertEqual(d["hipotesis"][0]["codigo"], "P01")
        self.assertGreaterEqual(len(d["hipotesis"][0]["recomendaciones"]), 2)
        self.assertTrue(d["evidencias"])
        self.assertTrue(any(r["hipotesis"] == "P01" and r["coincidencia"] == 100 and r["cumplidas"] == len(r["condiciones"]) for r in d["reglas"]))
        self.assertEqual(u.pedir("get", "/api/diagnosticos").get_json()["diagnosticos"][0]["codigo"], "P01")

    def test_respuestas_manipuladas_se_rechazan(self):
        u = self.usuario_nuevo()
        eq = u.pedir("post", "/api/equipos", EQUIPO).get_json()["equipo"]
        for malas in ([{"hecho": "sintoma_principal", "valor": "<script>"}], [{"hecho": "no_existe", "valor": "x"}],
                      [{"hecho": "sintoma_principal", "valor": "lentitud"}] * 2, [{"hecho": "archivos_corruptos", "valor": "falso"}], "texto", [None]):
            self.assertEqual(u.pedir("post", "/api/diagnosticos/paso", {"equipo_id": eq["id"], "respuestas": malas}).status_code, 422, malas)
        self.assertEqual(u.pedir("post", "/api/diagnosticos", {"equipo_id": eq["id"], "respuestas": []}).status_code, 422)

    def test_perfil_cambio_de_clave(self):
        u = self.usuario_nuevo()
        self.assertEqual(u.pedir("put", "/api/perfil", {"nombre": "Ana", "clave_actual": "otra-clave-xx", "clave_nueva": "Nueva-Clave-2026"}).status_code, 422)
        self.assertEqual(u.pedir("put", "/api/perfil", {"nombre": "Ana B", "clave_actual": CLAVE, "clave_nueva": "Nueva-Clave-2026"}).status_code, 200)

    def test_admin_pruebas_y_conocimiento(self):
        a = self.admin()
        r = a.pedir("post", "/api/admin/pruebas", {}).get_json()["pruebas"]
        self.assertEqual(len(r), 31)
        fallidas = [x for x in r if not x["aprobado"]]
        self.assertEqual(fallidas, [])
        h = next(x for x in a.pedir("get", "/api/admin/hipotesis").get_json()["hipotesis"] if x["codigo"] == "P01")
        ok = a.pedir("put", "/api/admin/hipotesis/P01", {"nombre": h["nombre"], "causa_probable": h["causa_probable"], "recomendaciones": h["recomendaciones"], "validada": True})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(a.pedir("put", "/api/admin/hipotesis/P01", {"nombre": "x", "causa_probable": "corta", "recomendaciones": ["uno"], "validada": True}).status_code, 422)

    def test_admin_no_puede_autodegradarse(self):
        a = self.admin()
        yo = a.pedir("get", "/api/admin/usuarios").get_json()["yo"]
        self.assertEqual(a.pedir("patch", f"/api/admin/usuarios/{yo}", {"rol": "usuario", "activo": True}).status_code, 422)
        self.usuario_nuevo()
        uid = next(x["id"] for x in a.pedir("get", "/api/admin/usuarios").get_json()["usuarios"] if x["id"] != yo)
        self.assertEqual(a.pedir("patch", f"/api/admin/usuarios/{uid}", {"rol": "usuario", "activo": False}).status_code, 200)
        self.assertEqual(a.pedir("patch", f"/api/admin/usuarios/{uid}", {"rol": "usuario", "activo": True}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
