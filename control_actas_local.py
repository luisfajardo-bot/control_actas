# control_actas_local.py
import os
import sys
import importlib
from pathlib import Path
from typing import Optional, Dict, Any

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


def resolver_base_root(anio_proyecto: Optional[int | str] = None) -> str:
    """
    Construye BASE_ROOT final PARA FILESYSTEM.

    - En LOCAL: <ROOT>/<AÑO> (si anio_proyecto viene) o <ROOT>
    - En CLOUD: devuelve una ruta staging en /tmp (NO Drive)
      La app debe descargar actas/Bd desde Drive a este staging si lo necesita.
    """
    root = get_projects_root()
    root.mkdir(parents=True, exist_ok=True)  # asegura staging en cloud

    if anio_proyecto is None or str(anio_proyecto).strip() == "":
        return str(root)

    anio_str = str(anio_proyecto).strip()
    return str(root / anio_str)


# =========================================================
#  IMPORT DINÁMICO DEL BACKEND (NORMAL / CRÍTICO)
# =========================================================
def _import_backend(modo: str):
    """
    Importa el paquete `control_actas` desde el backend correspondiente
    (control_normal/ o control_critico/) de forma segura para Streamlit.
    """
    root = Path(__file__).resolve().parent  # carpeta donde está control_actas_local.py

    if modo == "critico":
        backend_root = root / "control_critico"
    else:
        backend_root = root / "control_normal"

    # 1) asegurar que el backend_root esté primero en sys.path
    backend_root_str = str(backend_root)
    if backend_root_str in sys.path:
        sys.path.remove(backend_root_str)
    sys.path.insert(0, backend_root_str)

    # 2) limpiar importaciones previas (evita KeyError por estado inconsistente)
    #    primero submódulos, luego el paquete
    to_remove = [k for k in list(sys.modules.keys()) if k == "control_actas" or k.startswith("control_actas.")]
    to_remove.sort(key=len, reverse=True)
    for k in to_remove:
        sys.modules.pop(k, None)

    importlib.invalidate_caches()

    # 3) importar fresco
    return importlib.import_module("control_actas")


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





