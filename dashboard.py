import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os, time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="ProQuant Terminal", page_icon="📈", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1rem; max-width: 98%; }
        [data-testid="stMetric"] { background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 15px; }
        .stDataFrame { border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL")
    if url and url.startswith("postgres://"): url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url)

engine = get_engine()

with st.sidebar:
    st.title("🛡️ Bot Controller")
    refresh_rate = st.slider("Update Interval (s)", 1, 10, 2)
    st.markdown("---")
    st.subheader("Chart Settings")
    show_ema = st.checkbox("EMA 200 (Trend)", True)
    show_sma = st.checkbox("SMA 20 (Momentum)", True)
    show_markers = st.checkbox("Trade Markers", True)
    st.markdown("---")
    if st.button("Emergency Stop", use_container_width=True):
        st.error("Stop signal sent to bot.py (requires API integration)")

st.title("⚡ ProQuant Algorithmic Terminal")

placeholder = st.empty()

while True:
    try:
        with engine.connect() as conn:
            df_p = pd.read_sql("SELECT * FROM prices ORDER BY id DESC LIMIT 200", conn).sort_values("timestamp")
            df_i = pd.read_sql("SELECT * FROM indicators ORDER BY id DESC LIMIT 200", conn).sort_values("timestamp")
            df_t = pd.read_sql("SELECT * FROM trades ORDER BY id DESC LIMIT 50", conn)
            df_port = pd.read_sql("SELECT * FROM portfolio LIMIT 1", conn)

        with placeholder.container():
            # --- TOP ROW: KPI METRICS ---
            cp = df_p.iloc[-1]['price'] if not df_p.empty else 0
            usd, btc = df_port.iloc[0]['usd_balance'], df_port.iloc[0]['btc_balance']
            entry = df_port.iloc[0]['entry_price']
            eq = usd + (btc * cp)
            pnl_pct = ((eq - 10000) / 10000) * 100
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Equity", f"${eq:,.2f}", f"{pnl_pct:.2f}%")
            c2.metric("Market Price", f"${cp:,.2f}", f"{((cp - df_p.iloc[0]['price'])/df_p.iloc[0]['price'])*100:.2f}% (View)")
            
            rsi = df_i.iloc[-1]['rsi'] if not df_i.empty else 50
            c3.metric("RSI (14)", f"{rsi:.1f}", "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL")
            
            active_pnl = ((cp - entry) / entry * 100) if btc > 0 and entry > 0 else 0
            c4.metric("Active Trade PnL", f"{active_pnl:.2f}%", "IN POSITION" if btc > 0 else "FLAT")

            # --- MIDDLE ROW: MAIN CHART ---
            
            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                row_heights=[0.7, 0.3], 
                vertical_spacing=0.03,
                subplot_titles=("Price Action", "Relative Strength Index")
            )

            # Price Line
            fig.add_trace(go.Scatter(x=df_p['timestamp'], y=df_p['price'], name="BTC Price", line=dict(color='#2962FF', width=2)), row=1, col=1)
            
            # Indicators
            if show_ema and not df_i.empty:
                fig.add_trace(go.Scatter(x=df_i['timestamp'], y=df_i['ema_200'], name="EMA 200", line=dict(color='rgba(255,255,255,0.5)', dash='dot')), row=1, col=1)
            if show_sma and not df_i.empty:
                fig.add_trace(go.Scatter(x=df_i['timestamp'], y=df_i['sma_20'], name="SMA 20", line=dict(color='#FFAB00')), row=1, col=1)

            # Trade Markers (Arrows on the chart)
            if show_markers and not df_t.empty:
                buys = df_t[df_t['side'] == 'BUY']
                sells = df_t[df_t['side'] == 'SELL']
                fig.add_trace(go.Scatter(x=buys['timestamp'], y=buys['price'], mode='markers', name='Buy Signal', marker=dict(symbol='triangle-up', size=12, color='#00E676')), row=1, col=1)
                fig.add_trace(go.Scatter(x=sells['timestamp'], y=sells['price'], mode='markers', name='Sell Signal', marker=dict(symbol='triangle-down', size=12, color='#FF5252')), row=1, col=1)

            # RSI Subplot
            fig.add_trace(go.Scatter(x=df_i['timestamp'], y=df_i['rsi'], name="RSI", line=dict(color='#00E676'), fill='tozeroy', fillcolor='rgba(0,230,118,0.05)'), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

            fig.update_layout(template="plotly_dark", height=700, margin=dict(l=0, r=0, t=30, b=0), hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{time.time()}")

            # --- BOTTOM ROW: STATS & LOGS ---
            col_left, col_right = st.columns([1, 2])
            
            with col_left:
                st.subheader("📊 Performance")
                win_count = len(df_t[df_t['side'] == 'SELL']) # Simplification: count exit trades
                st.write(f"Total Completed Trades: {win_count}")
                st.write(f"Current Exposure: {btc:.4f} BTC")
                st.progress(min(max(rsi/100, 0.0), 1.0), text=f"RSI Intensity: {rsi:.1f}")

            with col_right:
                st.subheader("📁 Live Execution Log")
                if not df_t.empty:
                    # Formatting the dataframe for a pro look
                    display_t = df_t[['timestamp', 'side', 'price', 'reason']].copy()
                    st.dataframe(display_t, use_container_width=True, hide_index=True)
                else:
                    st.info("Waiting for execution signals...")

        time.sleep(refresh_rate)
    except Exception as e:
        st.error(f"Syncing Data: {e}")
        time.sleep(2)