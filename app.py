# app.py
import os
import shutil
import tempfile

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st

# =========================
# CONFIG STREAMLIT
# =========================
st.set_page_config(page_title="Curva de calibres - Promoción de flores", layout="wide")

st.title("Curva de calibres (corregido por cada evaluación de cada baya)")
st.caption("Dashboard dinámico (filtros: ETAPA, CAMPO, VARIEDAD, CONDICIÓN y PROMOCIÓN).")

# =========================
# PARAMETROS / COLUMNAS
# =========================
CAL_COL = "CALIBRE (mm)"
MUESTRA_COL = "N° MUESTRA"

# =========================
# RUTA LOCAL (SOLO PARTE 2)
# =========================
parte_2_2025_local = r"C:\Users\JeinerJhoelLunaYacup\OneDrive - Fruitist Holdings Inc\PE-Gerencia de Gestion - 01. Harvest Forecasts\02. Data\Promoción de flores\BD_PROMOCIÓN DE FLORES_2025.2 PARTE 2.xlsx"

# =========================
# RUTA EN REPO (SOLO PARTE 2)
# =========================
parte_2_repo = "data/BD_PROMOCIÓN DE FLORES_2025.2 PARTE 2.xlsx"

# =========================
# LECTURA ROBUSTA (ONE DRIVE SAFE)
# =========================
def read_excel_safe(path_or_file):
    """
    Lee un Excel de forma robusta.
    - Si es una ruta (str) intenta copiar a temporal antes de leer (evita PermissionError de OneDrive).
    - Si es un objeto tipo file-like (por ejemplo st.file_uploader) lo lee directo.
    """
    if hasattr(path_or_file, "read") or hasattr(path_or_file, "getbuffer"):
        return pd.read_excel(path_or_file)

    path = str(path_or_file)
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    tmp_dir = tempfile.mkdtemp(prefix="st_excel_")
    tmp_path = os.path.join(tmp_dir, os.path.basename(path))
    shutil.copy2(path, tmp_path)

    return pd.read_excel(tmp_path)

# =========================
# CARGA DE DATOS (SOLO 1 ARCHIVO)
# =========================
@st.cache_data(show_spinner=True)
def cargar_data():
    # 1) Intentar LOCAL
    if os.path.exists(parte_2_2025_local):
        p = parte_2_2025_local
        modo = "LOCAL (ruta C:/... / OneDrive)"
    # 2) Si no existe local, usar REPO (Streamlit Cloud)
    elif os.path.exists(parte_2_repo):
        p = parte_2_repo
        modo = "CLOUD/REPO (carpeta data/ del repositorio)"
    else:
        raise FileNotFoundError(
            "No se encontró el Excel (PARTE 2) ni en LOCAL ni en el REPO.\n\n"
            f"LOCAL:\n- {parte_2_2025_local}\n\n"
            f"REPO:\n- {parte_2_repo}\n"
        )

    df_final = read_excel_safe(p).iloc[:, :12].copy()

    # Tipos
    df_final["FECHA"] = pd.to_datetime(df_final["FECHA"], errors="coerce")
    df_final["SEMANA"] = pd.to_numeric(df_final["SEMANA"], errors="coerce")

    return df_final, modo

try:
    df, modo_carga = cargar_data()
except Exception as e:
    st.error("❌ Error cargando archivos.")
    st.exception(e)
    st.stop()

st.success(f"✅ Data cargada: {df.shape} | Modo: {modo_carga}")

# =========================
# VALIDACION DE COLUMNAS
# =========================
REQ = ["ETAPA", "CAMPO", "TURNO", "LOTE", "VARIEDAD", "PROMOCION", MUESTRA_COL, "FECHA", CAL_COL, "CONDICION"]
falt = [c for c in REQ if c not in df.columns]
if falt:
    st.error(f"Faltan columnas requeridas: {falt}")
    st.stop()

# =========================
# UTILS
# =========================
def opciones_columna(df_base, col):
    return sorted(df_base[col].dropna().unique().tolist())

def etiqueta_filtro(nombre, valores):
    if not valores:
        return ""
    if len(valores) == 1:
        return f"{nombre} {valores[0]}"
    return f"{nombre} (múltiples)"

def construir_serie_por_orden(df_filtrado: pd.DataFrame) -> pd.DataFrame:
    d = df_filtrado.copy()

    d = d.dropna(subset=["ETAPA","CAMPO","TURNO","LOTE","VARIEDAD","PROMOCION",MUESTRA_COL,"FECHA",CAL_COL])
    if d.empty:
        return pd.DataFrame(columns=["PROMOCION","EVAL_DIA","PROMO_MEDIA_MM"])

    d["BAYA_ID"] = (
        d["ETAPA"].astype(str) + "|" +
        d["CAMPO"].astype(str) + "|" +
        d["TURNO"].astype(str) + "|" +
        d["LOTE"].astype(str) + "|" +
        d["VARIEDAD"].astype(str) + "|" +
        d["PROMOCION"].astype(str) + "|" +
        d[MUESTRA_COL].astype(str)
    )

    d = (
        d.groupby(["PROMOCION","BAYA_ID","FECHA"], as_index=False)[CAL_COL]
         .mean()
         .sort_values(["PROMOCION","BAYA_ID","FECHA"])
    )

    d["EVAL_DIA"] = d.groupby(["PROMOCION","BAYA_ID"]).cumcount() + 1

    pv = d.pivot_table(
        index=["PROMOCION","EVAL_DIA"],
        columns="BAYA_ID",
        values=CAL_COL,
        aggfunc="mean"
    ).sort_index()

    out = []
    for promo, g in pv.groupby(level=0):
        g2 = g.droplevel(0)
        max_eval = int(g2.index.max())
        g2 = g2.reindex(range(1, max_eval + 1)).ffill()
        g2.index.name = "EVAL_DIA"
        g2["PROMOCION"] = promo
        out.append(g2.reset_index())

    if not out:
        return pd.DataFrame(columns=["PROMOCION","EVAL_DIA","PROMO_MEDIA_MM"])

    pv2 = pd.concat(out, ignore_index=True)

    cols_bayas = [c for c in pv2.columns if c not in ["PROMOCION","EVAL_DIA"]]
    pv2["PROMO_MEDIA_MM"] = pv2[cols_bayas].mean(axis=1, skipna=True)

    return pv2[["PROMOCION","EVAL_DIA","PROMO_MEDIA_MM"]]

# =========================
# FILTROS (SIDEBAR)
# =========================
st.sidebar.header("Filtros")

etapa_opts = opciones_columna(df, "ETAPA")
campo_opts = opciones_columna(df, "CAMPO")
variedad_opts = opciones_columna(df, "VARIEDAD")
condicion_opts = opciones_columna(df, "CONDICION")

etapa = st.sidebar.multiselect("Etapa", options=etapa_opts, default=[])
campo = st.sidebar.multiselect("Campo", options=campo_opts, default=[])
variedad = st.sidebar.multiselect("Variedad", options=variedad_opts, default=[])
condicion = st.sidebar.multiselect("Condición", options=condicion_opts, default=[])

mask = pd.Series(True, index=df.index)
if etapa:
    mask &= df["ETAPA"].isin(etapa)
if campo:
    mask &= df["CAMPO"].isin(campo)
if variedad:
    mask &= df["VARIEDAD"].isin(variedad)
if condicion:
    mask &= df["CONDICION"].isin(condicion)

df_f = df[mask].copy()
promos_opts = sorted(df_f["PROMOCION"].dropna().unique().tolist()) if not df_f.empty else []

with st.sidebar.expander("Promoción (múltiple)", expanded=True):
    promociones = st.multiselect("Selecciona promociones", options=promos_opts, default=[])

df_filtrado = df_f[df_f["PROMOCION"].isin(promociones)].copy() if promociones else df_f.copy()

if df_filtrado.empty:
    st.warning("⚠ No hay datos para los filtros seleccionados.")
    st.stop()

serie = construir_serie_por_orden(df_filtrado)
if serie.empty:
    st.warning("⚠ No hay datos suficientes para construir la serie por orden de evaluación.")
    st.stop()

# =========================
# GRAFICOS
# =========================
col1, col2 = st.columns(2)

with col1:
    st.subheader("Curva por día (EVAL_DIA)")

    fig1 = plt.figure(figsize=(12, 6))
    max_x = 0

    for promo, sub in serie.groupby("PROMOCION"):
        sub = sub.sort_values("EVAL_DIA").dropna(subset=["PROMO_MEDIA_MM"])
        if sub.empty:
            continue

        x = sub["EVAL_DIA"].astype(int).values
        y = sub["PROMO_MEDIA_MM"].values
        max_x = max(max_x, x.max())

        plt.plot(x, y, marker="o", label=f"Promoción {promo}")
        for xi, yi in zip(x, y):
            plt.text(xi, yi, f"{yi:.2f}", fontsize=8, ha="center", va="bottom")

    plt.xlabel("Día de evaluación (1 = 1ra evaluación de cada baya)")
    plt.ylabel("Promedio de calibre (mm) - toda la promoción (baya numerada)")

    titulo = "Curva de calibre por día (orden de evaluación por baya)"
    filtros = [
        etiqueta_filtro("Etapa", etapa),
        etiqueta_filtro("Campo", campo),
        etiqueta_filtro("Variedad", variedad),
        etiqueta_filtro("Condición", condicion),
    ]
    filtros = [f for f in filtros if f]
    if filtros:
        titulo += " - " + ", ".join(filtros)

    plt.title(titulo)
    plt.grid(True)

    if max_x > 0:
        plt.xlim(0.5, max_x + 0.5)
        plt.xticks(range(1, int(max_x) + 1))

    plt.legend()
    plt.tight_layout()
    st.pyplot(fig1)

with col2:
    st.subheader("Curva por semana (SEMANA_REL)")

    serie_sem = serie.copy()
    serie_sem["SEMANA_REL"] = ((serie_sem["EVAL_DIA"].astype(int) - 1) // 7) + 1

    serie_sem = (
        serie_sem.sort_values(["PROMOCION", "SEMANA_REL", "EVAL_DIA"])
                 .groupby(["PROMOCION", "SEMANA_REL"], as_index=False)
                 .first()
    )

    fig2 = plt.figure(figsize=(12, 6))
    max_x = 0

    for promo, sub in serie_sem.groupby("PROMOCION"):
        sub = sub.sort_values("SEMANA_REL").dropna(subset=["PROMO_MEDIA_MM"])
        if sub.empty:
            continue

        x = sub["SEMANA_REL"].astype(int).values
        y = sub["PROMO_MEDIA_MM"].values
        max_x = max(max_x, x.max())

        plt.plot(x, y, marker="o", label=f"Promoción {promo}")
        for xi, yi in zip(x, y):
            plt.text(xi, yi, f"{yi:.2f}", fontsize=8, ha="center", va="bottom")

    plt.xlabel("Semana relativa (1 = eval 1–7, 2 = 8–14, ...)")
    plt.ylabel("Promedio de calibre (mm) - toda la promoción")

    titulo = "Curva de calibre por semana (desde orden de evaluación por baya)"
    filtros = [
        etiqueta_filtro("Etapa", etapa),
        etiqueta_filtro("Campo", campo),
        etiqueta_filtro("Variedad", variedad),
        etiqueta_filtro("Condición", condicion),
    ]
    filtros = [f for f in filtros if f]
    if filtros:
        titulo += " - " + ", ".join(filtros)

    plt.title(titulo)
    plt.grid(True)

    if max_x > 0:
        plt.xlim(0.5, max_x + 0.5)
        plt.xticks(range(1, int(max_x) + 1))

    plt.legend()
    plt.tight_layout()
    st.pyplot(fig2)

with st.expander("Ver serie calculada (PROMOCION, EVAL_DIA, PROMO_MEDIA_MM)"):
    st.dataframe(
        serie.sort_values(["PROMOCION", "EVAL_DIA"]).reset_index(drop=True),
        use_container_width=True
    )
