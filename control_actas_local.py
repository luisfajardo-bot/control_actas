# control_actas_local.py
from __future__ import annotations

import sys
import tempfile
import importlib
from pathlib import Path
from typing import Optional, Dict, Any

_BACKEND_CACHE = {}  # {"normal": module, "critico": module}

def is_cloud() -> bool:
    try:
        import streamlit as st
        return "DRIVE_ROOT_FOLDER_ID" in st.secrets
    except Exception:
        return False

def _set_backend_path(modo: str) -> str:
    root = Path(__file__).resolve().parent
    backend_root = root / ("control_critico" if modo == "critico" else "control_normal")
    backend_root_str = str(backend_root)

    if backend_root_str in sys.path:
        sys.path.remove(backend_root_str)
    sys.path.insert(0, backend_root_str)

    return backend_root_str

def _import_backend(modo: str):
    if modo in _BACKEND_CACHE:
        return _BACKEND_CACHE[modo]

    _set_backend_path(modo)

    # Importa sin “limpiar” agresivamente: primera vez por modo
    m = importlib.import_module("control_actas")
    _BACKEND_CACHE[modo] = m
    return m

def resolver_base_root(*, anio_proyecto: Optional[int | str] = None) -> Path:
    if is_cloud():
        return Path(tempfile.gettempdir()) / "control_actas_data"
    return Path(r"G:\Mi unidad\Subcontratos")

def get_backend(modo: str, *, anio_proyecto: Optional[int | str] = None) -> Dict[str, Any]:
    backend = _import_backend(modo)
    base_root = resolver_base_root(anio_proyecto=anio_proyecto)

    return {
        "BASE_ROOT": str(base_root),
        "correr_todo": backend.correr_todo,
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": backend.listar_carpetas_mes,
    }










