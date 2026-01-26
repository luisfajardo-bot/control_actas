"""
bd_editor_ui.py

UI auxiliar para editar la BD de precios en vista OFICINA.

- No toca la lógica del backend (revisión / pipeline).
- No altera funciones existentes; se integra desde app.py con una sola llamada.

Permite:
- Ver BD (actividad, precio, unidad)
- Editar precios/unidad en tabla
- Agregar nuevos ítems (upsert)
- Cargar un Excel/CSV (actividad, precio, unidad) y hacer upsert
- Guardar cambios:
  - Local: escribe en la ruta_bd.
  - Cloud: además sube el .db a Drive (misma carpeta de versión).

Notas:
- No implementa borrado para evitar cambios de comportamiento.
- Se apoya en control_actas.bd_precios (leer_precios / upsert_precios / cargar_valores_referencia).
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

# Import robusto desde el backend activo (control_actas)
try:
    from control_actas.bd_precios import (
        leer_precios,
        upsert_precios,
        cargar_valores_referencia,
    )
except Exception:  # pragma: no cover
    leer_precios = None
    upsert_precios = None
    cargar_valores_referencia = None


def _require_bd_funcs():
    if leer_precios is None or upsert_precios is None or cargar_valores_referencia is None:
        st.error(
            "No pude importar 'leer_precios' / 'upsert_precios' / 'cargar_valores_referencia' "
            "desde control_actas.bd_precios. Verifica que el backend activo expone ese módulo."
        )
        st.stop()


def _upload_db_to_drive(
    *,
    ruta_bd: Path,
    is_cloud: bool,
    precios_version: str,
    drive_service=None,
    drive_root_id: str | None = None,
    find_child_folder=None,
    upload_or_update_file=None,
) -> None:
    """Sube/actualiza el archivo .db en Drive si estamos en Cloud y hay utilidades disponibles."""
    if not is_cloud:
        return

    if drive_service is None or drive_root_id is None:
        st.warning("Estoy en Cloud, pero no recibí credenciales/servicio de Drive para subir la BD.")
        return

    if find_child_folder is None or upload_or_update_file is None:
        st.warning("Faltan funciones de Drive (find_child_folder / upload_or_update_file).")
        return

    try:
        precios_root_id = find_child_folder(drive_service, drive_root_id, "precios_referencia")
        if not precios_root_id:
            raise FileNotFoundError("No existe carpeta 'precios_referencia' en Drive.")

        version_folder_id = find_child_folder(drive_service, precios_root_id, str(precios_version))
        if not version_folder_id:
            raise FileNotFoundError(f"No existe carpeta de versión '{precios_version}' en Drive.")

        mime_db = "application/x-sqlite3"
        upload_or_update_file(drive_service, version_folder_id, ruta_bd, mime_db)
        st.success("☁️ BD subida/actualizada en Drive ✅")

    except Exception as e:
        msg = str(e)

        # Caso típico en Streamlit Cloud con Service Accounts
        if "Service Accounts do not have storage quota" in msg or "storageQuotaExceeded" in msg:
            st.error("Guardé local, pero no pude subir a Drive por cuota de Service Account.")
            st.info(
                "Solución: mueve 'precios_referencia' a una Unidad compartida (Shared Drive) "
                "y agrega esta Service Account como miembro de esa Unidad. "
                "En 'Mi unidad' la Service Account no tiene cuota."
            )
            return

        st.error("Guardé local, pero falló la subida a Drive.")
        st.exception(e)


def _bootstrap_precios_desde_legacy(db_path: Path) -> bool:
    """
    Si la tabla nueva 'precios' está vacía pero existen datos legacy,
    los copia a 'precios' mediante upsert. Retorna True si migró algo.
    """
    try:
        legacy = cargar_valores_referencia(db_path) or {}
    except Exception:
        legacy = {}

    if not legacy:
        return False

    df_boot = pd.DataFrame(
        [{"actividad": k, "precio": v, "unidad": None} for k, v in legacy.items()]
    )
    upsert_precios(db_path, df_boot)
    return True


def _coerce_df_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Asegura columnas esperadas para upsert."""
    df2 = df.copy()
    cols = {str(c).strip().lower(): c for c in df2.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    col_act = pick("actividad", "item", "descripcion", "concepto", "nombre")
    col_pre = pick("precio", "valor", "pu", "unitario", "precio_unitario")
    col_uni = pick("unidad", "un")

    if col_act is None or col_pre is None:
        raise ValueError("El archivo debe tener al menos columnas 'actividad' y 'precio' (o equivalentes).")

    out = pd.DataFrame(
        {
            "actividad": df2[col_act],
            "precio": df2[col_pre],
        }
    )

    if col_uni is not None:
        out["unidad"] = df2[col_uni]
    else:
        out["unidad"] = None

    out["actividad"] = out["actividad"].astype(str).str.strip()
    out["unidad"] = out["unidad"].astype(str).replace({"nan": ""}).str.strip()
    out.loc[out["unidad"] == "", "unidad"] = None

    out["precio"] = pd.to_numeric(out["precio"], errors="coerce")
    out = out[out["actividad"].notna() & (out["actividad"] != "")]
    return out


def render_bd_editor(
    *,
    ruta_bd: str | Path,
    is_cloud: bool,
    precios_version: str,
    drive_service=None,
    drive_root_id: str | None = None,
    find_child_folder=None,
    upload_or_update_file=None,
) -> None:
    """Renderiza editor de BD."""
    _require_bd_funcs()

    ruta_bd = Path(ruta_bd)
    if not ruta_bd.exists():
        st.warning("No encuentro el archivo local de la BD para editar.")
        return

    st.markdown("---")
    st.subheader("🛠️ Editor de base de precios (OFICINA)")

    try:
        df = leer_precios(ruta_bd)

        # Si está vacía pero existen datos legacy, migra a la tabla nueva 'precios'
        if df.empty:
            migro = _bootstrap_precios_desde_legacy(ruta_bd)
            if migro:
                # En Cloud: subir inmediatamente la BD migrada, para que no se pierda en el rerun
                _upload_db_to_drive(
                    ruta_bd=ruta_bd,
                    is_cloud=is_cloud,
                    precios_version=precios_version,
                    drive_service=drive_service,
                    drive_root_id=drive_root_id,
                    find_child_folder=find_child_folder,
                    upload_or_update_file=upload_or_update_file,
                )
                df = leer_precios(ruta_bd)

    except Exception as e:
        st.error("No pude leer la BD de precios.")
        st.exception(e)
        return

    colf1, colf2 = st.columns([2, 1])
    with colf1:
        q = st.text_input(
            "Buscar por texto (actividad)",
            value="",
            placeholder="Ej: excavación, concreto, ...",
            key=f"bd_q_{precios_version}",
        )
    with colf2:
        solo_sin_unidad = st.checkbox("Solo sin unidad", value=False, key=f"bd_su_{precios_version}")

    df_view = df.copy()
    if q.strip():
        df_view = df_view[df_view["actividad"].astype(str).str.contains(q.strip(), case=False, na=False)]
    if solo_sin_unidad:
        df_view = df_view[df_view["unidad"].isna() | (df_view["unidad"].astype(str).str.strip() == "")]

    st.caption(f"Registros visibles: {len(df_view)} | Registros totales: {len(df)}")

    edit_cols = ["actividad", "precio", "unidad"]
    df_edit = df_view[edit_cols].copy()

    edited = st.data_editor(
        df_edit,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key=f"bd_editor_{precios_version}",
        column_config={
            "actividad": st.column_config.TextColumn("Actividad", required=True),
            "precio": st.column_config.NumberColumn("Precio", required=True, format="%,.2f"),
            "unidad": st.column_config.TextColumn("Unidad"),
        },
    )

    with st.expander("➕ Agregar / actualizar un ítem puntual"):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            new_act = st.text_input("Actividad", key=f"new_act_{precios_version}")
        with c2:
            new_pre = st.number_input(
                "Precio",
                min_value=0.0,
                value=0.0,
                step=100.0,
                key=f"new_pre_{precios_version}",
            )
        with c3:
            new_uni = st.text_input("Unidad (opcional)", key=f"new_uni_{precios_version}")

        if st.button("Agregar / actualizar", key=f"btn_add_{precios_version}"):
            try:
                df_add = pd.DataFrame(
                    [
                        {
                            "actividad": (new_act or "").strip(),
                            "precio": float(new_pre),
                            "unidad": (new_uni or "").strip() or None,
                        }
                    ]
                )

                # Guardar local
                upsert_precios(ruta_bd, df_add)
                st.success("Listo: ítem guardado en la BD local ✅")

                # Subir a Drive en Cloud para que no se pierda en rerun
                _upload_db_to_drive(
                    ruta_bd=ruta_bd,
                    is_cloud=is_cloud,
                    precios_version=precios_version,
                    drive_service=drive_service,
                    drive_root_id=drive_root_id,
                    find_child_folder=find_child_folder,
                    upload_or_update_file=upload_or_update_file,
                )

                st.rerun()

            except Exception as e:
                st.error("No pude guardar el ítem.")
                st.exception(e)

    with st.expander("📥 Carga masiva (Excel/CSV)"):
        st.caption("Columnas esperadas: actividad, precio, unidad (unidad es opcional).")
        up = st.file_uploader(
            "Subir archivo",
            type=["xlsx", "csv"],
            accept_multiple_files=False,
            key=f"uploader_{precios_version}",
        )

        if up is not None:
            try:
                if up.name.lower().endswith(".csv"):
                    raw = pd.read_csv(up)
                else:
                    raw = pd.read_excel(up)

                df_up = _coerce_df_schema(raw)

                st.write("Vista previa (primeras 20):")
                st.dataframe(df_up.head(20), use_container_width=True, hide_index=True)

                if st.button("Aplicar carga (upsert)", key=f"btn_mass_{precios_version}"):
                    # Guardar local
                    upsert_precios(ruta_bd, df_up)
                    st.success(f"Se aplicó upsert de {len(df_up)} filas en la BD local ✅")

                    # Subir a Drive en Cloud
                    _upload_db_to_drive(
                        ruta_bd=ruta_bd,
                        is_cloud=is_cloud,
                        precios_version=precios_version,
                        drive_service=drive_service,
                        drive_root_id=drive_root_id,
                        find_child_folder=find_child_folder,
                        upload_or_update_file=upload_or_update_file,
                    )

                    st.rerun()

            except Exception as e:
                st.error("No pude procesar el archivo.")
                st.exception(e)

    st.markdown("---")

    colg1, colg2 = st.columns([1, 2])
    with colg1:
        guardar_local = st.button("💾 Guardar cambios de la tabla", key=f"btn_save_{precios_version}")
    with colg2:
        st.caption(
            "Esto hace **upsert** por 'actividad'. Si editas una actividad existente, se actualiza. "
            "Si agregas una nueva fila, se inserta."
        )

    if guardar_local:
        try:
            df_save = edited.copy()
            df_save["actividad"] = df_save["actividad"].astype(str).str.strip()
            df_save["precio"] = pd.to_numeric(df_save["precio"], errors="coerce")

            if "unidad" in df_save.columns:
                df_save["unidad"] = df_save["unidad"].astype(str).replace({"nan": ""}).str.strip()
                df_save.loc[df_save["unidad"] == "", "unidad"] = None

            df_save = df_save[df_save["actividad"].notna() & (df_save["actividad"] != "")]
            upsert_precios(ruta_bd, df_save)

            st.success("Cambios guardados en la BD local ✅")

            _upload_db_to_drive(
                ruta_bd=ruta_bd,
                is_cloud=is_cloud,
                precios_version=precios_version,
                drive_service=drive_service,
                drive_root_id=drive_root_id,
                find_child_folder=find_child_folder,
                upload_or_update_file=upload_or_update_file,
            )

            st.rerun()

        except Exception as e:
            st.error("No pude guardar los cambios de la tabla.")
            st.exception(e)
