import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import os
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# --- Page Configuration ---
st.set_page_config(
    page_title="ProQuant | Terminal",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Enhanced Dark Theme Styling ---
st.markdown("""
    <style>
        .main { background-color: #0E1117; }
        .block-container { padding-top: 1.5rem; max-width: 98%; }
        
        /* Glassmorphism Metric Cards */
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 15px 20px;
            border-radius: 12px;
            transition: all 0.3s ease;
        }
        [data-testid="stMetric"]:hover {
            border-color: #2962FF;
            background: rgba(41, 98, 255, 0.05);
        }
        
        /* Status Badges */
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-online { background: #00E676; color: #000; box-shadow: 0 0 15px rgba(0,230,118,0.4); }
        
        /* Custom Font */
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .mono { font-family: 'JetBrains Mono', monospace; }
    </style>
""", unsafe_allow_html=True)

# --- Database Connection ---
@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL")
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)

engine = get_engine()

# --- Sidebar Controls ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2091/2091665.png", width=80)
    st.title("ProQuant Bot")
    st.markdown("---")
    
    refresh_rate = st.slider("Terminal Refresh Rate (s)", 1, 10, 2)
    show_ema_200 = st.checkbox("Show EMA 200 (Trend)", value=True)
    show_signals = st.checkbox("Show Trade Signals", value=True)
    
    st.markdown("---")
    st.info("💡 **Strategy:** RSI Pullback + EMA 200 Trend Filter")
    if st.button("Clear Logs (Local Only)"):
        st.toast("Database reset requires CLI access.")

# --- Header Section ---
h_col1, h_col2 = st.columns([3, 1])
with h_col1:
    st.title("⚡ ProQuant Algorithmic Terminal")
    st.caption(f"Connected to: {os.getenv('DATABASE_URL', 'SQLite Local').split('@')[-1]}")
with h_col2:
    st.markdown(f'<div style="text-align:right; margin-top:25px;"><span class="status-badge status-online">● Live Feed</span></div>', unsafe_allow_html=True)

placeholder = st.empty()

# --- Main Data Loop ---
while True:
    try:
        # Data Fetching
        with engine.connect() as conn:
            df_prices = pd.read_sql("SELECT * FROM prices ORDER BY id DESC LIMIT 150", conn)
            df_indicators = pd.read_sql("SELECT * FROM indicators ORDER BY id DESC LIMIT 150", conn)
            df_trades = pd.read_sql("SELECT * FROM trades ORDER BY id DESC LIMIT 20", conn)
            df_portfolio = pd.read_sql("SELECT * FROM portfolio LIMIT 1", conn)

        # Sort for Charting
        df_prices = df_prices.sort_values("timestamp")
        df_indicators = df_indicators.sort_values("timestamp")

        with placeholder.container():
            # 1. Calculation Logic
            cur_p = df_prices.iloc[-1]['price'] if not df_prices.empty else 0
            usd = df_portfolio.iloc[0]['usd_balance']
            btc = df_portfolio.iloc[0]['btc_balance']
            equity = usd + (btc * cur_p)
            pnl_pct = ((equity - 10000) / 10000) * 100
            
            # 2. Top Metric Row
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Net Equity", f"${equity:,.2f}", f"{pnl_pct:.2f}%")
            m2.metric("Market Price", f"${cur_p:,.2f}", f"{btc:.4f} BTC Held")
            
            rsi = df_indicators.iloc[-1]['rsi'] if not df_indicators.empty else 50
            rsi_delta = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
            m3.metric("RSI (14)", f"{rsi:.1f}", rsi_delta, delta_color="off" if rsi_delta == "NEUTRAL" else "normal")
            
            # Drawdown logic
            high_water_mark = df_portfolio.iloc[0]['highest_price'] if 'highest_price' in df_portfolio.columns else cur_p
            dd = ((cur_p - high_water_mark) / high_water_mark) * 100 if high_water_mark > 0 else 0
            m4.metric("Active Drawdown", f"{dd:.2f}%", "Trailing Stop Active", delta_color="inverse")

            # 3. Main Charting
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                vertical_spacing=0.05, row_heights=[0.7, 0.3],
                subplot_titles=("", "")
            )

            # Price & Indicators
            fig.add_trace(go.Scatter(x=df_prices['timestamp'], y=df_prices['price'], name="BTC/USDT", line=dict(color='#2962FF', width=2)), row=1, col=1)
            
            if show_ema_200 and 'ema_200' in df_indicators.columns:
                fig.add_trace(go.Scatter(x=df_indicators['timestamp'], y=df_indicators['ema_200'], name="EMA 200", line=dict(color='rgba(255, 255, 255, 0.4)', width=1, dash='dot')), row=1, col=1)
            
            if 'sma_20' in df_indicators.columns:
                fig.add_trace(go.Scatter(x=df_indicators['timestamp'], y=df_indicators['sma_20'], name="SMA 20", line=dict(color='#FFAB00', width=1.5)), row=1, col=1)

            # RSI Subplot
            fig.add_trace(go.Scatter(x=df_indicators['timestamp'], y=df_indicators['rsi'], name="RSI", fill='tozeroy', fillcolor='rgba(0, 230, 118, 0.05)', line=dict(color='#00E676', width=1.5)), row=2, col=1)
            
            # RSI Bands
            fig.add_hline(y=70, line_dash="dash", line_color="#FF5252", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#00E676", row=2, col=1)

            fig.update_layout(template="plotly_dark", height=600, margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
            st.plotly_chart(fig, use_container_width=True)

            # 4. Logs and Activity
            col_l, col_r = st.columns([2, 1])
            
            with col_l:
                st.subheader("📁 Order Execution History")
                if not df_trades.empty:
                    st.dataframe(df_trades[['timestamp', 'side', 'price', 'reason']].style.applymap(lambda x: 'color: #00E676' if x == 'BUY' else ('color: #FF5252' if x == 'SELL' else ''), subset=['side']), use_container_width=True, hide_index=True)
                else:
                    st.info("No trades executed in this session.")

            with col_r:
                st.subheader("📊 Portfolio Exposure")
                labels = ['USDT Cash', 'BTC Exposure']
                values = [usd, btc * cur_p]
                pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.6, marker_colors=['#1E222D', '#2962FF'])])
                pie.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0), height=250, showlegend=False)
                st.plotly_chart(pie, use_container_width=True)

        time.sleep(refresh_rate)

    except Exception as e:
        st.error(f"Stream Sync Error: {e}")
        time.sleep(5)