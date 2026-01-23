# control_actas_local.py
from __future__ import annotations

import os
import sys
import tempfile
import importlib
from pathlib import Path
from typing import Optional, Dict, Any, Callable


_BACKEND_CACHE: dict[str, Any] = {}  # {"normal": module, "critico": module}


def is_cloud() -> bool:
    """
    Detecta Streamlit Cloud:
    - Preferimos st.secrets (porque ahí suele estar DRIVE_ROOT_FOLDER_ID)
    - Fallback a env vars típicas de Streamlit
    """
    try:
        import streamlit as st
        return "DRIVE_ROOT_FOLDER_ID" in st.secrets
    except Exception:
        pass

    return any(k in os.environ for k in ("STREAMLIT_RUNTIME", "STREAMLIT_SERVER_HEADLESS"))


def _backend_root_for(modo: str) -> Path:
    """
    Retorna la carpeta que debe ir en sys.path para que exista el paquete 'control_actas'.
    Estructura esperada (tu repo):
      control_normal/control_actas/...
      control_critico/control_actas/...
    """
    root = Path(__file__).resolve().parent
    folder = "control_critico" if modo == "critico" else "control_normal"
    return root / folder


def _ensure_sys_path(modo: str) -> Path:
    """
    Asegura que sys.path priorice el backend_root del modo,
    y saque del frente el backend_root del otro modo.
    """
    backend_root = _backend_root_for(modo)
    backend_root_str = str(backend_root)

    other_root = _backend_root_for("critico" if modo == "normal" else "normal")
    other_root_str = str(other_root)

    # Quitar el otro si está antes (o en cualquier parte)
    sys.path = [p for p in sys.path if p != other_root_str]

    # Poner este al inicio
    if backend_root_str in sys.path:
        sys.path.remove(backend_root_str)
    sys.path.insert(0, backend_root_str)

    return backend_root


def _loaded_control_actas_path() -> Optional[Path]:
    """
    Si ya está importado 'control_actas', devuelve el path real del módulo.
    """
    mod = sys.modules.get("control_actas")
    if not mod:
        return None
    f = getattr(mod, "__file__", None)
    if not f:
        return None
    try:
        return Path(f).resolve()
    except Exception:
        return None


def _purge_control_actas_modules():
    """
    Borra 'control_actas' y submódulos de sys.modules.
    IMPORTANTE: solo se usa cuando detectamos que está cargado desde el backend equivocado.
    """
    keys = [k for k in list(sys.modules.keys()) if k == "control_actas" or k.startswith("control_actas.")]
    for k in keys:
        try:
            del sys.modules[k]
        except Exception:
            pass
    importlib.invalidate_caches()


def _import_backend(modo: str):
    """
    Importa el paquete 'control_actas' apuntando al backend correcto (normal/crítico),
    sin inventar nombres.
    """
    if modo in _BACKEND_CACHE:
        return _BACKEND_CACHE[modo]

    backend_root = _ensure_sys_path(modo)
    importlib.invalidate_caches()

    # Si ya está cargado 'control_actas' pero viene del backend equivocado, lo limpiamos.
    loaded_path = _loaded_control_actas_path()
    if loaded_path is not None:
        # Queremos que el __file__ esté dentro de backend_root/control_actas/...
        # Ej: .../control_normal/control_actas/__init__.py
        if backend_root not in loaded_path.parents:
            _purge_control_actas_modules()

    m = importlib.import_module("control_actas")
    _BACKEND_CACHE[modo] = m
    return m


def resolver_base_root(*, anio_proyecto: Optional[int | str] = None) -> Path:
    """
    Base root del filesystem donde el backend lee/escribe.
    - Cloud: /tmp/control_actas_data (temporal)
    - Local: tu ruta real (ajústala si lo necesitas)
    """
    if is_cloud():
        return Path(tempfile.gettempdir()) / "control_actas_data"
    return Path(r"G:\Mi unidad\Subcontratos")


def _resolver_cargar_valores_referencia(backend_module: Any) -> Optional[Callable[[Path], dict]]:
    """
    Intenta obtener cargar_valores_referencia desde el backend importado.
    Si no existe, devuelve None (app.py decide qué hacer).
    """
    # 1) Ideal: control_actas.bd_precios.cargar_valores_referencia
    try:
        bp = getattr(backend_module, "bd_precios", None)
        if bp is not None and hasattr(bp, "cargar_valores_referencia"):
            return bp.cargar_valores_referencia  # type: ignore[attr-defined]
    except Exception:
        pass

    # 2) Import directo desde el paquete activo (ya apuntado por sys.path)
    try:
        from control_actas.bd_precios import cargar_valores_referencia as _cvr  # type: ignore
        return _cvr
    except Exception:
        return None


def get_backend(modo: str, *, anio_proyecto: Optional[int | str] = None) -> Dict[str, Any]:
    """
    Retorna un dict con métodos/constantes que usa el front.
    IMPORTANTE:
    - El paquete siempre se importa como 'control_actas'
    - El modo solo cambia la carpeta que se pone en sys.path (control_normal vs control_critico)
    """
    if modo not in ("normal", "critico"):
        raise ValueError(f"modo inválido: {modo}. Usa 'normal' o 'critico'.")

    backend = _import_backend(modo)

    base_root_path = resolver_base_root(anio_proyecto=anio_proyecto)
    base_root_path.mkdir(parents=True, exist_ok=True)

    cargar_valores_referencia = _resolver_cargar_valores_referencia(backend)

    return {
        "BASE_ROOT": str(base_root_path),
        "BASE_ROOT_PATH": base_root_path,

        "correr_todo": backend.correr_todo,
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": backend.listar_carpetas_mes,

        # Para que app.py NO tenga que importar nada “por fuera” del backend activo
        "cargar_valores_referencia": cargar_valores_referencia,
        "backend_module": backend,  # opcional: útil si quieres acceder a bd_precios, etc.
    }








