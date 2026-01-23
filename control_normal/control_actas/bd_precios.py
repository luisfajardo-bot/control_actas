# control_actas/bd_precios.py
from __future__ import annotations

import sqlite3


from pathlib import Path
from datetime import datetime
from typing import Iterable, Optional, Tuple

import pandas as pd


# =========================
# Esquema
# =========================
DDL = """
CREATE TABLE IF NOT EXISTS precios (
  actividad   TEXT PRIMARY KEY,
  precio      REAL NOT NULL,
  unidad      TEXT,
  updated_at  TEXT
);
"""

# (Opcional pero recomendado) historial/auditoría
DDL_LOG = """
CREATE TABLE IF NOT EXISTS precios_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  actividad   TEXT NOT NULL,
  precio_old  REAL,
  precio_new  REAL,
  unidad_old  TEXT,
  unidad_new  TEXT,
  changed_at  TEXT NOT NULL
);
"""


# =========================
# Conexión
# =========================
def connect(db_path: str | Path) -> sqlite3.Connection:
    """
    Conecta y asegura tablas. Ojo: WAL puede fallar en algunos FS raros, pero suele ir bien.
    """
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")

    con.execute(DDL)
    con.execute(DDL_LOG)
    return con



















# =========================
# Lecturas
# =========================
def leer_precios(db_path: str | Path) -> pd.DataFrame:
    con = connect(db_path)
    try:
        return pd.read_sql_query(
            "SELECT actividad, precio, unidad, updated_at FROM precios ORDER BY actividad",
            con,
        )
    finally:
        con.close()




















def existe_actividad(db_path: str | Path, actividad: str) -> bool:
    actividad = (actividad or "").strip()
    if not actividad:
        return False
    con = connect(db_path)
    try:
        cur = con.execute("SELECT 1 FROM precios WHERE actividad = ? LIMIT 1", (actividad,))
        return cur.fetchone() is not None
    finally:
        con.close()


def obtener_precio(db_path: str | Path, actividad: str) -> Optional[float]:
    actividad = (actividad or "").strip()
    if not actividad:
        return None
    con = connect(db_path)
    try:
        cur = con.execute("SELECT precio FROM precios WHERE actividad = ? LIMIT 1", (actividad,))
        row = cur.fetchone()
        return float(row[0]) if row else None
    finally:
        con.close()


# =========================
# Escrituras / Upserts
# =========================
def _normalizar_df_precios(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza y valida:
    - actividad: str.strip()
    - precio: numérico
    - unidad: opcional
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["actividad", "precio", "unidad"])

    df2 = df.copy()

    # columnas mínimas
    if "actividad" not in df2.columns:
        raise ValueError("Falta columna 'actividad'")
    if "precio" not in df2.columns:
        raise ValueError("Falta columna 'precio'")

    df2["actividad"] = df2["actividad"].astype(str).str.strip()


    # filtrar vacíos
    df2 = df2[df2["actividad"].notna() & (df2["actividad"] != "")]




    # asegurar numérico
    df2["precio"] = pd.to_numeric(df2["precio"], errors="coerce")
    if df2["precio"].isna().any():
        bad = df2[df2["precio"].isna()][["actividad", "precio"]].head(10)
        raise ValueError(f"Hay precios no numéricos. Ejemplos:\n{bad}")

    if "unidad" not in df2.columns:
        df2["unidad"] = None
    else:
        # unidad: limpiamos strings si vienen
        df2["unidad"] = df2["unidad"].apply(lambda x: str(x).strip() if pd.notna(x) else None)

    # quitar duplicados por actividad (nos quedamos con el último)
    df2 = df2.drop_duplicates(subset=["actividad"], keep="last")

    return df2[["actividad", "precio", "unidad"]].reset_index(drop=True)


def upsert_precios(db_path: str | Path, df: pd.DataFrame, *, log_changes: bool = True) -> None:
    """
    Inserta/actualiza por 'actividad' (PRIMARY KEY).
    Espera columnas: actividad, precio (unidad opcional)

    log_changes=True: guarda auditoría en precios_log con valores old/new.
    """
    df2 = _normalizar_df_precios(df)
    if df2.empty:
        return

    now = datetime.now().isoformat(timespec="seconds")

    con = connect(db_path)
    try:
        # Para logging: capturamos valores previos de las actividades que vamos a tocar
        prev = {}
        if log_changes:
            acts = tuple(df2["actividad"].tolist())
            # Evitar query inválida si no hay acts
            if acts:
                qmarks = ",".join(["?"] * len(acts))
                cur = con.execute(
                    f"SELECT actividad, precio, unidad FROM precios WHERE actividad IN ({qmarks})",
                    acts,
                )
                prev = {a: (p, u) for (a, p, u) in cur.fetchall()}

        # Upsert en precios
        rows = []
        for _, r in df2.iterrows():
            rows.append((r["actividad"], float(r["precio"]), r["unidad"], now))

        con.executemany(
            """
            INSERT INTO precios (actividad, precio, unidad, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(actividad) DO UPDATE SET
              precio=excluded.precio,
              unidad=excluded.unidad,
              updated_at=excluded.updated_at
            """,
            rows,
        )

        # Auditoría
        if log_changes:
            log_rows = []
            for (actividad, precio_new, unidad_new, _) in rows:
                if actividad in prev:
                    precio_old, unidad_old = prev[actividad]
                else:
                    precio_old, unidad_old = (None, None)

                # Guardar solo si realmente cambió algo (o si es nuevo)
                changed = (precio_old is None) or (float(precio_old) != float(precio_new)) or ((unidad_old or None) != (unidad_new or None))
                if changed:
                    log_rows.append((actividad, precio_old, precio_new, unidad_old, unidad_new, now))

            if log_rows:
                con.executemany(
                    """
                    INSERT INTO precios_log (actividad, precio_old, precio_new, unidad_old, unidad_new, changed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    log_rows,
                )

        con.commit()
    finally:
        con.close()


def actualizar_precio(db_path: str | Path, actividad: str, precio: float, unidad: Optional[str] = None) -> None:
    """
    Helper para actualizar una sola actividad.
    """
    df = pd.DataFrame([{"actividad": actividad, "precio": precio, "unidad": unidad}])
    upsert_precios(db_path, df, log_changes=True)


def eliminar_actividad(db_path: str | Path, actividad: str, *, log_delete: bool = True) -> None:
    """
    (Opcional) Elimina una actividad. Útil si quieres permitir limpieza desde OFICINA.
    No lo usaría si no estás seguro, pero te lo dejo listo.


    """
    actividad = (actividad or "").strip()
    if not actividad:
        return

    now = datetime.now().isoformat(timespec="seconds")
    con = connect(db_path)
    try:
        if log_delete:
            cur = con.execute("SELECT precio, unidad FROM precios WHERE actividad = ? LIMIT 1", (actividad,))
            row = cur.fetchone()
            if row:
                precio_old, unidad_old = row
                con.execute(
                    """
                    INSERT INTO precios_log (actividad, precio_old, precio_new, unidad_old, unidad_new, changed_at)
                    VALUES (?, ?, NULL, ?, NULL, ?)
                    """,
                    (actividad, precio_old, unidad_old, now),
                )

        con.execute("DELETE FROM precios WHERE actividad = ?", (actividad,))
        con.commit()
    finally:
        con.close()





# =========================
# Utilidades
# =========================
def validar_db(db_path: str | Path) -> Tuple[bool, str]:
    """
    Verifica que exista la tabla y que no esté corrupta (chequeo básico).
    """
    con = connect(db_path)
    try:
        # pragma integrity_check retorna 'ok' si todo bien
        cur = con.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        if not res:
            return False, "No se pudo ejecutar integrity_check."
        ok = (str(res[0]).lower() == "ok")
        return ok, str(res[0])
    finally:







