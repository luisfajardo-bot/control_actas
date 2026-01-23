# control_actas_local.py
from __future__ import annotations

import os
import tempfile
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any

_BACKEND_CACHE: dict[str, Any] = {}  # {"normal": module, "critico": module}


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


def _backend_pkg_dir_for(modo: str) -> Path:
    """
    Retorna la carpeta que contiene el package 'control_actas' del backend:
      control_normal/control_actas
      control_critico/control_actas
    """
    root = Path(__file__).resolve().parent
    base = root / ("control_critico" if modo == "critico" else "control_normal")
    pkg_dir = base / "control_actas"
    return pkg_dir


def _import_backend(modo: str):
    """
    Importa el package del backend como un paquete aislado (nombre único),
    SIN tocar sys.path y SIN purgar sys.modules.

    Esto evita los KeyError raros de Streamlit (import a medias en reruns).
    """
    if modo in _BACKEND_CACHE:
        return _BACKEND_CACHE[modo]

    pkg_dir = _backend_pkg_dir_for(modo)
    init_py = pkg_dir / "__init__.py"

    if not init_py.exists():
        raise FileNotFoundError(f"No existe __init__.py del backend en: {init_py}")

    # Nombre único por modo para evitar colisiones: control_actas__normal / control_actas__critico
    module_name = f"control_actas__{modo}"

    spec = importlib.util.spec_from_file_location(
        module_name,
        str(init_py),
        submodule_search_locations=[str(pkg_dir)],  # clave para que funcionen imports relativos
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"No pude crear spec para backend '{modo}' desde: {init_py}")

    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]

    _BACKEND_CACHE[modo] = mod
    return mod


def resolver_base_root(*, anio_proyecto: Optional[int | str] = None) -> Path:
    """
    Base root del filesystem donde el backend lee/escribe.
    - Cloud: /tmp/control_actas_data (ephemeral, sirve para procesar y luego subir a Drive)
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

    # Intentar exponer cargar_valores_referencia desde el backend aislado
    cargar_valores_referencia = None
    try:
        # Si el __init__.py del backend expone bd_precios como submódulo importado
        bd = getattr(backend, "bd_precios", None)
        if bd is not None:
            cargar_valores_referencia = getattr(bd, "cargar_valores_referencia", None)
    except Exception:
        cargar_valores_referencia = None

    return {
        "BASE_ROOT": str(base_root_path),
        "BASE_ROOT_PATH": base_root_path,
        "correr_todo": getattr(backend, "correr_todo"),
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": getattr(backend, "listar_carpetas_mes"),
        "cargar_valores_referencia": cargar_valores_referencia,
        # (Opcional) por si quieres acceder al módulo completo desde app.py para debug:
        "backend_module": backend,
    }














