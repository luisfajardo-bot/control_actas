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

# Defaults (puedes cambiarlos fácil)
PROYECTO_DEFAULT = "Grupo 4"

# ⚠️ Local: tu Drive montado (ajústalo aquí y solo aquí)
DEFAULT_PROYECTOS_ROOT_LOCAL = Path(r"G:\Mi unidad\Subcontratos")

# Cloud / CI: si defines una variable de entorno, se usa.
# Ejemplo en Streamlit Cloud: PROJECTS_ROOT=/mount/data  (o lo que uses)
ENV_PROJECTS_ROOT = "PROJECTS_ROOT"


def get_projects_root() -> Path:
    """
    Devuelve la raíz de proyectos.
    Prioridad:
      1) Variable de entorno PROJECTS_ROOT (ideal para Cloud)
      2) Ruta local por defecto (Drive montado en Windows)
    """
    env = os.environ.get(ENV_PROJECTS_ROOT, "").strip()
    if env:
        return Path(env)
    return DEFAULT_PROYECTOS_ROOT_LOCAL


def resolver_base_root(anio_proyecto: Optional[int | str] = None) -> str:
    """
    Construye BASE_ROOT final para el proyecto.

    Si tu estructura tiene año como carpeta:
        <ROOT>/<AÑO>/<PROYECTO>/control_actas/...
    entonces anio_proyecto debe venir (ej: 2026) y esto retorna:
        <ROOT>/<AÑO>

    Si tu estructura NO usa año como carpeta, pasa anio_proyecto=None
    y retorna solo <ROOT>.
    """
    root = get_projects_root()

    if anio_proyecto is None or str(anio_proyecto).strip() == "":
        return str(root)

    # Si el "año" viene como número o string, lo normalizamos
    anio_str = str(anio_proyecto).strip()
    return str(root / anio_str)


# =========================================================
#  IMPORT DINÁMICO DEL BACKEND (NORMAL / CRÍTICO)
# =========================================================
def _import_backend(modo: str):
    """
    Importa el paquete `control_actas` desde:
      - control_critico/control_actas (modo critico)
      - control_normal/control_actas  (modo normal)

    Nota: ambos paquetes se llaman igual (control_actas), por eso
    manipulamos sys.path e invalidamos cachés de import.
    """
    modo = (modo or "").strip().lower()
    if modo not in ("critico", "normal"):
        raise ValueError("modo debe ser 'critico' o 'normal'")

    backend_root = BACKEND_CRITICO if modo == "critico" else BACKEND_NORMAL
    if not backend_root.exists():
        raise FileNotFoundError(f"No existe backend: {backend_root}")

    # 1) Poner el backend seleccionado primero en sys.path
    backend_root_str = str(backend_root)
    if backend_root_str in sys.path:
        sys.path.remove(backend_root_str)
    sys.path.insert(0, backend_root_str)

    # 2) Borrar el módulo `control_actas` y sus submódulos del cache
    for name in list(sys.modules.keys()):
        if name == "control_actas" or name.startswith("control_actas."):
            del sys.modules[name]

    importlib.invalidate_caches()

    # 3) Importar el paquete desde el sys.path actual
    backend = importlib.import_module("control_actas")
    return backend


def get_backend(modo: str, *, anio_proyecto: Optional[int | str] = None) -> Dict[str, Any]:
    """
    Retorna un objeto "backend" con los métodos/constantes que usa el front,
    y además entrega un BASE_ROOT ya resuelto según el año del proyecto.

    Uso recomendado desde app.py:
        backend = get_backend(modo_backend, anio_proyecto=anio_proyecto)
        BASE_ROOT = backend["BASE_ROOT"]
    """
    backend = _import_backend(modo)

    # BASE_ROOT centralizado (no dependemos de lo hardcodeado en config.py)
    base_root = resolver_base_root(anio_proyecto=anio_proyecto)

    return {
        "BASE_ROOT": base_root,
        "PROYECTO_DEFAULT": getattr(backend, "PROYECTO_DEFAULT", PROYECTO_DEFAULT),
        "correr_todo": backend.correr_todo,
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": backend.listar_carpetas_mes,
        # útil para debug en UI:
        "PROJECTS_ROOT": str(get_projects_root()),
    }


