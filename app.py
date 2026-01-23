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

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
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

    IMPORTANTE:
    - El backend arma la ruta como:
      base_root / proyecto / control_actas / actas / nombre_carpeta_mes
    """
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

    candidates = [
        [proyecto, "control_actas", "actas", nombre_carpeta_mes],
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

    for p in Path(info["carpeta_salida_mes"]).glob("*.xlsx"):
        upload_or_update_file(service, salidas_mes_id, p, mime_xlsx)

    for p in Path(info["carpeta_resumen_mes"]).glob("*.xlsx"):
        upload_or_update_file(service, resumen_mes_id, p, mime_xlsx)

    base_general = Path(info["carpeta_datos"]) / "base_general.xlsx"
    if base_general.exists():
        upload_or_update_file(service, datos_id, base_general, mime_xlsx)

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
            df_fmt[col] = df_fmt[col].apply(
                lambda x: f"{x:,.2f}" if pd.notnull(x) else x
            )
    return df_fmt

















