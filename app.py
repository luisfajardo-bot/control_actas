import os
import streamlit as st
import pandas as pd
from pathlib import Path

from control_actas_local import get_backend


def formatear_numeros_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Formatea columnas numéricas:
    - Separador de miles
    - Máximo 2 decimales
    - No altera el DF original
    """
    df_fmt = df.copy()

    for col in df_fmt.columns:
        if pd.api.types.is_numeric_dtype(df_fmt[col]):
            df_fmt[col] = df_fmt[col].apply(
                lambda x: f"{x:,.2f}" if pd.notnull(x) else x
            )

    return df_fmt


# ==================================================
# CONFIG CENTRAL (RUTAS + DEFAULTS + HELPERS)
# ==================================================
REPO_ROOT = Path(__file__).resolve().parent

# 1) Donde viven tus proyectos (actas/salidas)
#    En LOCAL puedes dejarlo apuntando a tu Drive.
#    En CLOUD lo ideal es que esto sea relativo al repo o temporal.
DEFAULT_PROYECTOS_ROOT_LOCAL = Path(r"G:\Mi unidad\Subcontratos")  # <-- cámbialo fácil aquí

# 2) Donde viven tus bases de precios por año/versión
DEFAULT_PRECIOS_ROOT_LOCAL = Path(r"G:\Mi unidad\Subcontratos\precios_referencia")  # <-- y aquí

# Defaults de filtros
DEFAULT_ANIO_PROY = 2026
DEFAULT_PRECIOS_VERSION = "2025"


def detectar_carpetas_anio(root: Path, fallback: list[int]) -> list[int]:
    """Lista subcarpetas '2025', '2026', etc. Si no existe, usa fallback."""
    if root.exists():
        yrs = []
        for p in root.iterdir():
            if p.is_dir() and p.name.isdigit():
                yrs.append(int(p.name))
        if yrs:
            return sorted(yrs)
    return fallback


def detectar_versiones_precios(root: Path, fallback: list[str]) -> list[str]:
    """Lista carpetas de versiones dentro de PRECIOS_ROOT (ej: 2024, 2025)."""
    if root.exists():
        vs = []
        for p in root.iterdir():
            if p.is_dir():
                vs.append(p.name)
        if vs:
            return sorted(vs)
    return fallback


def get_proyectos_root() -> Path:
    # Si luego quieres hacerlo cloud-friendly: puedes usar st.secrets o variables de entorno
    return DEFAULT_PROYECTOS_ROOT_LOCAL


def get_precios_root() -> Path:
    return DEFAULT_PRECIOS_ROOT_LOCAL


def construir_db_path(precios_root: Path, version: str) -> str:
    return str(precios_root / str(version) / "precios_referencia.db")


# --------------------------------------------------
# Configuración básica de la página
# --------------------------------------------------
st.set_page_config(
    page_title="Control de Actas de Obra- ICEIN 🤓",
    page_icon="📑",
    layout="wide",
)

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

# Mantener selección
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

/* ================= VARIABLES ================= */
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

/* ================= BASE ================= */
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

/* ================= SELECTBOX FIX ================= */

/* Caja cerrada */
section[data-testid="stSidebar"] div[data-baseweb="select"] > div {{
  background-color: var(--card) !important;
  border: 1px solid var(--border) !important;
}}

/* Texto seleccionado */
section[data-testid="stSidebar"] div[data-baseweb="select"] span,
section[data-testid="stSidebar"] div[data-baseweb="select"] div,
section[data-testid="stSidebar"] div[data-baseweb="select"] p {{
  color: var(--text) !important;
}}

/* Flecha */
section[data-testid="stSidebar"] div[data-baseweb="select"] svg {{
  fill: var(--text) !important;
}}

/* Popover flotante */
div[data-baseweb="popover"],
div[data-baseweb="popover"] * {{
  background-color: var(--card) !important;
}}

/* Lista */
ul[role="listbox"] {{
  background-color: var(--card) !important;
  border: 1px solid var(--border) !important;
  padding: 6px !important;
}}

/* Opciones */
ul[role="listbox"] li,
ul[role="listbox"] div[role="option"] {{
  background-color: var(--card) !important;
  color: var(--text) !important;
}}

/* Hover */
ul[role="listbox"] li:hover,
ul[role="listbox"] div[role="option"]:hover {{
  background-color: var(--primary) !important;
  color: var(--button_text) !important;
}}

/* Seleccionado */
ul[role="listbox"] li[aria-selected="true"],
ul[role="listbox"] div[role="option"][aria-selected="true"] {{
  background-color: var(--primary) !important;
  color: var(--button_text) !important;
}}

/* Input interno */
div[data-baseweb="select"] input {{
  color: var(--text) !important;
  caret-color: var(--text) !important;
}}

/* ================= BOTONES ================= */

/* st.button */
.stButton > button {{
  background: var(--primary) !important;
  color: var(--button_text) !important;
  border: 1px solid var(--primary) !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
  padding: 0.6rem 1rem !important;
}}

.stButton > button:hover {{
  filter: brightness(0.95);
}}

.stButton > button:active {{
  transform: translateY(1px);
}}

.stButton > button:disabled {{
  opacity: 0.55 !important;
  background: var(--card) !important;
  color: var(--muted) !important;
  border: 1px solid var(--border) !important;
}}

/* st.link_button */
a[data-testid="stLinkButton"] {{
  background: var(--primary) !important;
  color: var(--button_text) !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
  border: 1px solid var(--primary) !important;
  padding: 0.6rem 1rem !important;
  text-decoration: none !important;
}}

a[data-testid="stLinkButton"]:hover {{
  filter: brightness(0.95);
}}

/* Botones BaseWeb */
button[kind="primary"],
button[kind="secondary"],
button[data-baseweb="button"] {{
  background: var(--primary) !important;
  color: var(--button_text) !important;
  border: 1px solid var(--primary) !important;
  border-radius: 12px !important;
  font-weight: 700 !important;
}}

/* Iconos dentro del botón */
.stButton svg,
button[data-baseweb="button"] svg {{
  fill: var(--button_text) !important;
}}

</style>
""",
    unsafe_allow_html=True,
)

# --------------------------------------------------
# Tus constantes
# --------------------------------------------------
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

# --------------------------------------------------
# SIDEBAR: filtros
# --------------------------------------------------
st.sidebar.title("Filtros")
st.sidebar.markdown("---")

# 1) Modo crítico primero (no depende de nada)
modo_critico = st.sidebar.toggle(
    "🔥 Modo crítico (solo actividades sensibles)",
    value=False
)
modo_backend = "critico" if modo_critico else "normal"

# 2) Proyecto / Año / Mes (estos crean anio_proyecto)
proyecto = st.sidebar.selectbox("Proyecto", PROYECTOS)

anio_proyecto = st.sidebar.selectbox(
    "Año (Proyecto / Actas / Salidas)",
    list(range(2025, 2035)),
    index=list(range(2025, 2035)).index(st.session_state.get("anio_proyecto", 2026))
    if st.session_state.get("anio_proyecto", 2026) in list(range(2025, 2035)) else 0
)
st.session_state["anio_proyecto"] = anio_proyecto

mes = st.sidebar.selectbox("Mes", MESES)

nombre_carpeta_mes = f"{mes}{anio_proyecto}"

# 3) YA con anio_proyecto definido, ahora sí importamos backend
backend = get_backend(modo_backend, anio_proyecto=anio_proyecto)

BASE_ROOT = backend["BASE_ROOT"]
correr_todo = backend["correr_todo"]
correr_todos_los_meses = backend.get("correr_todos_los_meses")  # puede ser None en crítico
listar_carpetas_mes = backend["listar_carpetas_mes"]

# 4) Base de precios (depende solo del selector, no del backend)
st.sidebar.markdown("---")

# Si estás en crítico, no tiene sentido base de precios (la puedes ocultar)
if not modo_critico:
    precios_version = st.sidebar.selectbox(
        "Base de precios (versión/año)",
        ["2024", "2025", "2026"],
        index=["2024", "2025", "2026"].index(st.session_state.get("precios_version", "2025"))
        if st.session_state.get("precios_version", "2025") in ["2024", "2025", "2026"] else 1
    )
    st.session_state["precios_version"] = precios_version
else:
    st.session_state["precios_version"] = st.session_state.get("precios_version", "2025")

st.sidebar.markdown("---")
procesar_btn = st.sidebar.button("🚀 Procesar actas")

# --------------------------------------------------
# HEADER
# --------------------------------------------------
st.title("Control de Actas - ICEIN")
st.caption("Revisión automática de valores unitarios de cada actividad por proyecto, mes y año.")

st.markdown(
    f"### Proyecto seleccionado: **{proyecto}**  \n"
    f"Periodo: **{mes.capitalize()} {anio_proyecto}**  \n"
    f"Carpeta: `{nombre_carpeta_mes}`  \n"
    f"Base de precios: **{precios_version}**"
)

# ==================================================
# BD PRECIOS (solo NORMAL)
# ==================================================
valores_referencia = {}

if not modo_critico:
    from control_actas.bd_precios import cargar_valores_referencia

    db_path = construir_db_path(get_precios_root(), st.session_state["precios_version"])
    st.session_state["db_precios_path"] = db_path

    valores_referencia = cargar_valores_referencia(db_path)
else:
    st.session_state["db_precios_path"] = None

# --------------------------------------------------
# TABS: una para ejecutar, otra para visualizar
# --------------------------------------------------
tab_run, tab_resumen, tab_informes, tab_based = st.tabs(
    ["▶ Ejecutar proceso", "📊 Ver resúmenes", "📒📋 Ver informes", "🧾 Bases de precios"]
)

# --------------------------------------------------
# TAB 1: ejecutar proceso
# --------------------------------------------------
with tab_run:
    st.subheader("Procesar todos los meses del proyecto")
    st.caption("Este proceso puede tardar varios minutos, preferiblemente usar solo cuando sea necesario")

    if st.button("🌎 Procesar TODAS las carpetas del proyecto"):
        if correr_todos_los_meses is None:
            st.warning("En modo crítico no está habilitado 'Procesar todas las carpetas'.")
        else:
            with st.spinner("Procesando todas las carpetas del proyecto..."):
                resultados = correr_todos_los_meses(BASE_ROOT, proyecto, valores_referencia)

            if resultados:
                st.success(f"Proceso completado para {len(resultados)} carpetas de mes ✅")
            else:
                st.warning("No se encontraron carpetas de mes para este proyecto.")

            if resultados:
                df_res = pd.DataFrame(
                    [
                        {"carpeta_mes": r["carpeta_mes"], "anio": r["anio"], "mes": r["mes"]}
                        for r in resultados
                        if r is not None
                    ]
                )
                st.dataframe(df_res)

    st.subheader("Ejecución")
    if procesar_btn:
        with st.spinner("Procesando actas, por favor espera..."):
            info = correr_todo(
                BASE_ROOT,
                proyecto,
                nombre_carpeta_mes,
                valores_referencia,
                modo_critico=modo_critico
            )

        st.success("Proceso completado ✅")

        carpeta_mes = info["carpeta_mes"]
        carpeta_salida_mes = info["carpeta_salida_mes"]
        carpeta_resumen_mes = info["carpeta_resumen_mes"]
        carpeta_datos = info["carpeta_datos"]

        n_entrada = len([f for f in os.listdir(carpeta_mes) if f.lower().endswith(".xlsx")])
        n_salida = len([f for f in os.listdir(carpeta_salida_mes) if f.lower().endswith(".xlsx")])

        col1, col2, col3 = st.columns(3)
        col1.metric("Actas encontradas", n_entrada)
        col2.metric("Actas procesadas", n_salida)
        col3.write(f"Datos guardados en:\n`{carpeta_datos}`")

        with st.expander("Ver rutas generadas"):
            st.json(info)
    else:
        st.info("Usa el botón de la barra lateral para ejecutar el proceso de **un** mes.")

    st.markdown("---")


# --------------------------------------------------
# TAB 2: visualizar resúmenes y base de datos
# --------------------------------------------------
with tab_resumen:
    st.subheader("Resúmenes y registros")

    col_a, col_b = st.columns(2)

    # Base general (toda la historia)
    base_general_path = os.path.join(
        BASE_ROOT, proyecto, "control_actas", "datos", "base_general.xlsx"
    )

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
            st.dataframe(
                formatear_numeros_df(df_base.tail(200)),
                use_container_width=True
            )

            # --------- FILTRO DE CONTRATISTA ----------
            cols_norm = {str(c).strip().lower(): c for c in df_base.columns}

            col_contratista = None
            for candidata in ["contratista", "contratista ", "nombre_contratista"]:
                if candidata in cols_norm:
                    col_contratista = cols_norm[candidata]
                    break

            if col_contratista:
                contratista_sel = st.selectbox(
                    "Filtrar por contratista (base general)",
                    ["(Todos)"] + sorted(
                        df_base[col_contratista].dropna().astype(str).unique().tolist()
                    ),
                )

                if contratista_sel != "(Todos)":
                    st.dataframe(
                        formatear_numeros_df(
                            df_base[df_base[col_contratista].astype(str) == str(contratista_sel)]
                        ),
                        use_container_width=True
                    )
            else:
                st.warning(
                    f"No se encontró columna de contratista. Columnas disponibles: {list(df_base.columns)}"
                )

    # Resumen mensual
    carpeta_resumen_mes = os.path.join(
        BASE_ROOT, proyecto, "control_actas", "resumen", nombre_carpeta_mes
    )
    resumen_mes_path = os.path.join(carpeta_resumen_mes, f"resumen_{nombre_carpeta_mes}.xlsx")

    if os.path.exists(resumen_mes_path):
        with col_b:
            st.markdown(f"#### Resumen mensual ({mes.capitalize()} {anio_proyecto})")
            try:
                df_resumen = pd.read_excel(resumen_mes_path, sheet_name="RESUMEN")
                st.dataframe(
                    formatear_numeros_df(df_resumen),
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"No se pudo leer el resumen mensual: {e}")
    else:
        col_b.info("Aún no hay resumen mensual generado para este periodo.")

    st.markdown("#### Totales por contratista (Cantidades)")
    try:
        df_cat = pd.read_excel(resumen_mes_path, sheet_name="CANTIDADES")
        st.dataframe(
            formatear_numeros_df(df_cat),
            use_container_width=True
        )
    except Exception:
        st.info("No existe aún la hoja 'CANTIDADES'. Ejecuta el proceso.")


# --------------------------------------------------
# TAB 3: informes de looker studio
# --------------------------------------------------
with tab_informes:
    st.subheader(f"Dashboard del proyecto: {proyecto}")

    url_dashboard = LOOKER_LINKS.get(proyecto)

    if url_dashboard:
        st.link_button("Abrir Dashboard en Looker Studio", url_dashboard)
    else:
        st.warning("No hay un dashboard configurado para este proyecto.")


# --------------------------------------------------
# TAB 4: bases de precios
# --------------------------------------------------
with tab_based:
    st.subheader("📂 Base de datos en uso")

    ruta_bd = st.session_state.get("db_precios_path")

    if not ruta_bd:
        st.caption("Base de datos definida en de forma manual")
    else:
        carpeta = os.path.basename(os.path.dirname(ruta_bd))
        archivo = os.path.basename(ruta_bd)

        st.markdown(
            f"""
            **Archivo activo:**  
            `{carpeta}/{archivo}`
            """
        )

        st.caption("Esta es la base que el sistema está usando en este momento.")

    if modo_backend == "normal":
        st.caption("Esto muestra EXACTAMENTE lo que estás usando en modo NORMAL: `valores_referencia`.")

        if not valores_referencia:
            st.warning("`valores_referencia` está vacío. (O estás en modo crítico, o falló la carga).")
        else:
            if isinstance(valores_referencia, dict):
                df_bn = pd.DataFrame(
                    [{"actividad": k, "precio": v} for k, v in valores_referencia.items()]
                )
                st.dataframe(
                    formatear_numeros_df(df_bn),
                    use_container_width=True,
                    hide_index=True
                )
                st.caption(f"Registros: {len(df_bn)}")
            else:
                st.info("`valores_referencia` no es dict. Muestro tal cual:")
                st.write(valores_referencia)

    if modo_backend == "critico":
        st.caption("Esto muestra EXACTAMENTE lo que estás usando en modo CRÍTICO: `ACTIVIDADES_CRITICAS` (si está definida).")

        try:
            from control_actas.config import ACTIVIDADES_CRITICAS
        except Exception as e:
            ACTIVIDADES_CRITICAS = None
            st.error(f"No pude importar ACTIVIDADES_CRITICAS: {e}")

        if not ACTIVIDADES_CRITICAS:
            st.warning("`ACTIVIDADES_CRITICAS` está vacío o no existe.")
        else:
            if isinstance(ACTIVIDADES_CRITICAS, dict):
                sample_val = next(iter(ACTIVIDADES_CRITICAS.values()))
                if isinstance(sample_val, (int, float)):
                    df_bc = pd.DataFrame(
                        [{"actividad": k, "precio": v} for k, v in ACTIVIDADES_CRITICAS.items()]
                    )
                else:
                    df_bc = pd.DataFrame(
                        [{"actividad": k, **(v if isinstance(v, dict) else {"valor": v})}
                         for k, v in ACTIVIDADES_CRITICAS.items()]
                    )

                st.dataframe(df_bc, use_container_width=True, hide_index=True)
                st.caption(f"Registros: {len(df_bc)}")
            else:
                st.info("`ACTIVIDADES_CRITICAS` no es dict. Muestro tal cual:")
                st.write(ACTIVIDADES_CRITICAS)


        



