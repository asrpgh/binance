import streamlit as st
import pandas as pd
import libsql_experimental as libsql
import plotly.graph_objects as go
from streamlit_js_eval import streamlit_js_eval

# ---------- 1. Configuration & Secrets ----------
TURSO_URL = st.secrets.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = st.secrets.get("TURSO_AUTH_TOKEN", "")
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "admin123")

st.set_page_config(page_title="Binance P2P — True Candlesticks", layout="wide")

# ---------- 2. Persistent Login Logic ----------
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if st.session_state["authenticated"]:
        return True
    stored_password = streamlit_js_eval(js_expressions="localStorage.getItem('p2p_app_pwd')", key="get_ls")
    if stored_password == APP_PASSWORD:
        st.session_state["authenticated"] = True
        return True
    st.markdown("### 🔒 Acceso Restringido")
    pwd_input = st.text_input("Contraseña:", type="password")
    if st.button("Ingresar"):
        if pwd_input == APP_PASSWORD:
            streamlit_js_eval(js_expressions=f"localStorage.setItem('p2p_app_pwd', '{pwd_input}')", key="set_ls")
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrecto")
    return False

if not check_login():
    st.stop()

# ---------- 3. Data Fetching (Turso with OHLC Logic) ----------
@st.cache_data(ttl=300)
def get_p2p_data(seconds_limit):
    try:
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
        
        # This query uses Window Functions to identify the first and last prices in each bucket
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
                ) as bucket_open,
                FIRST_VALUE(market_median) OVER (
                    PARTITION BY (strftime('%s', datetime_utc) / ?) 
                    ORDER BY datetime_utc DESC
                ) as bucket_close
            FROM p2p_data
            WHERE datetime_utc >= date('now', '-1 month')
        )
        SELECT 
            interval_start,
            bucket_open AS [open],
            MAX(buy_max) AS [high],
            MIN(sell_min) AS [low],
            bucket_close AS [close],
            AVG(market_median) AS market_avg
        FROM bucketed
        GROUP BY interval_start
        ORDER BY interval_start DESC;
        """
        
        # We pass seconds_limit 4 times for the 4 '?' placeholders
        df = pd.read_sql_query(query, conn, params=(seconds_limit, seconds_limit, seconds_limit, seconds_limit))
        conn.close()
        
        if not df.empty:
            df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
            df["datetime_bo"] = df["interval_start"].dt.tz_convert("America/Caracas")
        return df
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# ---------- 4. UI ----------
st.sidebar.title("🛠️ Control")
if st.sidebar.button("Log Out"):
    streamlit_js_eval(js_expressions="localStorage.removeItem('p2p_app_pwd')", key="logout_js")
    st.session_state["authenticated"] = False
    st.rerun()

intervalo_map = {"5 Min": 300, "1 Hora": 3600, "Diario": 86400}
seleccion = st.sidebar.selectbox("Temporalidad:", list(intervalo_map.keys()), index=1)

df = get_p2p_data(intervalo_map[seleccion])

if df.empty:
    st.info("No hay datos.")
else:
    # Candlestick chart now uses TRUE Open and Close from the DB
    fig = go.Figure(data=[go.Candlestick(
        x=df['datetime_bo'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing_line_color='#26a69a', 
        decreasing_line_color='#ef5350'
    )])

    fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
