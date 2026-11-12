"""Equipos del usuario y sus componentes (RF-01). Toda consulta filtra por el dueño: un usuario nunca ve equipos ajenos."""
import psycopg.errors
from flask import Blueprint, abort, g, jsonify

from .. import componentes
from ..db import conexion, todos, uno
from ..seguridad import requiere_sesion
from ..validacion import ErrorValidacion, cuerpo

bp = Blueprint("equipos", __name__, url_prefix="/api/equipos")
CAMPOS = "id, nombre, sistema_operativo, procesador, cpu_nucleos, gpu, gpu_dedicada"


def con_componentes(filas: list[dict]) -> list[dict]:
    """Agrega a cada equipo sus módulos de RAM, sus discos y el resumen con avisos de compatibilidad."""
    ids = [f["id"] for f in filas]
    ram = todos("SELECT id, equipo_id, capacidad_gb, tipo, frecuencia_mhz, marca FROM tx.equipo_ram WHERE equipo_id = ANY(%s) ORDER BY id", (ids,))
    discos = todos("SELECT id, equipo_id, tipo, capacidad_gb, modelo, es_sistema FROM tx.equipo_disco WHERE equipo_id = ANY(%s) ORDER BY id", (ids,))
    for f in filas:
        f["ram"] = [{**m, "etiqueta": componentes.etiqueta_ram(m)} for m in ram if m["equipo_id"] == f["id"]]
        f["discos"] = [{**x, "etiqueta": componentes.etiqueta_disco(x, i)} for i, x in enumerate((x for x in discos if x["equipo_id"] == f["id"]), 1)]
        f["resumen"] = componentes.resumen(f["ram"], f["discos"])
    return filas


def _guardar(datos: dict, equipo_id: int | None):
    cx = conexion()
    try:
        with cx.transaction():
            valores = (datos["nombre"], datos["sistema_operativo"], datos["procesador"], datos["cpu_nucleos"], datos["gpu"], datos["gpu_dedicada"])
            if equipo_id is None:
                fila = uno(f"INSERT INTO tx.equipo(nombre,sistema_operativo,procesador,cpu_nucleos,gpu,gpu_dedicada,usuario_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING {CAMPOS}", (*valores, g.usuario["id"]))
            else:
                fila = uno(f"UPDATE tx.equipo SET nombre=%s, sistema_operativo=%s, procesador=%s, cpu_nucleos=%s, gpu=%s, gpu_dedicada=%s WHERE id=%s AND usuario_id=%s RETURNING {CAMPOS}",
                           (*valores, equipo_id, g.usuario["id"]))
                if fila is None:
                    abort(404)
                cx.execute("DELETE FROM tx.equipo_ram WHERE equipo_id=%s", (equipo_id,))
                cx.execute("DELETE FROM tx.equipo_disco WHERE equipo_id=%s", (equipo_id,))
            with cx.cursor() as cur:
                cur.executemany("INSERT INTO tx.equipo_ram(equipo_id,capacidad_gb,tipo,frecuencia_mhz,marca) VALUES (%s,%s,%s,%s,%s)",
                                [(fila["id"], m["capacidad_gb"], m["tipo"], m["frecuencia_mhz"], m["marca"]) for m in datos["ram"]])
                cur.executemany("INSERT INTO tx.equipo_disco(equipo_id,tipo,capacidad_gb,modelo,es_sistema) VALUES (%s,%s,%s,%s,%s)",
                                [(fila["id"], x["tipo"], x["capacidad_gb"], x["modelo"], x["es_sistema"]) for x in datos["discos"]])
    except psycopg.errors.UniqueViolation:
        raise ErrorValidacion("Ya tienes un equipo con ese nombre.", "nombre")
    return con_componentes([fila])[0]


@bp.get("")
@requiere_sesion
def listar():
    return jsonify(equipos=con_componentes(todos(f"SELECT {CAMPOS} FROM tx.equipo WHERE usuario_id=%s ORDER BY nombre", (g.usuario["id"],))))


@bp.post("")
@requiere_sesion
def crear():
    return jsonify(equipo=_guardar(componentes.leer_equipo(cuerpo()), None)), 201


@bp.put("/<int:equipo_id>")
@requiere_sesion
def editar(equipo_id):
    return jsonify(equipo=_guardar(componentes.leer_equipo(cuerpo()), equipo_id))


@bp.delete("/<int:equipo_id>")
@requiere_sesion
def eliminar(equipo_id):
    if not uno("DELETE FROM tx.equipo WHERE id=%s AND usuario_id=%s RETURNING id", (equipo_id, g.usuario["id"])):
        abort(404)
    return "", 204
