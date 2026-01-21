# control_actas/excel_utils.py
import pandas as pd
import re
import unicodedata

def obtener_columnas(ws):
    """
    Lee encabezados en filas 8 y 9, construye un dict:
    { NOMBRE_COLUMNA: LETRA_COLUMNA }
    """
    encabezados_fila1 = []
    encabezados_fila2 = []
    for i in range(0, ws.max_column):
        try:
            encabezados_fila1.append(ws[f"{chr(65+i)}8"].value)
        except Exception:
            encabezados_fila1.append(None)
        try:
            encabezados_fila2.append(ws[f"{chr(65+i)}9"].value)
        except Exception:
            encabezados_fila2.append(None)

    nombres = []
    for e1, e2 in zip(encabezados_fila1, encabezados_fila2):
        if e1 and e2:
            nombres.append(f"{e1} {e2}".strip().upper())
        elif e1:
            nombres.append(str(e1).strip().upper())
        elif e2:
            nombres.append(str(e2).strip().upper())
        else:
            nombres.append(None)

    columnas = {}
    for i, nombre in enumerate(nombres):
        if nombre:
            columnas[nombre] = chr(65 + i)
    return columnas


def preparar_registro(df: pd.DataFrame, anio_actual: int, mes_nombre: str) -> pd.DataFrame:
    df = df.copy()

    if "anio" not in df.columns:
        df["anio"] = anio_actual
    if "mes" not in df.columns:
        df["mes"] = mes_nombre

    if "valor_unitario_original" in df.columns:
        df = df.rename(columns={"valor_unitario_original": "valor_unitario_pagado"})

    for col in ["valor_unitario_pagado", "cantidad_presenta", "valor_pactado", "valor_ajustado"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "valor_unitario_pagado" in df.columns and "cantidad_presenta" in df.columns:
        df["valor_pagado"] = df["valor_unitario_pagado"] * df["cantidad_presenta"]

    if "valor_ajustado" not in df.columns:
        if "valor_pactado" in df.columns and "cantidad_presenta" in df.columns:
            df["valor_ajustado"] = df["valor_pactado"] * df["cantidad_presenta"]

    if "valor_pagado" in df.columns and "valor_ajustado" in df.columns:
        df["descuento"] = df["valor_pagado"] - df["valor_ajustado"]

    columnas_orden = [
        "anio", "mes", "archivo", "contratista", "item", "descripcion",
        "un", "valor_unitario_pagado", "valor_pactado",
        "cantidad_presenta", "valor_pagado", "valor_ajustado", "descuento"
    ]
    cols_presentes = [c for c in columnas_orden if c in df.columns]
    extras = [c for c in df.columns if c not in cols_presentes]
    return df[cols_presentes + extras]


def _norm_texto(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _norm_unidad(u: str) -> str:
    u = _norm_texto(u)
    # opcional: homologaciones típicas (ajústalas a tu realidad)
    u = u.replace("m 3", "m3").replace("m 2", "m2")
    u = u.replace("und", "un").replace("unidad", "un")
    return u
