import pandas as pd
import sqlite3
import unicodedata
import re
from pathlib import Path

# =========================
# CONFIG (NO TOCAR)
# =========================
INPUT_EXCEL = "Precios_referencia_v4.xlsx"
OUTPUT_DB = "precios_referencia.db"
TABLE_NAME = "precios_referencia"

# =========================
# NORMALIZACIÓN
# =========================
def normalizar(texto):
    if pd.isna(texto):
        return None
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")  # quita tildes
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)  # deja solo letras/números/espacios
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto
def normalizar_unidad(u: str | None) -> str:
    if u is None:
        return ""
    s = str(u).strip().upper()

    # Unificar símbolos comunes
    s = s.replace("M³", "M3").replace("M^3", "M3").replace("M3", "M3")
    s = s.replace("M²", "M2").replace("M^2", "M2").replace("M2", "M2")

    # Quitar espacios internos raros
    s = re.sub(r"\s+", "", s)

    # Sinónimos típicos
    mapa = {
        "UND": "UN",
        "UNID": "UN",
        "UNIDAD": "UN",
        "U": "UN",
        "ML": "M",      # si en tus actas ML realmente significa metro lineal
        "M.L": "M",
    }
    return mapa.get(s, s)
# =========================
# MAIN
# =========================
def main():
    excel_path = Path(INPUT_EXCEL)
    if not excel_path.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo de entrada: {excel_path.resolve()}"
        )

    # 1) Leer Excel
    df = pd.read_excel(excel_path)

    # 2) Renombrar columnas a nombres internos estándar
    df = df.rename(columns={
        "DESCRIPCIÓN": "descripcion",
        "UNIDAD": "unidad",
        "AJUSTE PRECIOS (CD+AIU) 0G_0G_2025": "precio"
    })

    # 3) Validar columnas requeridas
    requeridas = ["descripcion", "unidad", "precio"]
    faltantes = [c for c in requeridas if c not in df.columns]
    if faltantes:
        raise ValueError(
            "Faltan columnas requeridas en el Excel: "
            f"{faltantes}\n\nColumnas disponibles:\n{list(df.columns)}"
        )

    # 4) Normalizar descripción
    df["descripcion_norm"] = df["descripcion"].apply(normalizar)

    # 5) Seleccionar columnas finales
    out = df[["descripcion", "descripcion_norm", "unidad", "precio"]].copy()

    # 6) Guardar a SQLite (un solo archivo .db)
    #    replace = borra y vuelve a crear la tabla cada vez que corras (ideal para pruebas)
    db_path = Path(OUTPUT_DB).resolve()
    with sqlite3.connect(db_path) as conn:
        out.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

        # 7) Verificación rápida
        check = pd.read_sql(f"SELECT * FROM {TABLE_NAME} LIMIT 20", conn)

    print(f"✅ OK. Entrada: {excel_path.resolve()}")
    print(f"✅ OK. Salida DB: {db_path}")
    print(f"✅ Tabla creada/reemplazada: {TABLE_NAME}")
    print("\n🔎 Muestra (primeras 20 filas):")
    print(check)

if __name__ == "__main__":
    main()
    
def cargar_valores_referencia(db_path: str | Path) -> dict:
    """
    Retorna dict con llave (descripcion_norm, unidad_norm) -> precio_ref(float)
    """
    db_path = Path(db_path)

    if not db_path.exists():
        raise FileNotFoundError(f"No se encontró la BD en: {db_path.resolve()}")

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql(
            "SELECT descripcion_norm, unidad, precio FROM precios_referencia",
            conn
        )

    ref = {}
    for _, r in df.iterrows():
        desc_norm = (r["descripcion_norm"] or "").strip()
        un_norm = normalizar_unidad(r["unidad"])
        try:
            precio = float(r["precio"])
        except Exception:
            continue

        if desc_norm and un_norm:
            ref[(desc_norm, un_norm)] = precio

    return ref


def filtrar_referencias_criticas(valores_referencia: dict, actividades_criticas: dict) -> dict:
    """
    valores_referencia:
        dict[(descripcion_norm, unidad_norm)] -> precio
    actividades_criticas:
        dict[str, any]  (llaves = nombres de actividades críticas)
    """

    # Normalizamos las llaves del diccionario crítico
    crit_norm = {normalizar(k) for k in actividades_criticas.keys()}
    crit_norm.discard(None)

    filtradas = {}

    for (desc_norm, un_norm), precio in valores_referencia.items():
        if desc_norm in crit_norm:
            filtradas[(desc_norm, un_norm)] = precio


    return filtradas


def cargar_valores_referencia(db_path: str | Path) -> dict:
    """
    Lee la BD SQLite de precios y retorna un dict:
        { actividad: precio }

    Soporta BDs viejas/nuevas:
    - tabla 'precios' (nuevo)
    - tabla 'precios_referencia_v4' (legacy)
    - tabla 'precios_referencia' (legacy)

    Intenta detectar columnas razonables para actividad y precio.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return {}

    con = sqlite3.connect(str(db_path))
    try:
        tablas = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()]

        # Orden de preferencia (la primera que exista gana)
        candidatos = ["precios", "precios_referencia_v4", "precios_referencia"]
        table = next((t for t in candidatos if t in tablas), None)
        if not table:
            return {}

        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table});").fetchall()]
        cols_low = {c.lower(): c for c in cols}

        # posibles nombres de columnas
        actividad_col = None
        precio_col = None

        for k in ["actividad", "item", "descripcion", "actividad_desc", "nombre", "concepto"]:
            if k in cols_low:
                actividad_col = cols_low[k]
                break

        for k in ["precio", "valor", "v_unitario", "unitario", "precio_unitario", "pu"]:
            if k in cols_low:
                precio_col = cols_low[k]
                break

        # Caso común legacy: actividad + precio
        if actividad_col is None and "actividad" in cols_low:
            actividad_col = cols_low["actividad"]
        if precio_col is None and "precio" in cols_low:
            precio_col = cols_low["precio"]

        if actividad_col is None or precio_col is None:
            return {}

        df = pd.read_sql_query(
            f"SELECT {actividad_col} AS actividad, {precio_col} AS precio FROM {table}",
            con,
        )

        if df.empty:
            return {}

        df["actividad"] = df["actividad"].astype(str).str.strip()
        df["precio"] = pd.to_numeric(df["precio"], errors="coerce")

        df = df[df["actividad"].notna() & (df["actividad"] != "")]
        df = df[df["precio"].notna()]

        return dict(zip(df["actividad"].tolist(), df["precio"].tolist()))
    finally:
        con.close()
