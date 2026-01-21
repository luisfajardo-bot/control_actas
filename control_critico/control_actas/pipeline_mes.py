import os
import pandas as pd
import inspect

from .meses import parsear_anio_mes_desde_carpeta
from .excel_utils import preparar_registro
from .procesar_actas import revisar_acta
from .meses import listar_carpetas_mes


def correr_todo(
    base_root: str,
    proyecto: str,
    nombre_carpeta_mes: str,
    valores_referencia: dict | None = None,   # en crítico se ignora
    modo_critico: bool = True,                # por defecto True en crítico
):

    base_path = os.path.join(base_root, proyecto, "control_actas")

    anio_actual, mes_nombre = parsear_anio_mes_desde_carpeta(nombre_carpeta_mes)
    print(f"[CRITICO] Año detectado: {anio_actual}, Mes detectado: {mes_nombre}")

    carpeta_mes = os.path.join(base_path, "actas", nombre_carpeta_mes)
    carpeta_salida_mes = os.path.join(base_path, "salidas", nombre_carpeta_mes)
    carpeta_datos = os.path.join(base_path, "datos")
    carpeta_resumen = os.path.join(base_path, "resumen")
    carpeta_resumen_mes = os.path.join(carpeta_resumen, nombre_carpeta_mes)

    for ruta in [carpeta_mes, carpeta_salida_mes, carpeta_datos, carpeta_resumen, carpeta_resumen_mes]:
        os.makedirs(ruta, exist_ok=True)

    base_registro: list[dict] = []
    base_cantidades: list[dict]=[]

    if not os.path.isdir(carpeta_mes):
        raise FileNotFoundError(f"No existe la carpeta de actas: {carpeta_mes}")

    for archivo in os.listdir(carpeta_mes):
        if archivo.lower().endswith(".xlsx"):
            ruta_archivo = os.path.join(carpeta_mes, archivo)

            # Armamos kwargs solo con lo que la función acepta
            sig = inspect.signature(revisar_acta)
            params = sig.parameters

            kwargs = dict(
                path_archivo=ruta_archivo,
                anio_actual=anio_actual,
                mes_nombre=mes_nombre,
                carpeta_salida_mes=carpeta_salida_mes,
                base_registro=base_registro,
            )

            # ✅ nuevo: solo si existe en esa versión
            if "base_cantidades" in params:
                kwargs["base_cantidades"] = base_cantidades

            # Solo si existe en esa versión de revisar_acta
            if "modo_critico" in params:
                kwargs["modo_critico"] = True

            if "valores_referencia" in params:
                kwargs["valores_referencia"] = {}  # en crítico se ignora (si existiera)

            revisar_acta(**kwargs)

    df_nuevo = pd.DataFrame(base_registro)
    if not df_nuevo.empty:
        df_nuevo = preparar_registro(df_nuevo, anio_actual, mes_nombre)

    # Guardar/actualizar base_general.xlsx igual que normal (si quieres mantener historia)
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

    # Resumen mensual (opcional, pero consistente con normal)
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
        resumen_mes_path = os.path.join(carpeta_resumen_mes, f"resumen_{nombre_carpeta_mes}.xlsx")
        with pd.ExcelWriter(resumen_mes_path, engine="openpyxl") as writer:
            resumen_mes.to_excel(writer, sheet_name="RESUMEN", index=False)
            df_nuevo.to_excel(writer, sheet_name="REGISTRO", index=False)
            # ✅ NUEVO: hoja CANTIDADES (si existe info)
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

    print(f"\n✅ [CRITICO] Revisión completa de '{nombre_carpeta_mes}'.")
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
