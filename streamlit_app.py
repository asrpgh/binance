# streamlit_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# ---------- Config ----------
CSV_URL = "https://raw.githubusercontent.com/asrpgh/binance/main/data/p2p_ves_usdt.csv"
st.set_page_config(page_title="Binance P2P — VES → USDT", layout="wide")
st.title("💵 Binance P2P — VES → USDT (Últimos 30 días)")

# ---------- Cargar y preparar datos (robusto) ----------
@st.cache_data(ttl=60)
def load_and_prepare(url):
    df = pd.read_csv(url)
    
    # Intento de cargar local si existe, similar a tu lógica original
    try:
        dflocal = pd.read_csv('./data/p2p_ves_usdt.csv')
        if dflocal.shape[0] > df.shape[0]:
            df = dflocal
    except FileNotFoundError:
        pass

    # buscar columna de fecha/hora
    posibles = ["datetime_utc", "timestamp", "datetime", "date", "time"]
    dtcol = next((c for c in posibles if c in df.columns), None)

    if dtcol is None:
        raise ValueError(f"No se encontró columna de fecha/hora.")

    # convertir a datetime
    df[dtcol] = pd.to_datetime(df[dtcol], errors="coerce", utc=True)
    df = df.dropna(subset=[dtcol]).reset_index(drop=True)

    # generar columna con hora Venezuela
    df["datetime_bo"] = df[dtcol].dt.tz_convert("America/Caracas")

    # --- FILTRO DE ÚLTIMO MES ---
    # Calculamos el umbral de hace 30 días respecto al dato más reciente
    last_date_available = df["datetime_bo"].max()
    one_month_ago = last_date_available - pd.Timedelta(days=30)
    df = df[df["datetime_bo"] >= one_month_ago].copy()
    # ----------------------------

    # separar fecha y hora
    df["Fecha"] = df["datetime_bo"].dt.date
    df["Hora"] = df["datetime_bo"].dt.strftime("%H:%M:%S")

    numeric_cols = ["buy_min", "buy_max", "buy_median", "buy_avg",
                    "sell_min", "sell_max", "sell_median", "sell_avg",
                    "market_median"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = pd.NA

    return df

# cargar
try:
    df = load_and_prepare(CSV_URL)
except Exception as e:
    st.error(f"Error cargando CSV: {e}")
    st.stop()

# ---------- Filtro de fechas (restringido al último mes) ----------
min_date_in_df = df["datetime_bo"].min().date()
max_date_in_df = df["datetime_bo"].max().date()

start_date, end_date = st.date_input(
    "📅 Filtrar rango (dentro del último mes):",
    [min_date_in_df, max_date_in_df],
    min_value=min_date_in_df,
    max_value=max_date_in_df
)

mask = (df["datetime_bo"].dt.date >= start_date) & (df["datetime_bo"].dt.date <= end_date)
df_filtered = df.loc[mask].copy().sort_values("datetime_bo", ascending=False)

if df_filtered.empty:
    st.info("No hay datos en el rango seleccionado.")
else:
    # --- Gráfico ---
    st.subheader("📈 Tendencia (Market Median)")
    fig = px.line(
        df_filtered,
        x="datetime_bo",
        y="market_median",
        title="Tipo de cambio últimos 30 días",
        labels={"datetime_bo": "Fecha (VET)", "market_median": "VES/USDT"},
        markers=True
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Métricas ---
    col1, col2, col3 = st.columns(3)
    with col1:
        # El primer elemento de df_filtered (ordenado desc) es el más reciente
        last_val = df_filtered["market_median"].iloc[0] if not df_filtered.empty else None
        st.metric("Último valor", f"{last_val:.3f} VES" if pd.notna(last_val) else "N/D")
    with col2:
        max_val = df_filtered["market_median"].max()
        st.metric("Máximo (Mes)", f"{max_val:.3f} VES")
    with col3:
        min_val = df_filtered["market_median"].min()
        st.metric("Mínimo (Mes)", f"{min_val:.3f} VES")

    # --- Alertas (Basadas en el DF filtrado de 30 días) ---
    st.subheader("💡 Alertas y Tendencia")
    
    # Lógica de tendencia
    if len(df_filtered) >= 2:
        # Tomamos los dos puntos más recientes en el tiempo (index 0 es el más nuevo)
        recent = df_filtered["market_median"].dropna().values
        if len(recent) >= 2:
            if recent[0] > recent[1]:
                st.success("📈 Tendencia: AL ALZA")
            elif recent[0] < recent[1]:
                st.warning("📉 Tendencia: A LA BAJA")

    # Alerta promedio 7 días (siempre comparando contra la data cargada)
    avg_7 = df[df["datetime_bo"] >= (df["datetime_bo"].max() - pd.Timedelta(days=7))]["market_median"].mean()
    if pd.notna(last_val) and last_val < avg_7:
        st.info(f"💡 Oportunidad: El precio actual está por debajo del promedio de la última semana ({avg_7:.3f}).")

    # --- Tabla ---
    st.subheader("📊 Registros")
    cols_mostrar = ["Fecha", "Hora", "buy_median", "sell_median", "market_median"]
    cols_existentes = [c for c in cols_mostrar if c in df_filtered.columns]
    st.dataframe(df_filtered[cols_existentes], use_container_width=True)

st.caption("Nota: La aplicación solo procesa los últimos 30 días de datos para optimizar el rendimiento.")
