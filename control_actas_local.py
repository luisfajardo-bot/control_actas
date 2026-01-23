# control_actas_local.py
from __future__ import annotations

import os
import sys
import tempfile
import sqlite3
import importlib.util
import importlib
from pathlib import Path
from typing import Optional, Dict, Any, Callable

_BACKEND_CACHE: dict[str, Any] = {}  # {"normal": module, "critico": module}


def is_cloud() -> bool:
    try:
        import streamlit as st
        return "DRIVE_ROOT_FOLDER_ID" in st.secrets
    except Exception:
        pass
    return any(k in os.environ for k in ("STREAMLIT_RUNTIME", "STREAMLIT_SERVER_HEADLESS"))


def _backend_pkg_dir_for(modo: str) -> Path:
    """
    Carpeta que contiene el package 'control_actas' del backend:
      control_normal/control_actas
      control_critico/control_actas
    """
    root = Path(__file__).resolve().parent
    base = root / ("control_critico" if modo == "critico" else "control_normal")
    return base / "control_actas"


def _import_backend(modo: str):
    """
    Importa el package del backend como paquete aislado (nombre único),
    sin sys.path y sin purgas globales.
    """
    if modo in _BACKEND_CACHE:
        return _BACKEND_CACHE[modo]

    pkg_dir = _backend_pkg_dir_for(modo)
    init_py = pkg_dir / "__init__.py"
    if not init_py.exists():
        raise FileNotFoundError(f"No existe __init__.py del backend en: {init_py}")

    module_name = f"control_actas__{modo}"

    spec = importlib.util.spec_from_file_location(
        module_name,
        str(init_py),
        submodule_search_locations=[str(pkg_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"No pude crear spec para backend '{modo}' desde: {init_py}")

    mod = importlib.util.module_from_spec(spec)

    # CLAVE: registrar el paquete antes de ejecutarlo para que funcionen imports relativos
    sys.modules[module_name] = mod

    try:
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    except Exception:
        sys.modules.pop(module_name, None)
        raise

    _BACKEND_CACHE[modo] = mod
    return mod


def resolver_base_root(*, anio_proyecto: Optional[int | str] = None) -> Path:
    if is_cloud():
        return Path(tempfile.gettempdir()) / "control_actas_data"
    return Path(r"G:\Mi unidad\Subcontratos")


def _fallback_cargar_valores_referencia(db_path_local: Path) -> dict:
    """
    Fallback ultra robusto:
    - Intenta leer desde varias tablas posibles
    - Devuelve dict {actividad: precio}
    """
    p = Path(db_path_local)
    if not p.exists():
        return {}

    con = sqlite3.connect(str(p))
    try:
        tablas = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()]

        # Orden de preferencia
        candidatas = [
            "precios",                # tu tabla editable
            "precios_referencia",     # tu tabla vieja
            "precios_referencia_v4",  # tu tabla nueva
        ]

        tabla = next((t for t in candidatas if t in tablas), None)
        if not tabla:
            return {}

        # columnas disponibles
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({tabla});").fetchall()]

        # nombres típicos
        col_act = None
        for c in ("actividad", "ACTIVIDAD", "item", "ITEM", "codigo", "CODIGO", "nombre", "NOMBRE"):
            if c in cols:
                col_act = c
                break

        col_prec = None
        for c in ("precio", "PRECIO", "valor", "VALOR", "unitario", "UNITARIO", "pu", "PU"):
            if c in cols:
                col_prec = c
                break

        if not col_act or not col_prec:
            return {}

        rows = con.execute(
            f"SELECT {col_act}, {col_prec} FROM {tabla} WHERE {col_act} IS NOT NULL;"
        ).fetchall()

        out: dict[str, float] = {}
        for a, v in rows:
            if a is None:
                continue
            a2 = str(a).strip()
            if not a2:
                continue
            try:
                out[a2] = float(v)
            except Exception:
                # ignora valores no numéricos
                continue

        return out
    finally:
        con.close()


def _resolver_cargar_valores_referencia(backend_pkg) -> Callable[[Path], dict]:
    """
    1) Intenta obtener backend.bd_precios.cargar_valores_referencia (si existe)
    2) Si no existe, intenta importar submódulo bd_precios del paquete aislado
    3) Si aún no existe, usa fallback directo a SQLite
    """
    # (1) Si el __init__ ya expone bd_precios
    try:
        bd = getattr(backend_pkg, "bd_precios", None)
        if bd is not None:
            fn = getattr(bd, "cargar_valores_referencia", None)
            if callable(fn):
                return fn  # type: ignore[return-value]
    except Exception:
        pass

    # (2) Importar submódulo explícitamente dentro del paquete aislado
    try:
        modname = backend_pkg.__name__  # control_actas__normal / control_actas__critico
        bd2 = importlib.import_module(f"{modname}.bd_precios")
        fn2 = getattr(bd2, "cargar_valores_referencia", None)
        if callable(fn2):
            return fn2  # type: ignore[return-value]

        # si no existe esa fn pero sí existe leer_precios, podríamos construir dict desde DF
        leer = getattr(bd2, "leer_precios", None)
        if callable(leer):
            def _from_leer(db_path_local: Path) -> dict:
                df = leer(db_path_local)
                if df is None or getattr(df, "empty", True):
                    return {}
                # espera columnas: actividad, precio
                if "actividad" not in df.columns or "precio" not in df.columns:
                    return _fallback_cargar_valores_referencia(db_path_local)
                out = {}
                for _, r in df.iterrows():
                    a = str(r["actividad"]).strip()
                    if not a:
                        continue
                    try:
                        out[a] = float(r["precio"])
                    except Exception:
                        continue
                return out
            return _from_leer
    except Exception:
        pass

    # (3) fallback final
    return _fallback_cargar_valores_referencia


def get_backend(modo: str, *, anio_proyecto: Optional[int | str] = None) -> Dict[str, Any]:
    if modo not in ("normal", "critico"):
        raise ValueError(f"modo inválido: {modo}. Usa 'normal' o 'critico'.")

    backend = _import_backend(modo)

    base_root_path = resolver_base_root(anio_proyecto=anio_proyecto)
    base_root_path.mkdir(parents=True, exist_ok=True)

    cargar_valores_referencia = _resolver_cargar_valores_referencia(backend)

    return {
        "BASE_ROOT": str(base_root_path),
        "BASE_ROOT_PATH": base_root_path,

        "correr_todo": getattr(backend, "correr_todo"),
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": getattr(backend, "listar_carpetas_mes"),

        # ✅ SIEMPRE disponible (ya no te va a reventar app.py)
        "cargar_valores_referencia": cargar_valores_referencia,

        # opcional para debug
        "backend_module": backend,
    }






