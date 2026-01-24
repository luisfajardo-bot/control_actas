from __future__ import annotations

import io
import os
import zipfile
import tempfile
from pathlib import Path
from typing import Iterable, Tuple, Dict, Any, List

import pandas as pd

from .pipeline_mes import detectar_anio_y_mes_desde_nombre  # si existe en tu pipeline; si no, lo quitamos
from .procesar_actas import revisar_acta
from .bd_precios import cargar_valores_referencia


def _save_uploaded_file(uploaded, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        f.write(uploaded.getbuffer())


def _extraer_xlsx_desde_uploads(
    uploads: List,
    work_dir: Path,
) -> List[Path]:
    """
    Recibe lista de UploadedFile (xlsx o zip) y devuelve paths a .xlsx extraídos.
    """
    xlsx_paths: List[Path] = []

    for uf in uploads:
        name = (uf.name or "").lower().strip()

        if name.endswith(".xlsx"):
            p = work_dir / uf.name
            _save_uploaded_file(uf, p)
            xlsx_paths.append(p)

        elif name.endswith(".zip"):
            # guardar zip y extraer
            zip_path = work_dir / uf.name
            _save_uploaded_file(uf, zip_path)

            extract_dir = work_dir / (zip_path.stem + "_unzipped")
            extract_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)

            # buscar xlsx recursivo
            for p in extract_dir.rglob("*.xlsx"):
                # ignora temporales de Excel
                if p.name.startswith("~$"):
                    continue
                xlsx_paths.append(p)

        else:
            # ignora otros archivos
            continue

    # dedup (por ruta absoluta)
    uniq = []
    seen = set()
    for p in xlsx_paths:
        ap = str(p.resolve())
        if ap not in seen:
            uniq.append(p)
            seen.add(ap)
    return uniq


def _zip_dir_to_bytes(folder: Path) -> bytes:
    """
    Empaqueta folder (recursivo) a ZIP en memoria.
    """
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob("*"):
            if p.is_file():
                z.write(p, arcname=str(p.relative_to(folder)))
    return bio.getvalue()


def correr_revision_desde_uploads_normal(
    uploads: List,
    *,
    anio: int,
    mes_nombre: str,
    base_root_path: Path,
) -> Dict[str, Any]:
    """
    Procesa actas subidas (xlsx o zip) SIN Drive.
    Retorna:
      - dfs: base_general_df, base_cantidades_df, resumen_df
      - out_dir: carpeta con outputs
      - zip_bytes: zip con outputs
      - archivos_procesados: lista de nombres
    """
    if not uploads:
        raise ValueError("No se subieron archivos.")

    # Carga BD precios referencia (normal)
    valores_ref = cargar_valores_referencia(base_root_path)

    with tempfile.TemporaryDirectory(prefix="actas_upload_") as td:
        work_dir = Path(td)
        in_dir = work_dir / "inputs"
        out_dir = work_dir / "outputs"
        in_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        xlsx_paths = _extraer_xlsx_desde_uploads(uploads, in_dir)
        if not xlsx_paths:
            raise ValueError("No se encontraron .xlsx dentro de lo subido.")

        base_registro: list = []
        base_cantidades: list = []

        # Procesar cada acta como ya haces hoy
        for xlsx in xlsx_paths:
            # OJO: aquí usamos tu revisar_acta existente
            revisar_acta(
                path_archivo=str(xlsx),
                valores_referencia=valores_ref,
                anio_actual=anio,
                mes_nombre=mes_nombre,
                carpeta_salida_mes=str(out_dir),
                base_registro=base_registro,
                base_cantidades=base_cantidades,
                modo_critico=False,
            )

        # DataFrames
        base_general_df = pd.DataFrame(base_registro)
        base_cantidades_df = pd.DataFrame(base_cantidades)

        # Resumen (ajústalo a tu gusto)
        if not base_general_df.empty:
            resumen_df = (
                base_general_df
                .groupby(["contratista"], dropna=False)
                .agg(
                    Items_con_error=("item", "count"),
                    Valor_ajustado_total=("valor_ajustado", "sum"),
                )
                .reset_index()
                .sort_values("Items_con_error", ascending=False)
            )
        else:
            resumen_df = pd.DataFrame(columns=["contratista", "Items_con_error", "Valor_ajustado_total"])

        # ===============================
        # Guardar archivos de salida
        # ===============================
        base_general_path = out_dir / "base_general.xlsx"
        base_cant_path = out_dir / "base_cantidades.xlsx"
        resumen_path = out_dir / "resumen.xlsx"

        base_general_df.to_excel(base_general_path, index=False)
        base_cantidades_df.to_excel(base_cant_path, index=False)
        resumen_df.to_excel(resumen_path, index=False)

        # ===============================
        # Crear ZIP con todos los outputs
        # ===============================
        zip_bytes = _zip_dir_to_bytes(out_dir)

        # ===============================
        # Retorno al frontend (app.py)
        # ===============================
        return {
            "base_general_df": base_general_df,
            "base_cantidades_df": base_cantidades_df,
            "resumen_df": resumen_df,
            "zip_bytes": zip_bytes,
            "archivos_procesados": [p.name for p in xlsx_paths],
        }

