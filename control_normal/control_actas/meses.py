# control_actas/meses.py
import os
import re

MAPA_MESES = {
    "enero": 1, "ene": 1,
    "febrero": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6,
    "julio": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "septiembre": 9, "sep": 9, "setiembre": 9,
    "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12,
}

def parsear_anio_mes_desde_carpeta(nombre: str):
    """
    Recibe algo tipo 'julio2025', 'actas_jul2024', etc.
    Devuelve (anio, mes_nombre_texto) si los encuentra.
    """
    nombre = str(nombre).lower()

    anio = None
    m = re.search(r"(\d{4})", nombre)
    if m:
        anio = int(m.group(1))

    mes_nombre = None
    for texto_mes in MAPA_MESES.keys():
        if texto_mes in nombre:
            mes_nombre = texto_mes
            break

    return anio, mes_nombre


def listar_carpetas_mes(base_root: str, proyecto: str):
    """
    Devuelve una lista de dicts con la info de cada carpeta de mes
    que exista dentro de control_actas/actas del proyecto.
    """
    actas_root = os.path.join(base_root, proyecto, "control_actas", "actas")
    meses = []

    if not os.path.isdir(actas_root):
        return meses

    for nombre in os.listdir(actas_root):
        ruta = os.path.join(actas_root, nombre)
        if os.path.isdir(ruta):
            anio, mes_nombre = parsear_anio_mes_desde_carpeta(nombre)
            meses.append({
                "carpeta": nombre,
                "anio": anio,
                "mes_nombre": mes_nombre
            })

    def clave_orden(m):
        anio = m["anio"] or 0
        mes_num = MAPA_MESES.get(m["mes_nombre"], 0) if m["mes_nombre"] else 0
        return (anio, mes_num)

    meses.sort(key=clave_orden)
    return meses
