# control_actas/bd_precios.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd


DDL = """
CREATE TABLE IF NOT EXISTS precios (
  actividad   TEXT PRIMARY KEY,
  precio      REAL NOT NULL,
  unidad      TEXT,
  updated_at  TEXT
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute(DDL)
    return con


def leer_precios(db_path: str | Path) -> pd.DataFrame:
    con = connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT actividad, precio, unidad, updated_at FROM precios ORDER BY actividad",
            con
        )
        return df
    finally:
        con.close()


def upsert_precios(db_path: str | Path, df: pd.DataFrame) -> None:
    """
    Inserta/actualiza por 'actividad' (PRIMARY KEY).
    Espera columnas: actividad, precio (unidad opcional)
    """
    if df.empty:
        return

    df2 = df.copy()
    df2["actividad"] = df2["actividad"].astype(str).str.strip()

    # Validaciones básicas
    df2 = df2[df2["actividad"].notna() & (df2["actividad"] != "")]
    if "precio" not in df2.columns:
        raise ValueError("Falta columna 'precio'")

    # Asegurar numérico
    df2["precio"] = pd.to_numeric(df2["precio"], errors="coerce")
    if df2["precio"].isna().any():
        bad = df2[df2["precio"].isna()][["actividad", "precio"]].head(10)
        raise ValueError(f"Hay precios no numéricos. Ejemplos:\n{bad}")

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
              precio=excluded.precio,
              unidad=excluded.unidad,
              updated_at=excluded.updated_at
            """,
            rows
        )
        con.commit()
    finally:
        con.close()


