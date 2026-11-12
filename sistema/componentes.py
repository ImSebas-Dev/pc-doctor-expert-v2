"""Componentes del equipo: validación, resumen legible y hechos que se entregan al motor de inferencia."""
from .validacion import ErrorValidacion, booleano, cadena, entero, opcion, opcional

TIPOS_RAM = ("DDR3", "DDR4", "DDR5", "LPDDR4", "LPDDR5")
TIPOS_DISCO = ("SSD NVMe", "SSD SATA", "HDD")
MAX_MODULOS = MAX_DISCOS = 8


def _lista(d: dict, clave: str, etiqueta: str) -> list[dict]:
    v = d.get(clave)
    if not isinstance(v, list) or not 1 <= len(v) <= MAX_MODULOS or not all(isinstance(x, dict) for x in v):
        raise ErrorValidacion(f"{etiqueta}: registra entre 1 y {MAX_MODULOS}.", clave)
    return v


def _en(clave: str, i: int, f, *args):
    """Ejecuta un validador y prefija el campo con su posición (ram.0.tipo) para marcar el campo exacto."""
    try:
        return f(*args)
    except ErrorValidacion as e:
        raise ErrorValidacion(e.mensaje, f"{clave}.{i}.{e.campo}")


def leer_equipo(d: dict) -> dict:
    ram = []
    for i, m in enumerate(_lista(d, "ram", "Memoria RAM")):
        n = f"Módulo de RAM {i + 1}"
        ram.append({"capacidad_gb": _en("ram", i, entero, m, "capacidad_gb", f"{n} · capacidad (GB)", 1, 256),
                    "tipo": _en("ram", i, opcion, m, "tipo", f"{n} · tipo", TIPOS_RAM),
                    "frecuencia_mhz": _en("ram", i, entero, m, "frecuencia_mhz", f"{n} · frecuencia (MHz)", 400, 10000),
                    "marca": _en("ram", i, opcional, m, "marca", f"{n} · marca", 40)})
    tipos = {m["tipo"] for m in ram}
    if len(tipos) > 1:
        raise ErrorValidacion(f"No se pueden mezclar módulos {' y '.join(sorted(tipos))}: no son compatibles entre sí. Revisa el tipo de cada módulo.", "ram.0.tipo")
    discos = []
    for i, x in enumerate(_lista(d, "discos", "Almacenamiento")):
        n = f"Disco {i + 1}"
        discos.append({"tipo": _en("discos", i, opcion, x, "tipo", f"{n} · tipo", TIPOS_DISCO),
                       "capacidad_gb": _en("discos", i, entero, x, "capacidad_gb", f"{n} · capacidad (GB)", 8, 100000),
                       "modelo": _en("discos", i, opcional, x, "modelo", f"{n} · modelo", 60),
                       "es_sistema": _en("discos", i, booleano, x, "es_sistema", f"{n} · disco del sistema")})
    if sum(x["es_sistema"] for x in discos) != 1:
        raise ErrorValidacion("Indica cuál es el disco donde está instalado el sistema operativo (solo uno).", "discos.0.es_sistema")
    return {"nombre": cadena(d, "nombre", "Nombre del equipo", 2, 60), "sistema_operativo": cadena(d, "sistema_operativo", "Sistema operativo", 2, 60),
            "procesador": cadena(d, "procesador", "Procesador", 2, 80), "cpu_nucleos": entero(d, "cpu_nucleos", "Núcleos del procesador", 1, 128),
            "gpu": cadena(d, "gpu", "Tarjeta gráfica", 2, 80), "gpu_dedicada": booleano(d, "gpu_dedicada", "Tarjeta gráfica dedicada"),
            "ram": ram, "discos": discos}


def _capacidad(gb: int) -> str:
    return f"{gb / 1000:g} TB" if gb >= 1000 else f"{gb} GB"


def etiqueta_ram(m: dict) -> str:
    return f"{m['capacidad_gb']} GB {m['tipo']} a {m['frecuencia_mhz']} MHz" + (f" ({m['marca']})" if m.get("marca") else "")


def etiqueta_disco(x: dict, numero: int) -> str:
    return f"Disco {numero}: {x['tipo']} de {_capacidad(x['capacidad_gb'])}" + (f", {x['modelo']}" if x.get("modelo") else "") + (" (sistema)" if x["es_sistema"] else "")


def resumen(ram: list[dict], discos: list[dict]) -> dict:
    """Totales y avisos de compatibilidad en lenguaje sencillo (no son errores: los módulos son compatibles)."""
    avisos, frecuencias = [], {m["frecuencia_mhz"] for m in ram}
    if len(ram) == 1:
        avisos.append("Tienes un solo módulo de RAM: trabaja en canal único, más lento que con dos módulos iguales.")
    if len(frecuencias) > 1:
        avisos.append(f"Los módulos tienen frecuencias distintas: todos funcionarán a {min(frecuencias)} MHz, la del más lento.")
    if len({m["capacidad_gb"] for m in ram}) > 1:
        avisos.append("Los módulos tienen capacidades distintas: funcionan, pero parte de la memoria puede trabajar en canal único.")
    return {"ram_total_gb": sum(m["capacidad_gb"] for m in ram), "ram_modulos": len(ram), "frecuencia_efectiva_mhz": min(frecuencias) if ram else None,
            "almacenamiento_total_gb": sum(x["capacidad_gb"] for x in discos), "avisos": avisos}


def hechos(equipo: dict, ram: list[dict], discos: list[dict]) -> dict[str, str]:
    """Hechos que el motor recibe como evidencia del equipo (el motor deriva el resto con las reglas RH-14 a RH-16)."""
    sistema = next((x for x in discos if x["es_sistema"]), None)
    return {"ram_total_gb": str(sum(m["capacidad_gb"] for m in ram)), "ram_modulos": str(len(ram)),
            "ram_capacidades_distintas": str(len({m["capacidad_gb"] for m in ram})), "ram_frecuencias_distintas": str(len({m["frecuencia_mhz"] for m in ram})),
            "cpu_nucleos": str(equipo["cpu_nucleos"]), "gpu_dedicada": "verdadero" if equipo["gpu_dedicada"] else "falso",
            "disco_sistema_hdd": "verdadero" if sistema and sistema["tipo"] == "HDD" else "falso"}
