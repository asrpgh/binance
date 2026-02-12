import streamlit as st
import pandas as pd
import libsql_experimental as libsql
import plotly.graph_objects as go
from streamlit_js_eval import streamlit_js_eval
from datetime import datetime, timedelta

# ---------- 1. Config & Secrets ----------
TURSO_URL = st.secrets.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = st.secrets.get("TURSO_AUTH_TOKEN", "")
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "admin123")

st.set_page_config(page_title="Binance P2P — Master Dashboard", layout="wide")

# ---------- 2. Persistent Login Logic ----------
def check_login():
    # If session is already authenticated, don't do anything
    if st.session_state.get("authenticated"):
        return True

    # Attempt to read from Local Storage
    # We use a unique key for the component to ensure it triggers correctly
    stored_password = streamlit_js_eval(js_expressions="localStorage.getItem('p2p_app_pwd')", key="ls_reader")
    
    # If the JS hasn't returned yet, we show a spinner and stop briefly
    if stored_password is None:
        st.spinner("Verificando credenciales...")
        return False

    # Validation logic
    if stored_password == APP_PASSWORD:
        st.session_state["authenticated"] = True
        st.rerun() # Refresh to show the app immediately
        return True

    # Show Login UI if no match or empty storage
    st.title("🔒 Acceso Restringido")
    pwd_input = st.text_input("Introduce la contraseña maestra:", type="password")
    
    if st.button("Ingresar"):
        if pwd_input == APP_PASSWORD:
            # Persistent set in JS
            streamlit_js_eval(js_expressions=f"localStorage.setItem('p2p_app_pwd', '{pwd_input}')", key="ls_writer")
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    
    return False

# Execute Login Check
if not check_login():
    st.stop()

# ---------- 3. Data Engine (True OHLC) ----------
@st.cache_data(ttl=300)
def get_p2p_data(seconds_limit):
    try:
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
        
        # This query uses Window Functions to pick the absolute FIRST and LAST 
        # market_median records within each time bucket.
        query = """
        WITH bucketed AS (
            SELECT 
                datetime((strftime('%s', datetime_utc) / ?) * ?, 'unixepoch') AS interval_start,
                market_median,
                buy_max,
                sell_min,
                datetime_utc,
                FIRST_VALUE(market_median) OVER (
                    PARTITION BY (strftime('%s', datetime_utc) / ?) 
                    ORDER BY datetime_utc ASC
                ) as b_open,
                FIRST_VALUE(market_median) OVER (
                    PARTITION BY (strftime('%s', datetime_utc) / ?) 
                    ORDER BY datetime_utc DESC
                ) as b_close
            FROM p2p_data
            WHERE datetime_utc >= date('now', '-1 month')
        )
        SELECT 
            interval_start,
            b_open AS [open],
            MAX(buy_max) AS [high],
            MIN(sell_min) AS [low],
            b_close AS [close],
            AVG(market_median) AS market_avg
        FROM bucketed
        GROUP BY interval_start
        ORDER BY interval_start DESC;
        """
        
        # Pass seconds_limit 4 times for the 4 '?' markers in the query
        df = pd.read_sql_query(query, conn, params=(seconds_limit, seconds_limit, seconds_limit, seconds_limit))
        conn.close()
        
        if not df.empty:
            df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
            df["datetime_bo"] = df["interval_start"].dt.tz_convert("America/Caracas")
        return df
    except Exception as e:
        st.error(f"Error Turso: {e}")
        return pd.DataFrame()

# ---------- 4. Sidebar & Filtering ----------
st.sidebar.title("⚙️ Configuración")

# Logout logic
if st.sidebar.button("Cerrar Sesión"):
    streamlit_js_eval(js_expressions="localStorage.removeItem('p2p_app_pwd')", key="ls_logout")
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.divider()

st.sidebar.divider()

# Temporality Options
intervalo_map = {
    "5 Minutos": 300,
    "30 Minutos": 1800,
    "1 Hora": 3600,
    "4 Horas": 14400,
    "Diario": 86400,
    "Semanal": 604800
}
seleccion = st.sidebar.selectbox("Temporalidad de Velas:", list(intervalo_map.keys()), index=2)
seconds = intervalo_map[seleccion]

# Load base data (Last 30 days from DB)
df = get_p2p_data(seconds)

if not df.empty:
    # Date Range Picker
    min_date = df["datetime_bo"].min().date()
    max_date = df["datetime_bo"].max().date()

    start_date, end_date = st.sidebar.date_input(
        "📅 Rango de fechas:",
        [min_date, max_date],
        min_value=min_date,
        max_value=max_date
    )

    # Filter DataFrame by Sidebar Selection
    mask = (df["datetime_bo"].dt.date >= start_date) & (df["datetime_bo"].dt.date <= end_date)
    df_filtered = df.loc[mask].copy().sort_values("datetime_bo", ascending=False)
else:
    df_filtered = pd.DataFrame()

# ---------- 5. Dashboard View ----------
st.title("💵 Binance P2P — VES/USDT")

if df_filtered.empty:
    st.info("No hay datos disponibles para el rango o temporalidad seleccionada.")
else:
    # Summary Metrics
    latest = df_filtered.iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Último Cierre", f"{latest['close']:.3f} VES")
    m2.metric("Máximo (Rango)", f"{df_filtered['high'].max():.3f} VES")
    m3.metric("Mínimo (Rango)", f"{df_filtered['low'].min():.3f} VES")

    # Tabs
    tab1, tab2 = st.tabs(["🕯️ Gráfico de Velas (OHLC)", "📊 Datos Agregados"])

    with tab1:
        fig = go.Figure(data=[go.Candlestick(
            x=df_filtered['datetime_bo'],
            open=df_filtered['open'],
            high=df_filtered['high'],
            low=df_filtered['low'],
            close=df_filtered['close'],
            increasing_line_color='#26a69a', 
            decreasing_line_color='#ef5350'
        )])

        fig.update_layout(
            template="plotly_dark",
            height=650,
            xaxis_rangeslider_visible=False,
            margin=dict(t=30, b=0, l=10, r=10),
            yaxis_title="VES/USDT"
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Registros Detallados")
        st.dataframe(df_filtered, use_container_width=True)

st.sidebar.divider()
st.sidebar.caption(f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")
