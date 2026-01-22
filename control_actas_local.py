# control_actas_local.py
import os
import sys
import importlib
from pathlib import Path
from typing import Optional, Dict, Any
from __future__ import annotations
import importlib.util




# =========================================================
#  CONFIG CENTRALIZADA DE RUTAS (LOCAL / CLOUD)
# =========================================================
PROJECT_DIR = Path(__file__).resolve().parent

# Backends (carpetas dentro del repo)
BACKEND_CRITICO = PROJECT_DIR / "control_critico"
BACKEND_NORMAL  = PROJECT_DIR / "control_normal"

# Defaults
PROYECTO_DEFAULT = "Grupo 4"

# LOCAL: tu Drive montado
DEFAULT_PROYECTOS_ROOT_LOCAL = Path(r"G:\Mi unidad\Subcontratos")

# Cloud / CI: si defines una variable, se usa para FS staging (no Drive)
ENV_PROJECTS_ROOT = "PROJECTS_ROOT"


def is_cloud() -> bool:
    """
    Heurística estable para Streamlit Community Cloud.
    """
    return "STREAMLIT_RUNTIME" in os.environ or "STREAMLIT_SERVER_HEADLESS" in os.environ


def get_projects_root() -> Path:
    """
    Raíz de proyectos SOLO para filesystem (LOCAL o staging).
    Prioridad:
      1) ENV PROJECTS_ROOT (si existe)
      2) En Cloud: /tmp/control_actas_data (staging temporal)
      3) En Local: tu Drive montado (G:)
    """
    env = os.environ.get(ENV_PROJECTS_ROOT, "").strip()
    if env:
        return Path(env)

    if is_cloud():
        # staging temporal para descargas/outputs si se requiere
        return Path("/tmp/control_actas_data")

    return DEFAULT_PROYECTOS_ROOT_LOCAL


def resolver_base_root(*, anio_proyecto=None) -> Path:
    # Cloud: todo vive en /tmp
    try:
        import streamlit as st
        is_cloud = "DRIVE_ROOT_FOLDER_ID" in st.secrets
    except Exception:
        is_cloud = False

    if is_cloud:
        return Path(tempfile.gettempdir()) / "control_actas_data"

    # Local Windows (tu caso real)
    return Path(r"G:\Mi unidad\Subcontratos")


# =========================================================
#  IMPORT DINÁMICO DEL BACKEND (NORMAL / CRÍTICO)
# =========================================================
def _import_backend(modo: str):
    """
    Carga el paquete control_actas desde control_normal/ o control_critico/
    usando un NOMBRE ÚNICO para evitar colisiones con hot-reload de Streamlit.
    """
    root = Path(__file__).resolve().parent

    backend_root = root / ("control_critico" if modo == "critico" else "control_normal")
    pkg_dir = backend_root / "control_actas"
    init_py = pkg_dir / "__init__.py"

    if not init_py.exists():
        raise FileNotFoundError(f"No existe {init_py}")

    # Nombre único del paquete según modo
    pkg_name = "control_actas_critico" if modo == "critico" else "control_actas_normal"

    # Limpia SOLO lo de este alias (no toca 'control_actas' global)
    for k in list(sys.modules.keys()):
        if k == pkg_name or k.startswith(pkg_name + "."):
            sys.modules.pop(k, None)

    # Crea spec de paquete (clave: submodule_search_locations)
    spec = importlib.util.spec_from_file_location(
        pkg_name,
        init_py,
        submodule_search_locations=[str(pkg_dir)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo crear spec para {pkg_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = module
    spec.loader.exec_module(module)

    return module


def get_backend(modo: str, *, anio_proyecto: Optional[int | str] = None) -> Dict[str, Any]:
    """
    Retorna métodos/constantes que usa el front.
    BASE_ROOT aquí es SOLO para filesystem (local o staging).
    """
    backend = _import_backend(modo)

    base_root = resolver_base_root(anio_proyecto=anio_proyecto)

    return {
        "BASE_ROOT": base_root,
        "PROYECTO_DEFAULT": getattr(backend, "PROYECTO_DEFAULT", PROYECTO_DEFAULT),
        "correr_todo": backend.correr_todo,
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": backend.listar_carpetas_mes,
        "PROJECTS_ROOT": str(get_projects_root()),
        "IS_CLOUD": is_cloud(),
    }







