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
    page_title="ProQuant Crypto Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .block-container {padding-top: 1rem; padding-bottom: 1rem;}
        div[data-testid="metric-container"] {
            background-color: #1E1E1E;
            border: 1px solid #333;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.5);
        }
        h1 {text-align: center; margin-bottom: 30px;}
        .stDataFrame {border-radius: 10px; overflow: hidden;}
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
        df_prices = pd.read_sql("SELECT * FROM prices ORDER BY timestamp DESC LIMIT 100", engine)
        df_indicators = pd.read_sql("SELECT * FROM indicators ORDER BY timestamp DESC LIMIT 100", engine)
        df_trades = pd.read_sql("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10", engine)
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
            rsi_val = df_indicators.iloc[-1]['rsi'] if not df_indicators.empty else 50
            
            col1, col2, col3, col4 = st.columns(4)
            
            col1.metric("Total Equity", f"${total_equity:,.2f}", delta=f"{((total_equity-10000)/10000)*100:.2f}%")
            col2.metric("BTC Price", f"${current_price:,.2f}")
            col3.metric("RSI (14)", f"{rsi_val:.2f}", delta_color="inverse")
            col4.metric("Holdings", f"{btc_bal:.4f} BTC / ${usd_bal:,.2f} Cash")

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03, row_heights=[0.7, 0.3],
                                specs=[[{"secondary_y": False}], [{"secondary_y": False}]])

            if not df_prices.empty:
                fig.add_trace(go.Scatter(x=df_prices['timestamp'], y=df_prices['price'], 
                                         name="BTC Price", line=dict(color='#00F0FF', width=2)), row=1, col=1)
                
                if not df_indicators.empty and 'sma_20' in df_indicators.columns:
                     fig.add_trace(go.Scatter(x=df_indicators['timestamp'], y=df_indicators['sma_20'], 
                                         name="SMA 20", line=dict(color='#FFA500', width=1)), row=1, col=1)

            if not df_indicators.empty:
                fig.add_trace(go.Scatter(x=df_indicators['timestamp'], y=df_indicators['rsi'], 
                                         name="RSI", line=dict(color='#A020F0', width=2)), row=2, col=1)
                
                fig.add_hrect(y0=70, y1=100, fillcolor="red", opacity=0.1, line_width=0, row=2, col=1)
                fig.add_hrect(y0=0, y1=30, fillcolor="green", opacity=0.1, line_width=0, row=2, col=1)
                fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
                fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)

            fig.update_layout(
                template="plotly_dark",
                height=600,
                margin=dict(l=20, r=20, t=30, b=20),
                legend=dict(orientation="h", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig, use_container_width=True, key=f"main_chart_{time.time()}")

            st.subheader("📝 Recent Trade Executions")
            st.dataframe(
                df_trades[['timestamp', 'side', 'price', 'quantity', 'usd_balance']], 
                use_container_width=True,
                hide_index=True
            )

        time.sleep(2)

    except Exception as e:
        with placeholder.container():
            st.warning(f"Initializing System... ({str(e)})")
        time.sleep(2)