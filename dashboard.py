import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
import time
import plotly.express as px

# Config
st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/tradingbot")

# DB Connection
engine = create_engine(DATABASE_URL)

st.title("⚡ Automated Crypto Trading Bot")
st.markdown("### Live Performance Monitor")

# Auto-refresh mechanism
placeholder = st.empty()

while True:
    try:
        # Fetch Data
        df_prices = pd.read_sql("SELECT * FROM prices ORDER BY timestamp DESC LIMIT 100", engine)
        df_trades = pd.read_sql("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10", engine)
        
        with placeholder.container():
            # Metrics
            kpi1, kpi2, kpi3 = st.columns(3)
            current_price = df_prices.iloc[0]['price'] if not df_prices.empty else 0
            total_trades = len(pd.read_sql("SELECT id FROM trades", engine))
            
            kpi1.metric(label="Current BTC Price", value=f"${current_price:,.2f}")
            kpi2.metric(label="Total Trades Executed", value=total_trades)
            kpi3.metric(label="Status", value="Running", delta="Active")

            # Chart
            if not df_prices.empty:
                fig = px.line(df_prices, x='timestamp', y='price', title='Real-Time Price Feed')
                st.plotly_chart(fig, use_container_width=True)

            # Recent Trades Table
            st.subheader("Recent Executions")
            st.dataframe(df_trades, use_container_width=True)
            
        time.sleep(1) # Refresh UI every second
        
    except Exception as e:
        st.error(f"Waiting for Bot to initialize database... ({e})")
        time.sleep(2)