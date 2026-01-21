# control_actas_local.py
import os
import sys
import importlib
from pathlib import Path

# =========================================================
#  RUTAS BASE
# =========================================================
BASE_ROOT = r"G:\Mi unidad\Subcontratos\\"
PROYECTO_DEFAULT = "Grupo 4"

# Carpeta del repo/proyecto (donde está este archivo)
PROJECT_DIR = Path(__file__).resolve().parent

# Backends
BACKEND_CRITICO = PROJECT_DIR / "control_critico"
BACKEND_NORMAL  = PROJECT_DIR / "control_normal"


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
    #    para evitar que se quede cargado el otro backend
    for name in list(sys.modules.keys()):
        if name == "control_actas" or name.startswith("control_actas."):
            del sys.modules[name]

    importlib.invalidate_caches()

    # 3) Importar el paquete desde el sys.path actual
    backend = importlib.import_module("control_actas")
    return backend


def get_backend(modo: str):
    """
    Retorna un objeto "backend" con los métodos/constantes que usa el front.
    """
    backend = _import_backend(modo)

    # Exponemos exactamente lo que tu app usa
    return {
        "BASE_ROOT": getattr(backend, "BASE_ROOT", BASE_ROOT),
        "PROYECTO_DEFAULT": getattr(backend, "PROYECTO_DEFAULT", PROYECTO_DEFAULT),
        "correr_todo": backend.correr_todo,
        "correr_todos_los_meses": getattr(backend, "correr_todos_los_meses", None),
        "listar_carpetas_mes": backend.listar_carpetas_mes,
    }
