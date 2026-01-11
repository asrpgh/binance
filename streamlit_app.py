import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ---------- Config ----------
CSV_URL = "https://raw.githubusercontent.com/asrpgh/binance/main/data/p2p_ves_usdt.csv"
st.set_page_config(page_title="Binance P2P — VES → USDT", layout="wide")
st.title("💵 Binance P2P — VES → USDT (Velas Dinámicas)")

# ---------- Cargar y preparar datos ----------
@st.cache_data(ttl=60)
def load_and_prepare(url):
    try:
        df = pd.read_csv(url)
    except:
        df = pd.DataFrame()

    try:
        dflocal = pd.read_csv('./data/p2p_ves_usdt.csv')
        if dflocal.shape[0] > df.shape[0]:
            df = dflocal
    except FileNotFoundError:
        pass

    posibles = ["datetime_utc", "timestamp", "datetime", "date", "time"]
    dtcol = next((c for c in posibles if c in df.columns), None)

    if dtcol is None:
        raise ValueError("No se encontró columna de fecha/hora.")

    df[dtcol] = pd.to_datetime(df[dtcol], errors="coerce", utc=True)
    df = df.dropna(subset=[dtcol]).reset_index(drop=True)
    df["datetime_bo"] = df[dtcol].dt.tz_convert("America/Caracas")

    # Filtro 30 días (ajustable si quieres más historial)
    last_date_available = df["datetime_bo"].max()
    one_month_ago = last_date_available - pd.Timedelta(days=30)
    df = df[df["datetime_bo"] >= one_month_ago].copy()

    df["Fecha"] = df["datetime_bo"].dt.date
    df["Hora"] = df["datetime_bo"].dt.strftime("%H:%M:%S")

    numeric_cols = ["buy_median", "sell_median", "market_median"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    return df

try:
    df = load_and_prepare(CSV_URL)
except Exception as e:
    st.error(f"Error cargando CSV: {e}")
    st.stop()

# ---------- Sidebar: Selector de Temporalidad ----------
st.sidebar.header("📊 Configuración de Velas")

# Opciones de tiempo usando offsets de Pandas
intervalo_map = {
    "15 Minutos": "15T",
    "1 Hora": "1H",
    "4 Horas": "4H",
    "Diario": "D",
    "Semanal": "W"
}

seleccion = st.sidebar.selectbox("Seleccione Temporalidad:", list(intervalo_map.keys()), index=1)
freq = intervalo_map[seleccion]

# Filtro de fechas
min_date_in_df = df["datetime_bo"].min().date()
max_date_in_df = df["datetime_bo"].max().date()

start_date, end_date = st.sidebar.date_input(
    "📅 Rango de fechas:",
    [min_date_in_df, max_date_in_df],
    min_value=min_date_in_df,
    max_value=max_date_in_df
)

# ---------- Procesamiento ----------
mask = (df["datetime_bo"].dt.date >= start_date) & (df["datetime_bo"].dt.date <= end_date)
df_filtered = df.loc[mask].copy().sort_values("datetime_bo")

if df_filtered.empty:
    st.info("No hay datos en el rango seleccionado.")
else:
    # Generar OHLC (Open, High, Low, Close)
    ohlc_df = df_filtered.set_index("datetime_bo")["market_median"].resample(freq).ohlc()
    ohlc_df = ohlc_df.dropna() # Quitar huecos sin transacciones

    # ---------- Gráfico de Velas ----------
    st.subheader(f"📈 Gráfico {seleccion} (Market Median)")
    
    fig = go.Figure(data=[go.Candlestick(
        x=ohlc_df.index,
        open=ohlc_df['open'],
        high=ohlc_df['high'],
        low=ohlc_df['low'],
        close=ohlc_df['close'],
        increasing_line_color='#00ffad', # Verde Neón
        decreasing_line_color='#ff3e3e', # Rojo Neón
        name="Market Median"
    )])

    fig.update_layout(
        xaxis_title="Fecha y Hora",
        yaxis_title="VES/USDT",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=600,
        margin=dict(l=20, r=20, t=30, b=20)
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # --- Métricas Rápidas ---
    df_metrics = df_filtered.sort_values("datetime_bo", ascending=False)
    m1, m2, m3 = st.columns(3)
    
    last_val = df_metrics["market_median"].iloc[0]
    prev_val = df_metrics["market_median"].iloc[1] if len(df_metrics) > 1 else last_val
    delta = ((last_val - prev_val) / prev_val) * 100

    m1.metric("Último Precio", f"{last_val:.3f} VES", f"{delta:.2f}%")
    m2.metric("Precio Máximo", f"{df_metrics['market_median'].max():.3f} VES")
    m3.metric("Precio Mínimo", f"{df_metrics['market_median'].min():.3f} VES")

    # --- Tabla ---
    with st.expander("Ver tabla de datos raw"):
        st.dataframe(df_metrics[["Fecha", "Hora", "market_median"]], use_container_width=True)

st.caption(f"Visualizando temporalidad **{seleccion}**. Datos actualizados según el último registro disponible.")
