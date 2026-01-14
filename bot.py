import asyncio
import random
import os
import time
import requests
from datetime import datetime
from aiohttp import web
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
load_dotenv()

# --- Configuration ---
# We use External URL for local test, Internal for Render
raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./test.db")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL") 
PORT = int(os.getenv("PORT", 8080)) # Render provides a port automatically
if raw_db_url and raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
# --- Database Setup ---
Base = declarative_base()
try:
    engine = create_engine(raw_db_url, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    print("✅ Database Connected Successfully")
except Exception as e:
    print(f"❌ Database Connection Failed: {e}")
    engine = None

def get_db_session():
    if engine:
        return SessionLocal()
    return None

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String)
    side = Column(String)
    price = Column(Float)

class PriceLog(Base):
    __tablename__ = 'prices'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    price = Column(Float)


# --- Discord Notification ---
def send_discord_alert(message):
    if DISCORD_WEBHOOK:
        data = {
            "content": message,
            "username": "Crypto Bot 3000"
        }
        try:
            result = requests.post(DISCORD_WEBHOOK, json=data)
            result.raise_for_status()
        except Exception as e:
            print(f"Discord Send Failed: {e}")
    else:
        print("No Discord Webhook configured.")

# --- The Trading Logic Loop ---
async def trading_loop():
    print("🚀 Trading Bot Logic Started...")
    
    current_price = 45000.0
    
    while True:
        session = get_db_session()
        if not session:
            await asyncio.sleep(5)
            continue

        # 1. Simulate Market Movement
        change = random.uniform(-100, 105) 
        current_price += change
        
        # 2. Log Price
        price_entry = PriceLog(price=current_price)
        session.add(price_entry)
        
        # 3. Strategy: Buy/Sell on volatility
        trade_side = None
        if change > 80: 
            trade_side = "SELL"
        elif change < -80:
            trade_side = "BUY"
            
        if trade_side:
            trade = Trade(symbol="BTC/USD", side=trade_side, price=current_price)
            session.add(trade)
            msg = f"🚨 **{trade_side} ALERT** 🚨\nSymbol: BTC/USD\nPrice: ${current_price:,.2f}"
            print(msg)
            send_discord_alert(msg)
        
        session.commit()
        session.close()
        
        # Sleep for 10 seconds to not flood the free database
        await asyncio.sleep(10)

# --- The Keep-Alive Web Server ---
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_background_tasks(app):
    app['bot_task'] = asyncio.create_task(trading_loop())

async def cleanup_background_tasks(app):
    app['bot_task'].cancel()
    await app['bot_task']

if __name__ == "__main__":
    # Setup the web server to keep Render happy
    app = web.Application()
    app.router.add_get('/', health_check)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    
    print(f"🌍 Starting Web Server on Port {PORT}")
    web.run_app(app, port=PORT)