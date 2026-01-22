# utils/drive_db.py
from __future__ import annotations
from pathlib import Path

# Ajusta estos imports a tu implementación real
from utils.drive_utils import download_file, upload_file


def bajar_db_drive(file_id: str, dst_path: str | Path) -> Path:
    dst_path = Path(dst_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    download_file(file_id=file_id, destination=str(dst_path))
    return dst_path


def subir_db_drive(file_id: str, src_path: str | Path) -> None:
    upload_file(file_id=file_id, source=str(src_path))
