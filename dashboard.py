import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import os
import time
import plotly.express as px
from dotenv import load_dotenv 

# 1. Load Environment Variables (Crucial for local testing)
load_dotenv()

st.set_page_config(page_title="Crypto Bot Dashboard", layout="wide")

# 2. Database Setup
raw_db_url = os.getenv("DATABASE_URL")

# Fix for Neon/Render compatibility
if raw_db_url and raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

if not raw_db_url:
    st.error("DATABASE_URL is missing! Check your .env file.")
    st.stop()

# Create Engine
try:
    engine = create_engine(raw_db_url)
except Exception as e:
    st.error(f"Failed to connect to DB: {e}")
    st.stop()

# 3. Dashboard Interface
st.title("⚡ Automated Crypto Trading Bot")
st.markdown("### Live Performance Monitor")

# Create a placeholder where the dashboard will update
placeholder = st.empty()

# 4. The Live Update Loop
while True:
    try:
        # Fetch Data from Neon DB
        df_prices = pd.read_sql("SELECT * FROM prices ORDER BY timestamp DESC LIMIT 100", engine)
        df_trades = pd.read_sql("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10", engine)
        
        with placeholder.container():
            # KPI Metrics
            kpi1, kpi2, kpi3 = st.columns(3)
            current_price = df_prices.iloc[0]['price'] if not df_prices.empty else 0
            
            # Count total trades (safely)
            try:
                total_trades = pd.read_sql("SELECT COUNT(*) FROM trades", engine).iloc[0, 0]
            except:
                total_trades = 0
            
            kpi1.metric(label="Current BTC Price", value=f"${current_price:,.2f}")
            kpi2.metric(label="Total Trades Executed", value=total_trades)
            kpi3.metric(label="Status", value="Running", delta="Active")

            # Chart (The Error Fix is HERE)
            if not df_prices.empty:
                fig = px.line(df_prices, x='timestamp', y='price', title='Real-Time Price Feed')
                
                # We use time.time() to give the chart a unique ID every second
                st.plotly_chart(fig, use_container_width=True, key=f"live_chart_{time.time()}")

            # Recent Trades Table
            st.subheader("Recent Executions")
            st.dataframe(df_trades, use_container_width=True)
            
        time.sleep(1) # Refresh every second
        
    except Exception as e:
        # If DB is empty (bot hasn't started yet), show a waiting message
        with placeholder.container():
            st.warning(f"Waiting for Bot to write data... ({e})")
        time.sleep(2)