import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

# ---------- Config ----------
CSV_URL = "https://raw.githubusercontent.com/asrpgh/binance/main/data/p2p_ves_usdt.csv"
st.set_page_config(page_title="Binance P2P — VES → USDT", layout="wide")
st.title("💵 Binance P2P — VES → USDT")

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

    # Filtro 30 días
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

# ---------- Sidebar ----------
st.sidebar.header("⚙️ Configuración")

intervalo_map = {
    "5 Minutos": "5T",
    "30 Minutos": "30T",
    "1 Hora": "1H",
    "4 Horas": "4H",
    "Diario": "D",
    "Semanal": "W"
}
seleccion = st.sidebar.selectbox("Temporalidad de Velas:", list(intervalo_map.keys()), index=2)
freq = intervalo_map[seleccion]

min_date_in_df = df["datetime_bo"].min().date()
max_date_in_df = df["datetime_bo"].max().date()

start_date, end_date = st.sidebar.date_input(
    "📅 Rango de fechas:",
    [min_date_in_df, max_date_in_df],
    min_value=min_date_in_df,
    max_value=max_date_in_df
)

# Filtrar datos
mask = (df["datetime_bo"].dt.date >= start_date) & (df["datetime_bo"].dt.date <= end_date)
df_filtered = df.loc[mask].copy().sort_values("datetime_bo")

if df_filtered.empty:
    st.info("No hay datos en el rango seleccionado.")
else:
    # --- Lógica de Velas (OHLC) con Apertura Forzada ---
    ohlc_df = df_filtered.set_index("datetime_bo")["market_median"].resample(freq).ohlc().dropna()
    
    # Forzar que Open[n] = Close[n-1] para evitar gaps visuales
    ohlc_df['open'] = ohlc_df['close'].shift(1).fillna(ohlc_df['open'])

    # --- Layout con Pestañas ---
    tab1, tab2, tab3 = st.tabs(["🕯️ Velas (Análisis)", "📈 Línea (Tendencia)", "📊 Datos"])

    with tab1:
        st.subheader(f"Gráfico de Velas Continuo ({seleccion})")
        fig_candle = go.Figure(data=[go.Candlestick(
            x=ohlc_df.index,
            open=ohlc_df['open'], high=ohlc_df['high'],
            low=ohlc_df['low'], close=ohlc_df['close'],
            increasing_line_color='#26a69a', decreasing_line_color='#ef5350',
            name="VES/USDT"
        )])
        fig_candle.update_layout(
            template="plotly_dark", 
            height=600, 
            xaxis_rangeslider_visible=False,
            margin=dict(t=0, b=0)
        )
        st.plotly_chart(fig_candle, use_container_width=True)

    with tab2:
        st.subheader("Tendencia de Mercado Continua")
        fig_line = px.line(
            df_filtered,
            x="datetime_bo",
            y="market_median",
            labels={"datetime_bo": "Fecha (VET)", "market_median": "VES/USDT"},
            template="plotly_dark"
        )
        fig_line.update_traces(line_color='#00d1ff')
        fig_line.update_layout(height=600)
        st.plotly_chart(fig_line, use_container_width=True)

    with tab3:
        # Métricas resumidas
        df_metrics = df_filtered.sort_values("datetime_bo", ascending=False)
        m1, m2, m3 = st.columns(3)
        last_val = df_metrics["market_median"].iloc[0]
        m1.metric("Precio Actual", f"{last_val:.3f} VES")
        m2.metric("Máximo Periodo", f"{df_metrics['market_median'].max():.3f} VES")
        m3.metric("Mínimo Periodo", f"{df_metrics['market_median'].min():.3f} VES")
        
        st.subheader("Registros Raw (5m)")
        st.dataframe(df_metrics[["Fecha", "Hora", "market_median", "buy_median", "sell_median"]], use_container_width=True)

st.caption("Nota: El gráfico de velas utiliza 'Apertura Forzada' para mantener la continuidad visual.")
