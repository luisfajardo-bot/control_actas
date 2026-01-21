from pathlib import Path

# =========================================================
#  RUTAS BASE
# =========================================================
BASE_ROOT = r"G:\Mi unidad\Subcontratos\\"
PROYECTO_DEFAULT = "Grupo 4"

# =========================================================
#  PRECIOS DE REFERENCIA (Drive)
# =========================================================
PRECIOS_ROOT = Path(r"G:\Mi unidad\Subcontratos\precios_referencia")
DEFAULT_PRECIOS_VERSION = "2025"
PRECIOS_DB_FILENAME = "precios_referencia.db"

# Ruta por defecto completa 
DB_PRECIOS_DEFAULT = PRECIOS_ROOT / DEFAULT_PRECIOS_VERSION / PRECIOS_DB_FILENAME

# Actividades críticas (en texto normal, tú las llenas)
ACTIVIDADES_CRITICAS = {
    "EXCAVACION MECANICA": 1000,
    "BASE GRANULAR": 1000,
    "SUBBASE GRANULAR": 1000,
    "ESTABILIZACION DE SUBRASANTE": 4500,
    "ESTABILIZACION CON RAJON": 4500,
    "ESTABILIZACION CON RCD": 4500,
}
