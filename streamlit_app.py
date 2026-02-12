import streamlit as st
import pandas as pd
import libsql_experimental as libsql
import plotly.graph_objects as go
from streamlit_js_eval import streamlit_js_eval
from datetime import datetime

# ---------- 1. Config & Secrets ----------
TURSO_URL = st.secrets.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = st.secrets.get("TURSO_AUTH_TOKEN", "")
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "admin123")

st.set_page_config(page_title="Binance P2P Dashboard", layout="wide")

# ---------- 2. Simplified Persistent Login ----------

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Read from Local Storage
# This will return None on first run, then the value on the second run
stored_pwd = streamlit_js_eval(js_expressions="localStorage.getItem('p2p_app_pwd')", key="ls_check")

# Auto-auth if stored matches secret
if not st.session_state["authenticated"] and stored_pwd == APP_PASSWORD:
    st.session_state["authenticated"] = True
    st.rerun()

# If NOT authenticated, show the login form and STOP the rest of the script
if not st.session_state["authenticated"]:
    st.title("🔒 Acceso Restringido")
    
    pwd_input = st.text_input("Introduce la contraseña maestra:", type="password")
    if st.button("Ingresar"):
        if pwd_input == APP_PASSWORD:
            # Write to Local Storage
            streamlit_js_eval(js_expressions=f"localStorage.setItem('p2p_app_pwd', '{pwd_input}')", key="ls_save")
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    
    # Very important: we stop here so the dashboard doesn't load underneath
    st.stop()

# ---------- 3. The Dashboard (Only runs if authenticated) ----------

@st.cache_data(ttl=300)
def get_p2p_data(seconds_limit):
    try:
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
        query = """
        WITH bucketed AS (
            SELECT 
                datetime((strftime('%s', datetime_utc) / ?) * ?, 'unixepoch') AS interval_start,
                market_median, buy_max, sell_min, datetime_utc,
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
            b_open AS [open], MAX(buy_max) AS [high],
            MIN(sell_min) AS [low], b_close AS [close],
            AVG(market_median) AS market_avg
        FROM bucketed
        GROUP BY interval_start
        ORDER BY interval_start DESC;
        """
        df = pd.read_sql_query(query, conn, params=(seconds_limit, seconds_limit, seconds_limit, seconds_limit))
        conn.close()
        
        if not df.empty:
            df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
            df["datetime_bo"] = df["interval_start"].dt.tz_convert("America/Caracas")
        return df
    except Exception as e:
        st.error(f"Error Turso: {e}")
        return pd.DataFrame()

# Sidebar
st.sidebar.title("⚙️ Configuración")
if st.sidebar.button("Cerrar Sesión"):
    streamlit_js_eval(js_expressions="localStorage.removeItem('p2p_app_pwd')", key="ls_del")
    st.session_state["authenticated"] = False
    st.rerun()

intervalo_map = {"5 Minutos": 300, "1 Hora": 3600, "Diario": 86400}
seleccion = st.sidebar.selectbox("Temporalidad:", list(intervalo_map.keys()), index=1)
df = get_p2p_data(intervalo_map[seleccion])

st.title("💵 Binance P2P — Master Dashboard")

if not df.empty:
    # Date Picker
    min_date, max_date = df["datetime_bo"].min().date(), df["datetime_bo"].max().date()
    dr = st.sidebar.date_input("Rango de fechas:", [min_date, max_date])
    
    if len(dr) == 2:
        mask = (df["datetime_bo"].dt.date >= dr[0]) & (df["datetime_bo"].dt.date <= dr[1])
        df_filtered = df.loc[mask].copy()
    else:
        df_filtered = df

    # Plot
    fig = go.Figure(data=[go.Candlestick(
        x=df_filtered['datetime_bo'],
        open=df_filtered['open'], high=df_filtered['high'],
        low=df_filtered['low'], close=df_filtered['close']
    )])
    fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_filtered)
