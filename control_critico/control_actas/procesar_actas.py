from .excel_utils import obtener_columnas
from .config import ACTIVIDADES_CRITICAS

import os
import math
import unicodedata
import re
from openpyxl import load_workbook
from openpyxl.styles import Font


def normalizar(texto):
    if texto is None:
        return ""
    s = str(texto).upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Diccionario normalizado para búsqueda rápida
CRITICOS_NORM = {
    normalizar(k): float(v)
    for k, v in ACTIVIDADES_CRITICAS.items()
}


def revisar_acta(
    path_archivo: str,
    anio_actual: int,
    mes_nombre: str,
    carpeta_salida_mes: str,
    base_registro: list,
    base_cantidades: list | None = None,  # ✅ NUEVO 
):
    try:
        wb = load_workbook(path_archivo, data_only=False)
        wb_vals = load_workbook(path_archivo, data_only=True)

        hoja_corte = None
        for n in ["CORTE", "Corte", "corte", "Corte "]:
            if n in wb.sheetnames:
                hoja_corte = n
                break

        if not hoja_corte:
            print(f"❌ No se encontró hoja CORTE en {path_archivo}")
            return

        ws = wb[hoja_corte]
        ws_vals = wb_vals[hoja_corte]

    except Exception as e:
        print(f"❌ Error abriendo {path_archivo}: {e}")
        return

    nombre_contratista = ws["C6"].value or "SIN NOMBRE"
    columnas = obtener_columnas(ws)

    totales_cant = {
    "Excavaciones": 0.0,
    "Rellenos": 0.0,
    "Concreto MR": 0.0,
    "Concreto estampado": 0.0,
}


    col_item = columnas.get("ÍTEM", "A")
    col_desc = columnas.get("DESCRIPCIÓN", "B")
    col_un = columnas.get("UN", "D")

    col_valor = columnas.get("VALOR UNITARIO")
    if not col_valor:
        print("⚠ No se encontró VALOR UNITARIO")
        return

    col_cantidad = "I"

    for fila in range(10, ws.max_row + 1):
        item = str(ws[f"{col_item}{fila}"].value or "").strip()
        desc_raw = ws[f"{col_desc}{fila}"].value
        un = ws[f"{col_un}{fila}"].value

        if not item or not desc_raw:
            continue

        descripcion = str(desc_raw).strip()
        desc_norm = normalizar(descripcion)



        # Filtros
        if "MANO DE OBRA" in desc_norm or "PEA" in desc_norm:
            continue

        # Buscar actividad crítica por `in`
        precio_ref = None
        for k_norm, precio in CRITICOS_NORM.items():
            if k_norm in desc_norm:
                precio_ref = precio
                break

        if precio_ref is None:
            continue

        # Leer valor unitario
        try:
            valor = float(
                str(ws_vals[f"{col_valor}{fila}"].value)
                .replace("$", "")
                .replace(",", "")
            )
        except Exception:
            continue

        try:
            cantidad = float(ws_vals[f"{col_cantidad}{fila}"].value)
        except Exception:
            cantidad = 0

        if cantidad == 0 or math.isnan(cantidad):
            continue
        
        # ✅ sumar cantidades por categoría (keyword directo)
        if "EXCAV" in desc_norm:
            totales_cant["Excavaciones"] += float(cantidad)
        if "RELLEN" in desc_norm:
            totales_cant["Rellenos"] += float(cantidad)
        if re.search(r"\bMR\b", desc_norm):
            totales_cant["Concreto MR"] += float(cantidad)
        if "ESTAMP" in desc_norm:
            totales_cant["Concreto estampado"] += float(cantidad)



        celda_valor = ws[f"{col_valor}{fila}"]
        diff = valor - precio_ref

        if abs(diff) > 1:
            if diff > 0:
                celda_valor.font = Font(color="FFFF0000")  # rojo
            else:
                celda_valor.font = Font(color="FF0000FF")  # azul

            base_registro.append({
                "anio": anio_actual,
                "mes": mes_nombre,
                "archivo": os.path.basename(path_archivo),
                "contratista": nombre_contratista,
                "item": item,
                "descripcion": descripcion,
                "valor_unitario_original": valor,
                "un": un,
                "valor_pactado": precio_ref,
                "cantidad_presenta": cantidad,
                "valor_ajustado": precio_ref * cantidad,
            })

    salida = os.path.join(
        carpeta_salida_mes,
        os.path.basename(path_archivo).replace(".xlsx", "_verificado.xlsx")
    )
    if base_cantidades is not None:
        base_cantidades.append({
            "anio": anio_actual,
            "mes": mes_nombre,
            "archivo": os.path.basename(path_archivo),
            "contratista": nombre_contratista,
            "Excavaciones": totales_cant["Excavaciones"],
            "Rellenos": totales_cant["Rellenos"],
            "Concreto MR": totales_cant["Concreto MR"],
            "Concreto estampado": totales_cant["Concreto estampado"],
            "modo": "CRITICO",


        })

    wb.save(salida)






