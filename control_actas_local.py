# control_actas_local.py
from __future__ import annotations

import os
import sys
import tempfile
import importlib
from pathlib import Path
from typing import Optional, Dict, Any

_BACKEND_CACHE: dict[str, Any] = {}   # {"normal": module, "critico": module}
_BACKEND_PATHS: dict[str, str] = {}  # {"normal": ".../control_normal", "critico": ".../control_critico"}


def is_cloud() -> bool:
    """
    Detecta si estás en Streamlit Cloud.
    Preferimos st.secrets (porque ahí tienes DRIVE_ROOT_FOLDER_ID), y fallback por envs.
    """
    try:
        import streamlit as st
        return "DRIVE_ROOT_FOLDER_ID" in st.secrets
    except Exception:
        pass

    return any(k in os.environ for k in ("STREAMLIT_RUNTIME", "STREAMLIT_SERVER_HEADLESS"))


def _backend_root_for(modo: str) -> Path:
    root = Path(__file__).resolve().parent
    folder = "control_critico" if modo == "critico" else "control_normal"
    return root / folder


def _set_backend_path(modo: str) -> str:
    """
    Inserta en sys.path la carpeta que contiene el package 'control_actas'
    para el modo seleccionado (normal o critico).
    """
    backend_root = _backend_root_for(modo)
    backend_root_str = str(backend_root)

    # Saca el path del modo contrario si está
    for other_modo, other_path in list(_BACKEND_PATHS.items()):
        if other_modo != modo and other_path in sys.path:
            sys.path.remove(other_path)

    # Reinsertar este path al inicio
    if backend_root_str in sys.path:
        sys.path.remove(backend_root_str)
    sys.path.insert(0, backend_root_str)

    _BACKEND_PATHS[modo] = backend_root_str
    return backend_root_str


def _purge_control_actas_modules():
    """
    Limpia módulos cargados de 'control_actas' y submódulos.
    Esto evita choques cuando cambias entre backends (normal/critico) en caliente.
    """
    to_delete = [k for k in sys.modules.keys() if k == "control_actas" or k.startswith("control_actas.")]
    for k in to_delete:
        try:
            del sys.modules[k]
        except Exception:
            pass
    importlib.invalidate_caches()


def _import_backend(modo: str):
    """
    Importa el package 'control_actas' desde la ruta del backend correspondiente.
    Cachea por modo.
    """
    if modo in _BACKEND_CACHE:
        return _BACKEND_CACHE[modo]

    _set_backend_path(modo)

    # Import “fresco” para evitar KeyError / mezclas de módulos entre modos
    _purge_control_actas_modules()

    m = importlib.import_module("control_actas")
    _BACKEND_CACHE[modo] = m
    return m


def resolver_base_root(*, anio_proyecto: Optional[int | str] = None) -> Path:
    """
    Base root del filesystem donde el backend lee/escribe.
    - Cloud: /tmp/control_actas_data (ephemeral, pero sirve para procesar y luego subir a Drive)
    - Local: tu ruta real.
    """
    if is_cloud():
        return Path(tempfile.gettempdir()) / "control_actas_data"
    return Path(r"G:\Mi unidad\Subcontratos")


def get_backend(modo: str, *, anio_proyecto: Optional[int | str] = None) -> Dict[str, Any]:
    """
    Retorna un dict con métodos/constantes que usa el front.
    OJO: BASE_ROOT es filesystem local/staging (NO es Drive).
    """
    if modo not in ("normal", "critico"):
        raise ValueError(f"modo inválido: {modo}. Usa 'normal' o 'critico'.")

    backend = _import_backend(modo)
    base_root_path = resolver_base_root(anio_proyecto=anio_proyecto)
    base_root_path.mkdir(parents=True, exist_ok=True)

    # Exponer función de BD precios desde el backend importado (evita imports globales en Cloud)
    cargar_valores_referencia = None
    try:
        # Lo usual: control_actas.bd_precios.cargar_valores_referencia
        cargar_valores_referencia = backend.bd_precios.cargar_valores_referencia  # type: ignore[attr-defined]
    except Exception:
        try:
            from control_actas.bd_precios import cargar_valores_referencia as _cvr  # type: ignore
            cargar_valores_referencia = _cvr
        except Exception:
            cargar_valores_referencia = None

    return {
        "BASE_ROOT": str(base_root_path),
        "BASE_ROOT_PATH": base_root_path,

        "correr_todo": backend.correr_todo,
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": backend.listar_carpetas_mes,

        # Para que app.py NO tenga que importar 'control_actas' globalmente
        "cargar_valores_referencia": cargar_valores_referencia,
    }










