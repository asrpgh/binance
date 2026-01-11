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
    st.error(f"Error cargando CSV:
