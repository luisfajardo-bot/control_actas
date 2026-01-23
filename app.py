import os
import tempfile
import zipfile
import shutil
from pathlib import Path

import streamlit as st
import pandas as pd

from control_actas_local import get_backend


# ==================================================
# Drive utils (import robusto: raíz o utils/)
# ==================================================
try:
    from utils.drive_utils import (
        get_drive_service,
        list_folders,
        find_child_folder,
        find_file,
        download_file,
        upload_or_update_file,
    )
except Exception:
    from drive_utils import (
        get_drive_service,
        list_folders,
        find_child_folder,
        find_file,
        download_file,
        upload_or_update_file,
    )


# ==================================================
# Helpers Drive
# ==================================================
def list_files_in_folder(service, folder_id: str):
    """
    Lista archivos dentro de un folder de Drive.
    Retorna items con keys: id, name, mimeType.
    """
    q = f"'{folder_id}' in parents and trashed=false"
    fields = "nextPageToken, files(id,name,mimeType)"
    out = []
    page_token = None

    while True:
        resp = service.files().list(
            q=q,
            fields=fields,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        out.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return out


def get_or_create_folder(service, parent_id: str, name: str) -> str:
    fid = find_child_folder(service, parent_id, name)
    if fid:
        return fid
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    created = service.files().create(body=meta, fields="id").execute()
    return created["id"]


def sync_actas_mes_desde_drive(
    service,
    root_id: str,
    base_root: Path,
    proyecto: str,
    nombre_carpeta_mes: str,
    anio: int,
):
    """
    Descarga a filesystem local (Cloud) los .xlsx del mes para que el backend los vea.

    MUY IMPORTANTE:
    - El backend (pipeline_mes.py) arma carpeta_mes como:
      base_root / proyecto / control_actas / actas / nombre_carpeta_mes
    - Por eso descargamos EXACTO ahí (SIN meter /anio/ en local).
    """
    # Estructura objetivo local (la que tu backend espera)
    local_mes = base_root / proyecto / "control_actas" / "actas" / nombre_carpeta_mes
    local_mes.mkdir(parents=True, exist_ok=True)

    def _ls_names(folder_id: str) -> list[str]:
        try:
            childs = list_folders(service, folder_id)
        except TypeError:
            childs = list_folders(service, folder_id, mime_type="application/vnd.google-apps.folder")
        return [c.get("name", "") for c in (childs or [])]

    def _find_path(path_names: list[str]) -> str | None:
        cur = root_id
        for name in path_names:
            nxt = find_child_folder(service, cur, name)
            if not nxt:
                return None
            cur = nxt
        return cur

    # Tu ROOT YA contiene: Grupo 3, Grupo 4, precios_referencia, etc.
    candidates = [
        # ROOT / Grupo 3 / control_actas / actas / octubre2025
        [proyecto, "control_actas", "actas", nombre_carpeta_mes],

        # Variantes por si alguien guardó el año en medio (por si acaso)
        [proyecto, "control_actas", "actas", str(anio), nombre_carpeta_mes],
        [proyecto, str(anio), "control_actas", "actas", nombre_carpeta_mes],
    ]

    mes_id = None
    last_fail = None
    for path_names in candidates:
        try_id = _find_path(path_names)
        if try_id:
            mes_id = try_id
            break
        last_fail = path_names

    if not mes_id:
        root_folders = _ls_names(root_id)
        raise FileNotFoundError(
            "No pude ubicar la carpeta del mes en Drive.\n\n"
            f"Ruta intentada (último intento): {' / '.join(last_fail or [])}\n\n"
            "Carpetas visibles en DRIVE_ROOT_FOLDER_ID:\n- "
            + "\n- ".join(root_folders[:80])
        )

    # Listar archivos del mes y descargar xlsx
    items = list_files_in_folder(service, mes_id)

    descargados = 0
    for it in items:
        name = (it.get("name") or "")
        if name.lower().endswith(".xlsx"):
            download_file(service, it["id"], local_mes / name)
            descargados += 1

    return local_mes, descargados


def exportar_resultados_a_drive(service, root_id: str, proyecto: str, nombre_carpeta_mes: str, info: dict):
    """
    Sube outputs a Drive con esta estructura:
    ROOT / {proyecto} / control_actas / salidas / {mes}
    ROOT / {proyecto} / control_actas / resumen / {mes}
    ROOT / {proyecto} / control_actas / datos / base_general.xlsx
    ROOT / {proyecto} / control_actas / resumen / resumen_global.xlsx
    """
    proyecto_id = get_or_create_folder(service, root_id, proyecto)
    ca_id = get_or_create_folder(service, proyecto_id, "control_actas")

    salidas_id = get_or_create_folder(service, ca_id, "salidas")
    resumen_id = get_or_create_folder(service, ca_id, "resumen")
    datos_id = get_or_create_folder(service, ca_id, "datos")

    salidas_mes_id = get_or_create_folder(service, salidas_id, nombre_carpeta_mes)
    resumen_mes_id = get_or_create_folder(service, resumen_id, nombre_carpeta_mes)

    mime_xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Salidas del mes
    for p in Path(info["carpeta_salida_mes"]).glob("*.xlsx"):
        upload_or_update_file(service, salidas_mes_id, p, mime_xlsx)

    # Resumen del mes
    for p in Path(info["carpeta_resumen_mes"]).glob("*.xlsx"):
        upload_or_update_file(service, resumen_mes_id, p, mime_xlsx)

    # Base general
    base_general = Path(info["carpeta_datos"]) / "base_general.xlsx"
    if base_general.exists():
        upload_or_update_file(service, datos_id, base_general, mime_xlsx)

    # Resumen global
    resumen_global = Path(info["carpeta_resumen"]) / "resumen_global.xlsx"
    if resumen_global.exists():
        upload_or_update_file(service, resumen_id, resumen_global, mime_xlsx)


# ==================================================
# Helpers UI
# ==================================================
def formatear_numeros_df(df: pd.DataFrame) -> pd.DataFrame:
    """Miles + 2 decimales para columnas numéricas (sin modificar original)."""
    df_fmt = df.copy()
    for col in df_fmt.columns:
        if pd.api.types.is_numeric_dtype(df_fmt[col]):
            df_fmt[col] = df_fmt[col].apply(lambda x: f"{x:,.2f}" if pd.notnull(x) else x)
    return df_fmt


def _init_state():
    if "vista" not in st.session_state:
        st.session_state["vista"] = None  # None | "OFICINA" | "SUBCONTRATOS"
    if "oficina_ok" not in st.session_state:
        st.session_state["oficina_ok"] = False
    if "local_inputs_dir" not in st.session_state:
        st.session_state["local_inputs_dir"] = None  # Path str
    if "local_inputs_label" not in st.session_state:
        st.session_state["local_inputs_label"] = None


def _reset_local_inputs():
    p = st.session_state.get("local_inputs_dir")
    if p and os.path.exists(p):
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass
    st.session_state["local_inputs_dir"] = None
    st.session_state["local_inputs_label"] = None


def vista_selector():
    """Pantalla inicial + control simple de acceso para OFICINA."""
    _init_state()

    st.title("Control de Actas - ICEIN")
    st.caption("Selecciona tu vista de trabajo 👇")

    c1, c2 = st.columns(2)

    with c1:
        st.subheader("🏢 OFICINA")
        st.write("- Uso de carpetas compartidas para evaluación de pagos realizados.")
        st.write("- Requiere clave para entrar a modo de edición")
        if st.button("Entrar a OFICINA"):
            st.session_state["vista"] = "OFICINA"

    with c2:
        st.subheader("🧰 Ingenieros de Subcontratos")
        st.write("- Procesa archivos subidos (.zip / .xlsx).")
        if st.button("Entrar a Subcontratos"):
            st.session_state["vista"] = "SUBCONTRATOS"
            st.session_state["oficina_ok"] = False

    if st.session_state["vista"] is None:
        st.stop()

    # Gate para OFICINA
    if st.session_state["vista"] == "OFICINA" and not st.session_state["oficina_ok"]:
        st.markdown("---")
        st.subheader("🔐 Acceso OFICINA")

        clave = st.text_input("Palabra clave", type="password")
        oficina_key = st.secrets["OFICINA_KEY"] if "OFICINA_KEY" in st.secrets else None

        if st.button("Validar"):
            if oficina_key is None:
                st.error("No se encontró OFICINA_KEY en Secrets de Streamlit Cloud.")
                st.stop()

            if (clave or "").strip() == str(oficina_key).strip():
                st.session_state["oficina_ok"] = True
                st.success("Acceso concedido ✅")
                st.rerun()
            else:
                st.error("Clave incorrecta ❌")
                st.stop()

        if st.session_state["vista"] == "OFICINA" and not st.session_state["oficina_ok"]:
            st.stop()


def render_subcontratos_uploader():
    """UI de carga local para la vista SUBCONTRATOS."""
    st.markdown("## 🧰 Subcontratos: carga local")
    st.caption("Sube un .zip con actas o un .xlsx individual. Se guardan temporalmente para procesar local.")

    col1, col2 = st.columns([2, 1])

    with col1:
        up = st.file_uploader("Subir archivo", type=["zip", "xlsx"], accept_multiple_files=False)

    with col2:
        if st.button("🧹 Limpiar carga"):
            _reset_local_inputs()
            st.info("Carga local limpiada.")

    if up is None:
        if st.session_state.get("local_inputs_dir"):
            st.success(f"Carga activa: `{st.session_state['local_inputs_label']}`")
            st.caption(f"Ruta temporal: `{st.session_state['local_inputs_dir']}`")
        return

    _reset_local_inputs()
    tmp_dir = Path(tempfile.mkdtemp(prefix="actas_local_"))

    name = up.name.lower()
    target_label = up.name

    if name.endswith(".zip"):
        zip_path = tmp_dir / up.name
        zip_path.write_bytes(up.getbuffer())

        extract_dir = tmp_dir / "extraido"
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        st.session_state["local_inputs_dir"] = str(extract_dir)
        st.session_state["local_inputs_label"] = target_label
        st.success("ZIP cargado y extraído ✅")
        st.caption(f"Archivos extraídos en: `{extract_dir}`")

    elif name.endswith(".xlsx"):
        xlsx_dir = tmp_dir / "xlsx"
        xlsx_dir.mkdir(parents=True, exist_ok=True)
        xlsx_path = xlsx_dir / up.name
        xlsx_path.write_bytes(up.getbuffer())

        st.session_state["local_inputs_dir"] = str(xlsx_dir)
        st.session_state["local_inputs_label"] = target_label
        st.success("XLSX cargado ✅")
        st.caption(f"Archivo guardado en: `{xlsx_path}`")


# ==================================================
# Entorno
# ==================================================
def detectar_cloud() -> bool:
    try:
        return "DRIVE_ROOT_FOLDER_ID" in st.secrets
    except Exception:
        return False


IS_CLOUD = detectar_cloud()


# ==================================================
# Configuración básica de la página
# ==================================================
st.set_page_config(
    page_title="Control de Actas de Obra- ICEIN 🤓",
    page_icon="📑",
    layout="wide",
)


# ==================================================
# Selector de vista (ANTES de todo lo demás)
# ==================================================
vista_selector()
VISTA = st.session_state["vista"]  # "OFICINA" | "SUBCONTRATOS"


# ==================================================
# TEMA (OSCURO / CLARO)
# ==================================================
THEMES = {
    "OSCURO": {
        "bg": "#0b1220",
        "panel": "#111827",
        "card": "#0f172a",
        "text": "#e5e7eb",
        "muted": "#9ca3af",
        "primary": "#22c55e",
        "border": "#243041",
        "button_text": "#0b1220",
    },
    "CLARO": {
        "bg": "#f6f7fb",
        "panel": "#ffffff",
        "card": "#ffffff",
        "text": "#111827",
        "muted": "#4b5563",
        "primary": "#16a34a",
        "border": "#e5e7eb",
        "button_text": "#ffffff",
    },
}

if "Tema" not in st.session_state:
    st.session_state.Tema = "OSCURO"

Tema = st.sidebar.selectbox(
    "Tema",
    ["OSCURO", "CLARO"],
    index=["OSCURO", "CLARO"].index(st.session_state.Tema),
)
st.session_state.Tema = Tema
C = THEMES[Tema]

st.markdown(
    f"""
<style>
:root {{
  --bg: {C["bg"]};
  --panel: {C["panel"]};
  --card: {C["card"]};
  --text: {C["text"]};
  --muted: {C["muted"]};
  --primary: {C["primary"]};
  --border: {C["border"]};
  --button_text: {C["button_text"]};
}}
.stApp {{
  background: var(--bg) !important;
  color: var(--text) !important;
}}
section[data-testid="stSidebar"] {{
  background: var(--panel) !important;
  border-right: 1px solid var(--border) !important;
}}
section[data-testid="stSidebar"] * {{
  color: var(--text) !important;
}}
h1, h2, h3, h4, p, span, div, label {{
  color: var(--text) !important;
}}
small, .stCaption, [data-testid="stCaptionContainer"] {{
  color: var(--muted) !important;
}}
hr {{
  border-color: var(--border) !important;
}}
/* botones */
.stButton > button {{
  background: var(--primary) !important;
  color: var(--button_text) !important;
  border: 1px solid var(--primary) !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
  padding: 0.6rem 1rem !important;
}}
.stButton > button:disabled {{
  opacity: 0.55 !important;
  background: var(--card) !important;
  color: var(--muted) !important;
  border: 1px solid var(--border) !important;
}}
a[data-testid="stLinkButton"] {{
  background: var(--primary) !important;
  color: var(--button_text) !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
  border: 1px solid var(--primary) !important;
  padding: 0.6rem 1rem !important;
  text-decoration: none !important;
}}
</style>
""",
    unsafe_allow_html=True,
)


# ==================================================
# Constantes UI
# ==================================================
PROYECTOS = ["Grupo 3", "Grupo 4", "WF1-WF2", "WF5", "Corredor Verde", "Tintal", "Caracas Sur", "Cambao"]

LOOKER_LINKS = {
    "Grupo 3": "https://lookerstudio.google.com/s/o8k6-5wq7f8",
    "Grupo 4": "https://lookerstudio.google.com/s/iZMSjwAUvmQ",
    "WF1-WF2": "https://lookerstudio.google.com/reporting/WF1WF2XXXX",
    "WF5": "https://lookerstudio.google.com/reporting/WF5XXXX",
    "Corredor Verde": "https://lookerstudio.google.com/reporting/CORREDORXXXX",
}

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


# ==================================================
# Sidebar filtros
# ==================================================
st.sidebar.title("Filtros")
st.sidebar.markdown(f"**Vista activa:** `{VISTA}`")
st.sidebar.markdown("---")

if st.sidebar.button("↩ Cambiar vista"):
    st.session_state["vista"] = None
    st.session_state["oficina_ok"] = False
    st.rerun()

modo_critico = st.sidebar.toggle("🔥 Modo crítico (solo actividades sensibles)", value=False)
modo_backend = "critico" if modo_critico else "normal"

proyecto = st.sidebar.selectbox("Proyecto", PROYECTOS)

ANIOS_FALLBACK = list(range(2025, 2035))
anio_proyecto = st.sidebar.selectbox(
    "Año (Proyecto / Actas / Salidas)",
    ANIOS_FALLBACK,
    index=ANIOS_FALLBACK.index(st.session_state.get("anio_proyecto", 2026))
    if st.session_state.get("anio_proyecto", 2026) in ANIOS_FALLBACK else 0,
)
st.session_state["anio_proyecto"] = anio_proyecto

mes = st.sidebar.selectbox("Mes", MESES)
nombre_carpeta_mes = f"{mes}{anio_proyecto}"

st.sidebar.markdown("---")
if not modo_critico:
    VERSIONES_FALLBACK = ["2024", "2025", "2026"]
    precios_version = st.sidebar.selectbox(
        "Base de precios (versión/año)",
        VERSIONES_FALLBACK,
        index=VERSIONES_FALLBACK.index(st.session_state.get("precios_version", "2025"))
        if st.session_state.get("precios_version", "2025") in VERSIONES_FALLBACK else 1,
    )
    st.session_state["precios_version"] = precios_version
else:
    precios_version = st.session_state.get("precios_version", "2025")
    st.session_state["precios_version"] = precios_version

st.sidebar.markdown("---")
procesar_btn = st.sidebar.button("🚀 Procesar actas")


# ==================================================
# Backend (ya con anio_proyecto definido)
# ==================================================
backend = get_backend(modo_backend, anio_proyecto=anio_proyecto)
BASE_ROOT = backend["BASE_ROOT"]
correr_todo = backend["correr_todo"]
correr_todos_los_meses = backend.get("correr_todos_los_meses")
listar_carpetas_mes = backend["listar_carpetas_mes"]


# ==================================================
# Header
# ==================================================
st.title("Control de Actas - ICEIN")
st.caption("Revisión automática de valores unitarios de cada actividad por proyecto, mes y año.")

st.markdown(
    f"### Proyecto seleccionado: **{proyecto}**  \n"
    f"Periodo: **{mes.capitalize()} {anio_proyecto}**  \n"
    f"Carpeta: `{nombre_carpeta_mes}`  \n"
    f"Base de precios: **{precios_version}**"
)

if VISTA == "SUBCONTRATOS":
    render_subcontratos_uploader()
    st.info("🧩 Nota: la carga ya queda lista en `st.session_state['local_inputs_dir']`.")


# ==================================================
# Carga BD precios (NORMAL)
# ==================================================
valores_referencia = {}
db_path = None
st.session_state["db_precios_path"] = None

if not modo_critico:
    # Importa desde el backend ACTIVO (normal/crítico) usando import relativo ya resuelto por get_backend.
    # En cloud, 'control_actas' puede NO ser un paquete global, por eso importamos del backend devuelto:
    try:
        cargar_valores_referencia = backend["cargar_valores_referencia"]
    except Exception:
        cargar_valores_referencia = None

    try:
        if IS_CLOUD:
            service = get_drive_service()
            root_id = st.secrets["DRIVE_ROOT_FOLDER_ID"]

            precios_root_id = find_child_folder(service, root_id, "precios_referencia")
            if not precios_root_id:
                raise FileNotFoundError("No existe carpeta 'precios_referencia' en Drive.")

            version_folder_id = find_child_folder(service, precios_root_id, str(precios_version))
            if not version_folder_id:
                raise FileNotFoundError(f"No existe carpeta de versión '{precios_version}' en Drive.")

            file_id = find_file(service, version_folder_id, "precios_referencia.db")
            if not file_id:
                raise FileNotFoundError("No se encontró 'precios_referencia.db' en esa versión.")

            tmp_dir = Path(tempfile.gettempdir())
            db_path = tmp_dir / f"precios_referencia_{precios_version}.db"
            download_file(service, file_id, db_path)

        else:
            precios_root_env = os.environ.get("PRECIOS_ROOT", "").strip()
            if precios_root_env:
                precios_root = Path(precios_root_env)
            else:
                precios_root = Path(r"G:\Mi unidad\Subcontratos\precios_referencia")

            db_path = precios_root / str(precios_version) / "precios_referencia.db"

        if cargar_valores_referencia is None:
            raise ImportError("No pude obtener 'cargar_valores_referencia' desde el backend activo.")

        valores_referencia = cargar_valores_referencia(Path(db_path))
        st.session_state["db_precios_path"] = str(db_path)

    except FileNotFoundError as e:
        st.warning("⚠️ No se encontró la base de precios en el entorno actual. Se continúa sin precios de referencia.")
        st.caption(str(e))
        valores_referencia = {}
        st.session_state["db_precios_path"] = None

    except Exception as e:
        st.error("Error cargando la base de precios.")
        st.exception(e)
        valores_referencia = {}
        st.session_state["db_precios_path"] = None


# ==================================================
# Tabs
# ==================================================
tab_run, tab_resumen, tab_informes, tab_based = st.tabs(
    ["▶ Ejecutar proceso", "📊 Ver resúmenes", "📒📋 Ver informes", "🧾 Bases de precios"]
)


# ==================================================
# TAB 1: ejecutar proceso
# ==================================================
with tab_run:
    st.subheader("Ejecución")

    if procesar_btn:
        # Si estás en CLOUD+OFICINA, baja las actas del mes antes de correr
        if IS_CLOUD and VISTA == "OFICINA":
            try:
                service = get_drive_service()
                root_id = st.secrets["DRIVE_ROOT_FOLDER_ID"]
                local_mes, n = sync_actas_mes_desde_drive(
                    service, root_id, Path(BASE_ROOT), proyecto, nombre_carpeta_mes, anio_proyecto
                )
                st.caption(f"☁️ Actas sincronizadas: {n} archivos en `{local_mes}`")

                # Debug: esto te mata el "descargó 5, procesa 0"
                expected = Path(BASE_ROOT) / proyecto / "control_actas" / "actas" / nombre_carpeta_mes
                st.caption(f"🔎 Backend leerá: `{expected}`")
                st.caption(f"🔎 XLSX en esa carpeta: {len(list(expected.glob('*.xlsx')))}")

            except Exception as e:
                st.error("No se pudieron sincronizar actas desde Drive.")
                st.exception(e)
                st.stop()

        with st.spinner("Procesando actas, por favor espera..."):
            info = correr_todo(
                BASE_ROOT,
                proyecto,
                nombre_carpeta_mes,
                valores_referencia,
                modo_critico=modo_critico,
            )

        # Export a Drive (solo Cloud + Oficina)
        if IS_CLOUD and VISTA == "OFICINA":
            try:
                service = get_drive_service()
                root_id = st.secrets["DRIVE_ROOT_FOLDER_ID"]
                with st.spinner("☁️ Subiendo resultados a Drive..."):
                    exportar_resultados_a_drive(service, root_id, proyecto, nombre_carpeta_mes, info)
                st.success("✅ Resultados subidos/actualizados en Drive.")
            except Exception as e:
                st.error("❌ Falló la subida a Drive.")
                st.exception(e)

        st.success("Proceso completado ✅")

        carpeta_mes = info["carpeta_mes"]
        carpeta_salida_mes = info["carpeta_salida_mes"]
        carpeta_resumen_mes = info["carpeta_resumen_mes"]
        carpeta_datos = info["carpeta_datos"]

        n_entrada = len([f for f in os.listdir(carpeta_mes) if f.lower().endswith(".xlsx")]) if os.path.exists(carpeta_mes) else 0
        n_salida = len([f for f in os.listdir(carpeta_salida_mes) if f.lower().endswith(".xlsx")]) if os.path.exists(carpeta_salida_mes) else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("Actas encontradas", n_entrada)
        col2.metric("Actas procesadas", n_salida)
        col3.write(f"Datos guardados en:\n`{carpeta_datos}`")

        with st.expander("Ver rutas generadas"):
            st.json(info)
    else:
        st.info("Usa el botón de la barra lateral para ejecutar el proceso de **un** mes.")

    st.markdown("---")


# ==================================================
# TAB 2: resúmenes
# ==================================================
with tab_resumen:
    st.subheader("Resúmenes y registros")
    col_a, col_b = st.columns(2)

    base_general_path = os.path.join(BASE_ROOT, proyecto, "control_actas", "datos", "base_general.xlsx")

    df_base = None
    if os.path.exists(base_general_path):
        try:
            df_base = pd.read_excel(base_general_path)
        except Exception as e:
            df_base = None
            st.error(f"No se pudo leer base_general.xlsx: {e}")

    with col_a:
        st.markdown("#### Base general")
        if df_base is None or df_base.empty:
            st.info("Aún no existe la base general o está vacía. Ejecuta el proceso primero.")
        else:
            st.dataframe(formatear_numeros_df(df_base.tail(200)), use_container_width=True)

            cols_norm = {str(c).strip().lower(): c for c in df_base.columns}
            col_contratista = None
            for candidata in ["contratista", "contratista ", "nombre_contratista"]:
                if candidata in cols_norm:
                    col_contratista = cols_norm[candidata]
                    break

            if col_contratista:
                contratista_sel = st.selectbox(
                    "Filtrar por contratista (base general)",
                    ["(Todos)"] + sorted(df_base[col_contratista].dropna().astype(str).unique().tolist()),
                )

                if contratista_sel != "(Todos)":
                    st.dataframe(
                        formatear_numeros_df(df_base[df_base[col_contratista].astype(str) == str(contratista_sel)]),
                        use_container_width=True,
                    )
            else:
                st.warning(f"No se encontró columna de contratista. Columnas: {list(df_base.columns)}")

    carpeta_resumen_mes = os.path.join(BASE_ROOT, proyecto, "control_actas", "resumen", nombre_carpeta_mes)
    resumen_mes_path = os.path.join(carpeta_resumen_mes, f"resumen_{nombre_carpeta_mes}.xlsx")

    if os.path.exists(resumen_mes_path):
        with col_b:
            st.markdown(f"#### Resumen mensual ({mes.capitalize()} {anio_proyecto})")
            try:
                df_resumen = pd.read_excel(resumen_mes_path, sheet_name="RESUMEN")
                st.dataframe(formatear_numeros_df(df_resumen), use_container_width=True)
            except Exception as e:
                st.error(f"No se pudo leer el resumen mensual: {e}")
    else:
        col_b.info("Aún no hay resumen mensual generado para este periodo.")

    st.markdown("#### Totales por contratista (Cantidades)")
    try:
        df_cat = pd.read_excel(resumen_mes_path, sheet_name="CANTIDADES")
        st.dataframe(formatear_numeros_df(df_cat), use_container_width=True)
    except Exception:
        st.info("No existe aún la hoja 'CANTIDADES'. Ejecuta el proceso.")


# ==================================================
# TAB 3: Looker
# ==================================================
with tab_informes:
    st.subheader(f"Dashboard del proyecto: {proyecto}")
    url_dashboard = LOOKER_LINKS.get(proyecto)
    if url_dashboard:
        st.link_button("Abrir Dashboard en Looker Studio", url_dashboard)
    else:
        st.warning("No hay un dashboard configurado para este proyecto.")


# ==================================================
# TAB 4: Bases de precios
# ==================================================
with tab_based:
    st.subheader("📂 Base de datos en uso")
    ruta_bd = st.session_state.get("db_precios_path")

    if not ruta_bd:
        st.caption("No hay BD cargada (o estás en modo crítico / falló la carga).")
    else:
        carpeta = os.path.basename(os.path.dirname(ruta_bd))
        archivo = os.path.basename(ruta_bd)
        st.markdown(f"**Archivo activo:** `{carpeta}/{archivo}`")
        if VISTA == "SUBCONTRATOS":
            st.caption("Modo Subcontratos: esta BD se usa como SOLO LECTURA.")
        else:
            st.caption("Modo Oficina: BD accesible según permisos del entorno (Drive).")

    if modo_backend == "normal":
        st.caption("Esto muestra EXACTAMENTE lo que estás usando en modo NORMAL: `valores_referencia`.")
        if not valores_referencia:
            st.warning("`valores_referencia` está vacío.")
        else:
            if isinstance(valores_referencia, dict):
                df_bn = pd.DataFrame([{"actividad": k, "precio": v} for k, v in valores_referencia.items()])
                st.dataframe(formatear_numeros_df(df_bn), use_container_width=True, hide_index=True)
                st.caption(f"Registros: {len(df_bn)}")
            else:
                st.info("`valores_referencia` no es dict. Muestro tal cual:")
                st.write(valores_referencia)








