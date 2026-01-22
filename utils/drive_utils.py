# drive_utils.py
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    """
    Crea el cliente de Google Drive usando secrets en formato TOML:
    [google_service_account] ...
    """
    info = dict(st.secrets["google_service_account"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def list_folders(service, parent_id: str):
    q = (
        f"'{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id,name)", pageSize=100).execute()
    return res.get("files", [])


def find_child_folder(service, parent_id: str, name: str):
    q = (
        f"'{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and name='{name}' "
        f"and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def find_file(service, parent_id: str, filename: str):
    q = (
        f"'{parent_id}' in parents "
        f"and name='{filename}' "
        f"and trashed=false"
    )
    res = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def download_file(service, file_id: str, dest_path):
    request = service.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

def detectar_carpetas_anio(service, parent_id, fallback):
    folders = list_folders(service, parent_id)
    yrs = []
    for f in folders:
        if f["name"].isdigit():
            yrs.append(int(f["name"]))
    return sorted(yrs) if yrs else fallback


def detectar_versiones_precios(service, precios_root_id, fallback):
    folders = list_folders(service, precios_root_id)
    return sorted([f["name"] for f in folders]) or fallback

