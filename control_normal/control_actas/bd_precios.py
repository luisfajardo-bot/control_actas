from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd


DDL_PRECIOS = """
CREATE TABLE IF NOT EXISTS precios (
  actividad TEXT PRIMARY KEY,
  precio REAL NOT NULL,
  unidad TEXT,
  updated_at TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    # OJO: crear esta tabla NO daña nada si ya tienes otra (solo asegura compatibilidad futura)
    con.execute(DDL_PRECIOS)
    return con


def _tabla_precios_existente(con: sqlite3.Connection) -> str:
    """
    Devuelve el nombre de la tabla real que contiene los precios.
    Preferencias:
    1) precios
    2) precios_referencia
    3) precios_referencia_v4
    """
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    tablas = {r[0] for r in rows}

    if "precios" in tablas:
        return "precios"
    if "precios_referencia" in tablas:
        return "precios_referencia"
    if "precios_referencia_v4" in tablas:
        return "precios_referencia_v4"

    # Si no hay ninguna, por compatibilidad usamos la tabla nueva (ya creada por DDL_PRECIOS)
    return "precios"


def leer_precios(db_path: str | Path) -> pd.DataFrame:
    con = connect(db_path)
    try:
        tabla = _tabla_precios_existente(con)

        df = pd.read_sql_query(
            f"SELECT actividad, precio, unidad, updated_at FROM {tabla} ORDER BY actividad",
            con,
        )

        # Por si alguna tabla vieja no trae columnas (compat suave)
        for col in ["actividad", "precio", "unidad", "updated_at"]:
            if col not in df.columns:
                df[col] = None

        df = df[["actividad", "precio", "unidad", "updated_at"]]
        return df

    finally:
        con.close()


def upsert_precios(db_path: str | Path, df: pd.DataFrame) -> None:
    """
    Inserta/actualiza por 'actividad' (PRIMARY KEY).
    Espera columnas: actividad, precio (unidad opcional)
    """
    if df is None or df.empty:
        return

    df2 = df.copy()
    df2["actividad"] = df2["actividad"].astype(str).str.strip()

    # Validaciones básicas
    df2 = df2[df2["actividad"].notna() & (df2["actividad"] != "")]
    if "precio" not in df2.columns:
        raise ValueError("Falta columna 'precio'")

    df2["precio"] = pd.to_numeric(df2["precio"], errors="coerce")
    if df2["precio"].isna().any():
        bad = df2[df2["precio"].isna()][["actividad", "precio"]].head(10)
        raise ValueError(f"Hay precios no numéricos. Ejemplos:\n{bad}")

    if "unidad" not in df2.columns:
        df2["unidad"] = None

    now = datetime.now().isoformat(timespec="seconds")
    df2["updated_at"] = now

    rows = list(
        df2[["actividad", "precio", "unidad", "updated_at"]]
        .itertuples(index=False, name=None)
    )

    con = connect(db_path)
    try:
        tabla = _tabla_precios_existente(con)

        # Si la tabla real NO es 'precios', igual hacemos upsert sobre esa.
        # (Así no “pierdes” datos escribiendo en una tabla nueva vacía.)
        con.executemany(
            f"""
            INSERT INTO {tabla} (actividad, precio, unidad, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(actividad) DO UPDATE SET
              precio=excluded.precio,
              unidad=excluded.unidad,
              updated_at=excluded.updated_at
            """,
            rows,
        )
        con.commit()
    finally:
        con.close()




