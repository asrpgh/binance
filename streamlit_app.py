import streamlit as st
import pandas as pd
import libsql_experimental as libsql
import plotly.graph_objects as go
from streamlit_js_eval import streamlit_js_eval

# ---------- 1. Configuration & Secrets ----------
# Fetch credentials from .streamlit/secrets.toml or Streamlit Cloud Secrets
TURSO_URL = st.secrets.get("TURSO_URL", "")
TURSO_AUTH_TOKEN = st.secrets.get("TURSO_AUTH_TOKEN", "")
APP_PASSWORD = st.secrets.get("APP_PASSWORD", "")  # Default if not set

st.set_page_config(page_title="Binance P2P — Secure Turso", layout="wide")

# ---------- 2. Persistent Login Logic ----------

def check_login():
    """
    Handles authentication by checking Session State and Browser Local Storage.
    If the password in LocalStorage matches the secret, it bypasses the login screen.
    """
    # Initialize session state if not present
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if st.session_state["authenticated"]:
        return True

    # Attempt to read password from browser's Local Storage
    # This runs a JS snippet to pull the value
    stored_password = streamlit_js_eval(js_expressions="localStorage.getItem('p2p_app_pwd')", key="get_ls")
    
    # Validation: If LS matches current secret, skip login
    if stored_password == APP_PASSWORD:
        st.session_state["authenticated"] = True
        return True

    # Show Login UI
    st.markdown("### 🔒 Acceso Restringido")
    with st.container():
        pwd_input = st.text_input("Introduce la contraseña maestra:", type="password")
        if st.button("Ingresar"):
            if pwd_input == APP_PASSWORD:
                # Save to Local Storage via JS to persist across refreshes/tabs
                streamlit_js_eval(js_expressions=f"localStorage.setItem('p2p_app_pwd', '{pwd_input}')", key="set_ls")
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
    
    return False

# Stop the app here if not logged in
if not check_login():
    st.stop()

# ---------- 3. Data Fetching (Turso) ----------

@st.cache_data(ttl=300)
def get_p2p_data(seconds_limit):
    """
    Queries Turso DB for aggregated P2P data from the last month.
    """
    try:
        conn = libsql.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
        
        # SQL logic for time-bucketing and 1-month window
        query = """
        SELECT 
            datetime(
                (strftime('%s', datetime_utc) / ?) * ?, 
                'unixepoch'
            ) AS interval_start,
            SUM(buy_count) AS total_buy_count,
            AVG(buy_median) AS buy_median,
            MIN(buy_min) AS buy_min,
            MAX(buy_max) AS buy_max,
            SUM(sell_count) AS total_sell_count,
            AVG(sell_median) AS sell_median,
            MIN(sell_min) AS sell_min,
            MAX(sell_max) AS sell_max,
            AVG(market_median) AS market_median
        FROM p2p_data 
        WHERE datetime_utc >= date('now', '-1 month')
        GROUP BY interval_start
        ORDER BY interval_start DESC;
        """
        
        df = pd.read_sql_query(query, conn, params=(seconds_limit, seconds_limit))
        conn.close()
        
        if df.empty:
            return df

        # Timezone conversion to Venezuela
        df["interval_start"] = pd.to_datetime(df["interval_start"], utc=True)
        df["datetime_bo"] = df["interval_start"].dt.tz_convert("America/Caracas")
        
        return df
    except Exception as e:
        st.error(f"⚠️ Error de base de datos: {e}")
        return pd.DataFrame()

# ---------- 4. Dashboard UI ----------

# Sidebar Controls
st.sidebar.title("🛠️ Panel de Control")

# Logout button: Clears session and LocalStorage
if st.sidebar.button("Cerrar Sesión (Log Out)"):
    streamlit_js_eval(js_expressions="localStorage.removeItem('p2p_app_pwd')", key="logout_js")
    st.session_state["authenticated"] = False
    st.rerun()

st.sidebar.divider()

intervalo_map = {
    "5 Minutos": 300,
    "1 Hora": 3600,
    "Diario": 86400
}
seleccion = st.sidebar.selectbox("Temporalidad de Velas:", list(intervalo_map.keys()), index=1)
seconds = intervalo_map[seleccion]

# Header
st.title("💵 Binance P2P — VES/USDT")
st.caption("Visualización en tiempo real desde Turso (Últimos 30 días)")

# Main Logic
df = get_p2p_data(seconds)

if df.empty:
    st.warning("No hay datos disponibles en este momento.")
else:
    # Summary Metrics
    latest = df.iloc[0]
    m1, m2, m3 = st.columns(3)
    m1.metric("Precio Actual", f"{latest['market_median']:.3f} VES")
    m2.metric("Máximo (30d)", f"{df['buy_max'].max():.3f} VES")
    m3.metric("Mínimo (30d)", f"{df['sell_min'].min():.3f} VES")

    # Tabs
    tab1, tab2 = st.tabs(["🕯️ Gráfico de Velas", "📊 Registros Crudos"])

    with tab1:
        # OHLC logic: 'Open' is the 'Close' of the chronologically previous candle
        # Since DF is DESC, the previous candle is index + 1
        fig = go.Figure(data=[go.Candlestick(
            x=df['datetime_bo'],
            open=df['market_median'].shift(-1).fillna(df['market_median']),
            high=df['buy_max'],
            low=df['sell_min'],
            close=df['market_median'],
            increasing_line_color='#26a69a', 
            decreasing_line_color='#ef5350'
        )])

        fig.update_layout(
            template="plotly_dark",
            height=600,
            xaxis_rangeslider_visible=False,
            margin=dict(t=30, b=0, l=10, r=10)
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Datos Agregados por Periodo")
        st.dataframe(df, use_container_width=True)

st.divider()
st.caption("Nota: La contraseña se persiste localmente. Si la cambias en los Secretos, se requerirá un nuevo login.")
