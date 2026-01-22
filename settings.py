# settings.py
import os

IS_CLOUD = "STREAMLIT_RUNTIME" in os.environ

PROYECTOS = ["Grupo 3", "Grupo 4", "WF1-WF2", "WF5", "Corredor Verde", "Tintal", "Caracas Sur", "Cambao"]
MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]

DEFAULT_ANIO_PROY = 2026
DEFAULT_PRECIOS_VERSION = "2025"

DRIVE_PRECIOS_FOLDER_NAME = "precios_referencia"
DB_FILENAME = "precios_referencia.db"
