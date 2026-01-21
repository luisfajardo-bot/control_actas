# control_actas/pipeline_mes.py
import os
import pandas as pd

from .meses import parsear_anio_mes_desde_carpeta, listar_carpetas_mes
from .excel_utils import preparar_registro
from .procesar_actas import revisar_acta


def correr_todo(base_root: str, proyecto: str, nombre_carpeta_mes: str, valores_referencia: dict, modo_critico: bool = False):
    base_path = os.path.join(base_root, proyecto, "control_actas")

    anio_actual, mes_nombre = parsear_anio_mes_desde_carpeta(nombre_carpeta_mes)
    print(f"Año detectado: {anio_actual}, Mes detectado: {mes_nombre}")

    carpeta_mes = os.path.join(base_path, "actas", nombre_carpeta_mes)
    carpeta_salida_mes = os.path.join(base_path, "salidas", nombre_carpeta_mes)
    carpeta_datos = os.path.join(base_path, "datos")
    carpeta_resumen = os.path.join(base_path, "resumen")
    carpeta_resumen_mes = os.path.join(carpeta_resumen, nombre_carpeta_mes)

    for ruta in [carpeta_mes, carpeta_salida_mes, carpeta_datos, carpeta_resumen, carpeta_resumen_mes]:
        os.makedirs(ruta, exist_ok=True)

    base_registro = []
    base_cantidades = []   # ✅ NUEVA


    for archivo in os.listdir(carpeta_mes):
        if archivo.lower().endswith(".xlsx"):
            ruta_archivo = os.path.join(carpeta_mes, archivo)
            revisar_acta(
                ruta_archivo,
                valores_referencia,
                anio_actual,
                mes_nombre,
                carpeta_salida_mes,
                base_registro,
                base_cantidades,          # ✅ NUEVO
                modo_critico=modo_critico
            )



    # =========================
    # Base general
    # =========================
    df_nuevo = pd.DataFrame(base_registro)
    if not df_nuevo.empty:
        df_nuevo = preparar_registro(df_nuevo, anio_actual, mes_nombre)

    base_path_excel = os.path.join(carpeta_datos, "base_general.xlsx")
    if os.path.exists(base_path_excel):
        df_existente = pd.read_excel(base_path_excel)
        if "anio" in df_existente.columns and "mes" in df_existente.columns:
            df_existente = df_existente[
                ~((df_existente["anio"] == anio_actual) & (df_existente["mes"] == mes_nombre))
            ]
        df_existente = preparar_registro(df_existente, anio_actual, mes_nombre)
        df_combinado = pd.concat([df_existente, df_nuevo], ignore_index=True) if not df_nuevo.empty else df_existente.copy()
    else:
        df_combinado = df_nuevo.copy()

    df_combinado.to_excel(base_path_excel, index=False)

    # =========================
    # Resumen mensual (existente)
    # =========================
    resumen_mes_path = os.path.join(carpeta_resumen_mes, f"resumen_{nombre_carpeta_mes}.xlsx")

    if not df_nuevo.empty:
        resumen_mes = (
            df_nuevo.groupby("contratista", dropna=False)
            .agg(
                Items_con_error=("item", "count"),
                Suma_valor_ajustado=("valor_ajustado", "sum")
            )
            .reset_index()
            .rename(columns={"contratista": "Contratista"})
            .sort_values(["Contratista"])
        )

        with pd.ExcelWriter(resumen_mes_path, engine="openpyxl") as writer:
            resumen_mes.to_excel(writer, sheet_name="RESUMEN", index=False)
            df_nuevo.to_excel(writer, sheet_name="REGISTRO", index=False)

            # =========================
            # ✅ NUEVO: Resumen de cantidades
            # =========================
            if base_cantidades:
                df_cant = pd.DataFrame(base_cantidades)

                df_cant_res = (
                    df_cant.groupby("contratista", dropna=False)[
                        ["Excavaciones", "Rellenos", "Concreto MR", "Concreto estampado"]
                    ]
                    .sum()
                    .reset_index()
                    .rename(columns={"contratista": "Contratista"})
                    .sort_values("Contratista")
                )

                df_cant_res.to_excel(writer, sheet_name="CANTIDADES", index=False)

    # =========================
    # Resumen global (existente)
    # =========================
    resumen_global_path = os.path.join(carpeta_resumen, "resumen_global.xlsx")
    if not df_combinado.empty:
        resumen_global = (
            df_combinado.groupby(["anio", "mes", "contratista"], dropna=False)
            .agg(
                Items_con_error=("item", "count"),
                Suma_valor_ajustado=("valor_ajustado", "sum")
            )
            .reset_index()
            .rename(columns={"anio": "Año", "mes": "Mes", "contratista": "Contratista"})
            .sort_values(["Año", "Mes", "Contratista"])
        )

        if os.path.exists(resumen_global_path):
            try:
                df_existente_reg = pd.read_excel(resumen_global_path, sheet_name="REGISTRO")
                df_existente_reg = preparar_registro(df_existente_reg, anio_actual, mes_nombre)
            except Exception:
                df_existente_reg = None
        else:
            df_existente_reg = None

        df_nuevo_reg = df_nuevo.copy() if not df_nuevo.empty else pd.DataFrame()
        if df_existente_reg is not None and not df_existente_reg.empty:
            df_registro_final = pd.concat([df_existente_reg, df_nuevo_reg], ignore_index=True)
        else:
            df_registro_final = df_nuevo_reg

        with pd.ExcelWriter(resumen_global_path, engine="openpyxl") as writer:
            resumen_global.to_excel(writer, sheet_name="RESUMEN", index=False)
            df_registro_final.to_excel(writer, sheet_name="REGISTRO", index=False)

    print(f"\n✅ Revisión completa de la carpeta '{nombre_carpeta_mes}'.")
    return {
        "anio": anio_actual,
        "mes": mes_nombre,
        "carpeta_mes": carpeta_mes,
        "carpeta_salida_mes": carpeta_salida_mes,
        "carpeta_datos": carpeta_datos,
        "carpeta_resumen_mes": carpeta_resumen_mes,
        "carpeta_resumen": carpeta_resumen,
    }


def correr_todos_los_meses(base_root: str, proyecto: str, valores_referencia: dict):
    resultados = []
    meses = listar_carpetas_mes(base_root, proyecto)

    if not meses:
        print(f"No se encontraron carpetas de mes en el proyecto '{proyecto}'.")
        return resultados

    for m in meses:
        nombre_carpeta_mes = m["carpeta"]
        print(f"\n=== Procesando carpeta de mes: {nombre_carpeta_mes} ===")
        info = correr_todo(base_root, proyecto, nombre_carpeta_mes, valores_referencia)
        resultados.append(info)

    print(f"\n✅ Procesados {len(resultados)} meses para el proyecto '{proyecto}'.")
    return resultados
