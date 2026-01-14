import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
import time
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="ProQuant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .block-container {padding-top: 1.5rem; padding-bottom: 1rem;}
        div[data-testid="metric-container"] {
            background-color: #0E1117;
            border: 1px solid #262730;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        div[data-testid="metric-container"]:hover {
            border-color: #4B4B4B;
        }
        h1 {
            font-family: 'Helvetica Neue', sans-serif;
            font-weight: 700;
            color: #FAFAFA;
            margin-bottom: 25px;
        }
        .stDataFrame {
            border: 1px solid #262730;
            border-radius: 12px;
        }
    </style>
""", unsafe_allow_html=True)

raw_db_url = os.getenv("DATABASE_URL")

if raw_db_url and raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

if not raw_db_url:
    st.error("DATABASE_URL is missing.")
    st.stop()

try:
    engine = create_engine(raw_db_url)
except Exception as e:
    st.error(f"Connection Failed: {e}")
    st.stop()

st.title("⚡ ProQuant Algorithmic Terminal")

placeholder = st.empty()

while True:
    try:
        df_prices = pd.read_sql("SELECT * FROM prices ORDER BY id DESC LIMIT 100", engine)
        df_indicators = pd.read_sql("SELECT * FROM indicators ORDER BY id DESC LIMIT 100", engine)
        df_trades = pd.read_sql("SELECT * FROM trades ORDER BY id DESC LIMIT 15", engine)
        df_portfolio = pd.read_sql("SELECT * FROM portfolio LIMIT 1", engine)

        if not df_prices.empty:
            df_prices = df_prices.sort_values("timestamp")
        
        if not df_indicators.empty:
            df_indicators = df_indicators.sort_values("timestamp")

        with placeholder.container():
            current_price = df_prices.iloc[-1]['price'] if not df_prices.empty else 0
            
            usd_bal = 10000.0
            btc_bal = 0.0
            if not df_portfolio.empty:
                usd_bal = df_portfolio.iloc[0]['usd_balance']
                btc_bal = df_portfolio.iloc[0]['btc_balance']
            
            total_equity = usd_bal + (btc_bal * current_price)
            net_pl_pct = ((total_equity - 10000) / 10000) * 100
            
            rsi_val = df_indicators.iloc[-1]['rsi'] if not df_indicators.empty else 50
            sma_val = df_indicators.iloc[-1]['sma_20'] if not df_indicators.empty else 0

            col1, col2, col3, col4 = st.columns(4)
            
            col1.metric("Total Equity", f"${total_equity:,.2f}", delta=f"{net_pl_pct:.2f}%")
            col2.metric("BTC Price", f"${current_price:,.2f}", delta=f"${current_price - sma_val:.2f} vs SMA")
            col3.metric("RSI Momentum", f"{rsi_val:.2f}", delta="Overbought" if rsi_val > 70 else "Oversold" if rsi_val < 30 else "Neutral", delta_color="inverse")
            col4.metric("Portfolio Allocation", f"{btc_bal:.4f} BTC", f"${usd_bal:,.2f} Cash")

            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.05, 
                row_heights=[0.7, 0.3],
                subplot_titles=("Price Action & SMA", "Relative Strength Index")
            )

            if not df_prices.empty:
                fig.add_trace(go.Scatter(
                    x=df_prices['timestamp'], 
                    y=df_prices['price'], 
                    name="BTC Price", 
                    line=dict(color='#2962FF', width=2)
                ), row=1, col=1)
                
                if not df_indicators.empty:
                     fig.add_trace(go.Scatter(
                         x=df_indicators['timestamp'], 
                         y=df_indicators['sma_20'], 
                         name="SMA 20", 
                         line=dict(color='#FF6D00', width=1.5, dash='solid')
                    ), row=1, col=1)

            if not df_indicators.empty:
                fig.add_trace(go.Scatter(
                    x=df_indicators['timestamp'], 
                    y=df_indicators['rsi'], 
                    name="RSI", 
                    line=dict(color='#00E676', width=2)
                ), row=2, col=1)
                
                fig.add_hrect(y0=70, y1=100, fillcolor="#FF5252", opacity=0.1, line_width=0, row=2, col=1)
                fig.add_hrect(y0=0, y1=30, fillcolor="#00E676", opacity=0.1, line_width=0, row=2, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="#FF5252", row=2, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="#00E676", row=2, col=1)

            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=700,
                margin=dict(l=10, r=10, t=30, b=10),
                legend=dict(orientation="h", y=1.02, xanchor="right", x=1),
                hovermode="x unified"
            )
            
            fig.update_yaxes(gridcolor='#333333', row=1, col=1)
            fig.update_yaxes(gridcolor='#333333', range=[0, 100], row=2, col=1)
            fig.update_xaxes(gridcolor='#333333')
            
            st.plotly_chart(fig, use_container_width=True, key=f"main_chart_{time.time()}")

            st.subheader("📝 Order History")
            if not df_trades.empty:
                display_trades = df_trades[['timestamp', 'side', 'price', 'quantity', 'usd_balance', 'btc_balance']].copy()
                display_trades['price'] = display_trades['price'].apply(lambda x: f"${x:,.2f}")
                display_trades['usd_balance'] = display_trades['usd_balance'].apply(lambda x: f"${x:,.2f}")
                st.dataframe(
                    display_trades, 
                    use_container_width=True,
                    hide_index=True,
                    height=300
                )
            else:
                st.info("No trades executed yet. Waiting for market signals...")

        time.sleep(1)

    except Exception as e:
        with placeholder.container():
            st.warning(f"Connecting to live feed... ({str(e)})")
        time.sleep(2)