# control_actas/bd_precios.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd


# =========================
# DDL
# =========================
DDL = """
CREATE TABLE IF NOT EXISTS precios (
    actividad   TEXT PRIMARY KEY,
    precio      REAL NOT NULL,
    unidad      TEXT,
    updated_at  TEXT
);
"""


# =========================
# Conexión
# =========================
def connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute(DDL)
    return con


# =========================
# Lectura
# =========================
def leer_precios(db_path: str | Path) -> pd.DataFrame:
    con = connect(db_path)
    try:
        df = pd.read_sql_query(
            """
            SELECT actividad, precio, unidad, updated_at
            FROM precios
            ORDER BY actividad
            """,
            con,
        )
        return df
    finally:
        con.close()


# =========================
# Upsert
# =========================
def upsert_precios(db_path: str | Path, df: pd.DataFrame) -> None:
    """
    Inserta / actualiza precios por 'actividad' (PRIMARY KEY).

    Espera columnas:
    - actividad
    - precio
    - unidad (opcional)
    """
    if df.empty:
        return

    df2 = df.copy()

    # Normalizar actividad
    df2["actividad"] = df2["actividad"].astype(str).str.strip()

    # Validaciones básicas
    df2 = df2[df2["actividad"].notna() & (df2["actividad"] != "")]

    if "precio" not in df2.columns:
        raise ValueError("Falta columna 'precio'")

    # Asegurar numérico
    df2["precio"] = pd.to_numeric(df2["precio"], errors="coerce")

    if df2["precio"].isna().any():
        bad = df2[df2["precio"].isna()][["actividad", "precio"]].head(10)
        raise ValueError(
            f"Hay precios no numéricos. Ejemplos:\n{bad}"
        )

    # Campos adicionales
    now = datetime.now().isoformat(timespec="seconds")

    if "unidad" not in df2.columns:
        df2["unidad"] = None

    df2["updated_at"] = now

    rows = list(
        df2[["actividad", "precio", "unidad", "updated_at"]]
        .itertuples(index=False, name=None)
    )

    con = connect(db_path)
    try:
        con.executemany(
            """
            INSERT INTO precios (actividad, precio, unidad, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(actividad) DO UPDATE SET
                precio     = excluded.precio,
                unidad     = excluded.unidad,
                updated_at = excluded.updated_at
            """,
            rows,
        )
        con.commit()
    finally:
        con.close()


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








