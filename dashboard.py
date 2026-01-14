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

st.set_page_config(
    page_title="ProQuant Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            max-width: 95%;
        }
        
        /* Metric Cards */
        div[data-testid="metric-container"] {
            background-color: #12141C;
            border: 1px solid #2A2D3A;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.2);
            transition: border-color 0.3s ease;
        }
        div[data-testid="metric-container"]:hover {
            border-color: #00E676;
        }
        
        /* Typography */
        h1, h2, h3 {
            font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
            letter-spacing: -0.5px;
        }
        
        /* DataFrame Styling */
        .stDataFrame {
            border: 1px solid #2A2D3A;
            border-radius: 8px;
        }
        
        /* Status Indicator */
        .status-dot {
            height: 10px;
            width: 10px;
            background-color: #00E676;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
            box-shadow: 0 0 10px #00E676;
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

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.title("⚡ ProQuant Algorithmic Terminal")
with header_col2:
    st.markdown(f"""
        <div style="text-align: right; padding-top: 20px; color: #888;">
            <span class="status-dot"></span>SYSTEM ONLINE
        </div>
    """, unsafe_allow_html=True)

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
                # Safe access to portfolio columns
                if 'usd_balance' in df_portfolio.columns:
                    usd_bal = df_portfolio.iloc[0]['usd_balance']
                if 'btc_balance' in df_portfolio.columns:
                    btc_bal = df_portfolio.iloc[0]['btc_balance']
            
            total_equity = usd_bal + (btc_bal * current_price)
            net_pl_pct = ((total_equity - 10000) / 10000) * 100
            
            rsi_val = df_indicators.iloc[-1]['rsi'] if not df_indicators.empty else 50
            sma_val = df_indicators.iloc[-1]['sma_20'] if not df_indicators.empty else 0

            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            
            kpi1.metric(
                "Total Equity", 
                f"${total_equity:,.2f}", 
                delta=f"{net_pl_pct:.2f}%"
            )
            kpi2.metric(
                "BTC Price", 
                f"${current_price:,.2f}", 
                delta=f"${current_price - sma_val:.2f} vs SMA" if sma_val > 0 else None
            )
            
            status_color = "inverse"
            status_text = "Neutral"
            if rsi_val > 70: status_text = "Overbought (Sell Risk)"
            if rsi_val < 30: status_text = "Oversold (Buy Opp)"
            
            kpi3.metric(
                "RSI Momentum", 
                f"{rsi_val:.2f}", 
                delta=status_text, 
                delta_color=status_color
            )
            kpi4.metric(
                "Portfolio Allocation", 
                f"{btc_bal:.4f} BTC", 
                f"${usd_bal:,.2f} Cash"
            )

            st.markdown("---")

            fig = make_subplots(
                rows=2, cols=1, 
                shared_xaxes=True, 
                vertical_spacing=0.08, 
                row_heights=[0.75, 0.25],
                subplot_titles=("Price Action & SMA", "RSI Oscillator")
            )

            if not df_prices.empty:
                fig.add_trace(go.Scatter(
                    x=df_prices['timestamp'], 
                    y=df_prices['price'], 
                    name="Price", 
                    line=dict(color='#2962FF', width=2),
                    hovertemplate='$%{y:,.2f}'
                ), row=1, col=1)
                
                if not df_indicators.empty and 'sma_20' in df_indicators.columns:
                     fig.add_trace(go.Scatter(
                         x=df_indicators['timestamp'], 
                         y=df_indicators['sma_20'], 
                         name="SMA 20", 
                         line=dict(color='#FF6D00', width=1.5),
                         hovertemplate='$%{y:,.2f}'
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
                height=650,
                margin=dict(l=10, r=10, t=30, b=10),
                legend=dict(orientation="h", y=1.02, xanchor="right", x=1),
                hovermode="x unified"
            )
            
            fig.update_yaxes(gridcolor='#2A2D3A', row=1, col=1)
            fig.update_yaxes(gridcolor='#2A2D3A', range=[0, 100], row=2, col=1)
            fig.update_xaxes(gridcolor='#2A2D3A')
            
            st.plotly_chart(fig, use_container_width=True, key=f"main_chart_{time.time()}")

            st.subheader("📝 Live Execution Log")
            if not df_trades.empty:
                # CRITICAL CRASH PROOFING: Only select columns that actually exist
                expected_cols = ['timestamp', 'side', 'price', 'quantity', 'usd_balance', 'btc_balance']
                available_cols = [col for col in expected_cols if col in df_trades.columns]
                
                display_trades = df_trades[available_cols].copy()
                
                # Format currency columns if they exist
                if 'price' in display_trades.columns:
                    display_trades['price'] = display_trades['price'].apply(lambda x: f"${x:,.2f}")
                if 'usd_balance' in display_trades.columns:
                    display_trades['usd_balance'] = display_trades['usd_balance'].apply(lambda x: f"${x:,.2f}")
                
                st.dataframe(
                    display_trades, 
                    use_container_width=True,
                    hide_index=True,
                    height=250
                )
            else:
                st.info("System Initialized. Waiting for first trade execution...")

        time.sleep(1)

    except Exception as e:
        with placeholder.container():
            st.warning(f"Connecting to live feed... ({str(e)})")
        time.sleep(2)