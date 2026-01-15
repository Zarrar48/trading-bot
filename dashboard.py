import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, inspect, text
import os
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="ProQuant | Terminal",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
        .main { background-color: #0E1117; }
        .block-container { padding-top: 1.5rem; max-width: 98%; }
        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 15px 20px;
            border-radius: 12px;
        }
        [data-testid="stMetric"]:hover {
            border-color: #2962FF;
            background: rgba(41, 98, 255, 0.05);
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }
        .status-online { background: #00E676; color: #000; box-shadow: 0 0 15px rgba(0,230,118,0.4); }
        .status-offline { background: #FF5252; color: #FFF; }
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        .mono { font-family: 'JetBrains Mono', monospace; }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_engine():
    url = os.getenv("DATABASE_URL", "sqlite:///./trading_bot_pro.db")
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)

engine = get_engine()

def calculate_performance(df):
    if df.empty: return 0, 0.0, 0.0
    
    trades = df.sort_values("timestamp")
    closed_trades = []
    active_buy_price = None
    
    for index, row in trades.iterrows():
        if row['side'] == 'BUY':
            active_buy_price = row['price']
        elif row['side'] == 'SELL' and active_buy_price:
            pnl = (row['price'] - active_buy_price) / active_buy_price
            closed_trades.append(pnl)
            active_buy_price = None
            
    if not closed_trades: return 0, 0.0, 0.0
    
    total_trades = len(closed_trades)
    win_rate = (len([x for x in closed_trades if x > 0]) / total_trades) * 100
    avg_pnl = (sum(closed_trades) / total_trades) * 100
    
    return total_trades, win_rate, avg_pnl

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2091/2091665.png", width=80)
    st.title("ProQuant Bot")
    st.markdown("---")
    
    refresh_rate = st.slider("Terminal Refresh Rate (s)", 1, 10, 2)
    show_ema_200 = st.checkbox("Show EMA 200 (Trend)", value=True)
    
    st.markdown("---")
    st.caption("Status Check")
    
    try:
        insp = inspect(engine)
        if insp.has_table("prices"):
            st.success("✅ Database Connected")
        else:
            st.error("❌ Database Not Initialized")
    except:
        st.error("❌ Connection Failed")

h_col1, h_col2 = st.columns([3, 1])
with h_col1:
    st.title("⚡ ProQuant Algorithmic Terminal")
    st.caption(f"Target Database: {os.getenv('DATABASE_URL', 'Local SQLite').split('@')[-1]}")

placeholder = st.empty()

while True:
    try:
        insp = inspect(engine)
        if not insp.has_table("prices") or not insp.has_table("portfolio"):
            with placeholder.container():
                st.warning("⚠️ **Waiting for Bot Initialization...**")
                st.info("The database tables do not exist yet. Please run the `bot.py` script.")
                st.code("python bot.py", language="bash")
            time.sleep(5)
            continue

        with engine.connect() as conn:
            row_count = conn.execute(text("SELECT COUNT(*) FROM prices")).scalar()
            if row_count == 0:
                with placeholder.container():
                    st.info("⏳ **Waiting for Market Data...**")
                    st.caption("Bot running. Waiting for first candle close...")
                time.sleep(5)
                continue

            df_prices = pd.read_sql("SELECT * FROM prices ORDER BY id DESC LIMIT 150", conn)
            df_indicators = pd.read_sql("SELECT * FROM indicators ORDER BY id DESC LIMIT 150", conn)
            # Fetch more trades for accurate stats
            df_all_trades = pd.read_sql("SELECT * FROM trades", conn) 
            df_portfolio = pd.read_sql("SELECT * FROM portfolio LIMIT 1", conn)

        df_prices = df_prices.sort_values("timestamp")
        df_indicators = df_indicators.sort_values("timestamp")
        
        # Performance Calcs
        total_closed, win_rate, avg_pnl = calculate_performance(df_all_trades)

        with placeholder.container():
            st.markdown(f'<div style="text-align:right; margin-bottom:10px;"><span class="status-badge status-online">● Live Feed</span></div>', unsafe_allow_html=True)

            cur_p = df_prices.iloc[-1]['price']
            
            if not df_portfolio.empty:
                usd = df_portfolio.iloc[0]['usd_balance']
                btc = df_portfolio.iloc[0]['btc_balance']
                highest_price = df_portfolio.iloc[0]['highest_price']
                in_pos = df_portfolio.iloc[0]['in_position']
            else:
                usd, btc, highest_price, in_pos = 10000.0, 0.0, 0.0, False

            equity = usd + (btc * cur_p)
            pnl_pct = ((equity - 10000) / 10000) * 100
            
            # --- Row 1: Live Metrics ---
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Net Equity", f"${equity:,.2f}", f"{pnl_pct:.2f}%")
            m2.metric("Market Price", f"${cur_p:,.2f}", f"{btc:.4f} BTC")
            
            rsi = df_indicators.iloc[-1]['rsi'] if not df_indicators.empty else 50
            rsi_state = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
            m3.metric("RSI (14)", f"{rsi:.1f}", rsi_state, delta_color="off" if rsi_state == "NEUTRAL" else "normal")
            
            dd = ((cur_p - highest_price) / highest_price) * 100 if in_pos and highest_price > 0 else 0.0
            m4.metric("Position Drawdown", f"{dd:.2f}%", "Active" if in_pos else "Flat", delta_color="inverse")

            # --- Row 2: Strategy Performance ---
            st.markdown("### 🏆 Strategy Performance")
            p1, p2, p3 = st.columns(3)
            p1.metric("Win Rate", f"{win_rate:.1f}%", f"{total_closed} Trades Closed")
            p2.metric("Avg PnL per Trade", f"{avg_pnl:.2f}%", delta_color="normal" if avg_pnl > 0 else "inverse")
            
            est_monthly = avg_pnl * total_closed # Very rough projection
            p3.metric("Projected Monthly Return", "---" if total_closed < 5 else f"~{est_monthly:.1f}%", "Needs more data" if total_closed < 5 else "Est based on current avg")

            # --- Row 3: Charts ---
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                vertical_spacing=0.05, row_heights=[0.7, 0.3],
                subplot_titles=("Price Action", "RSI Momentum")
            )

            fig.add_trace(go.Scatter(x=df_prices['timestamp'], y=df_prices['price'], name="BTC/USD", line=dict(color='#2962FF', width=2)), row=1, col=1)
            
            if show_ema_200 and 'ema_200' in df_indicators.columns:
                ema_data = df_indicators.dropna(subset=['ema_200'])
                fig.add_trace(go.Scatter(x=ema_data['timestamp'], y=ema_data['ema_200'], name="EMA 200", line=dict(color='rgba(255, 255, 255, 0.5)', width=1, dash='dot')), row=1, col=1)
            
            if 'sma_20' in df_indicators.columns:
                sma_data = df_indicators.dropna(subset=['sma_20'])
                fig.add_trace(go.Scatter(x=sma_data['timestamp'], y=sma_data['sma_20'], name="SMA 20", line=dict(color='#FFAB00', width=1)), row=1, col=1)

            fig.add_trace(go.Scatter(x=df_indicators['timestamp'], y=df_indicators['rsi'], name="RSI", fill='tozeroy', fillcolor='rgba(0, 230, 118, 0.1)', line=dict(color='#00E676', width=1.5)), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#FF5252", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#00E676", row=2, col=1)

            fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation="h", y=1.02))
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{time.time()}")

            # --- Row 4: Tables ---
            col_l, col_r = st.columns([2, 1])
            
            with col_l:
                st.subheader("📁 Trade Log")
                if not df_all_trades.empty:
                    # Show last 10 trades for table
                    disp_trades = df_all_trades.sort_values("id", ascending=False).head(10).copy()
                    disp_trades['time'] = pd.to_datetime(disp_trades['timestamp']).dt.strftime('%H:%M:%S')
                    cols = ['time', 'side', 'price', 'quantity', 'reason']
                    disp_trades = disp_trades[[c for c in cols if c in disp_trades.columns]]
                    
                    st.dataframe(
                        disp_trades.style.map(lambda x: 'color: #00E676' if x == 'BUY' else ('color: #FF5252' if x == 'SELL' else ''), subset=['side']),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("No trades executed yet.")
                    
            with col_r:
                st.subheader("📊 Exposure")
                labels = ['USDT', 'BTC']
                values = [usd, btc * cur_p]
                pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.6, marker_colors=['#1E222D', '#2962FF'])])
                pie.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0), height=250, showlegend=False)
                st.plotly_chart(pie, use_container_width=True, key=f"pie_{time.time()}")

        time.sleep(refresh_rate)

    except Exception as e:
        st.error(f"Stream Loop Error: {e}")
        time.sleep(10)