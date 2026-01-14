import asyncio
import random
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from aiohttp import web
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./test.db")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL") 
PORT = int(os.getenv("PORT", 8080))

if raw_db_url and raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)

Base = declarative_base()

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String)
    side = Column(String)
    price = Column(Float)
    quantity = Column(Float)
    usd_balance = Column(Float)
    btc_balance = Column(Float)

class PriceLog(Base):
    __tablename__ = 'prices'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    price = Column(Float)

class IndicatorLog(Base):
    __tablename__ = 'indicators'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    rsi = Column(Float)
    sma_20 = Column(Float)

class Portfolio(Base):
    __tablename__ = 'portfolio'
    id = Column(Integer, primary_key=True)
    usd_balance = Column(Float, default=10000.0)
    btc_balance = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow)

try:
    engine = create_engine(raw_db_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    print("✅ Database Engine Initialized")
except Exception as e:
    print(f"❌ Database Engine Failed: {e}")
    engine = None

def get_db_session():
    if engine:
        return SessionLocal()
    return None

def init_db():
    if engine:
        try:
            Base.metadata.create_all(engine)
            session = SessionLocal()
            portfolio = session.query(Portfolio).first()
            if not portfolio:
                initial_portfolio = Portfolio(usd_balance=10000.0, btc_balance=0.0)
                session.add(initial_portfolio)
                session.commit()
                print("✅ Portfolio Initialized with $10,000")
            session.close()
            print("✅ Tables Verified")
        except Exception as e:
            print(f"❌ Error creating tables: {e}")

def send_discord_alert(message):
    if DISCORD_WEBHOOK:
        data = {"content": message, "username": "Quant Bot Pro"}
        try:
            requests.post(DISCORD_WEBHOOK, json=data)
        except Exception:
            pass

def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return 50.0
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum()/period
    down = -seed[seed < 0].sum()/period
    if down == 0: return 100.0
    rs = up/down
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100./(1. + rs)

    for i in range(period, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta
        
        up = (up*(period-1) + upval)/period
        down = (down*(period-1) + downval)/period
        if down == 0:
            rs = 0
        else:
            rs = up/down
        rsi[i] = 100. - 100./(1. + rs)
    return float(rsi[-1])

async def trading_loop():
    print("🚀 Advanced Trading Logic Started...")
    current_price = 45000.0
    
    while True:
        session = get_db_session()
        if not session:
            await asyncio.sleep(5)
            continue

        try:
            change = random.uniform(-150, 155) 
            current_price += change
            
            price_entry = PriceLog(price=current_price)
            session.add(price_entry)
            session.commit()

            history = session.query(PriceLog.price).order_by(PriceLog.id.desc()).limit(30).all()
            price_list = [p[0] for p in history][::-1]

            rsi_value = 50.0
            sma_value = 0.0

            if len(price_list) >= 14:
                rsi_value = calculate_rsi(price_list)
            
            if len(price_list) >= 20:
                sma_value = sum(price_list[-20:]) / 20
            
            ind_log = IndicatorLog(rsi=float(rsi_value), sma_20=float(sma_value))
            session.add(ind_log)

            portfolio = session.query(Portfolio).first()
            trade_side = None
            quantity = 0.0
            
            if rsi_value < 30 and portfolio.usd_balance > 100:
                trade_side = "BUY"
                quantity = (portfolio.usd_balance * 0.98) / current_price
                portfolio.btc_balance += quantity
                portfolio.usd_balance -= (quantity * current_price)
            
            elif rsi_value > 70 and portfolio.btc_balance > 0.001:
                trade_side = "SELL"
                quantity = portfolio.btc_balance
                portfolio.usd_balance += (quantity * current_price)
                portfolio.btc_balance = 0.0

            if trade_side:
                trade = Trade(
                    symbol="BTC/USD", 
                    side=trade_side, 
                    price=current_price, 
                    quantity=quantity,
                    usd_balance=portfolio.usd_balance,
                    btc_balance=portfolio.btc_balance
                )
                session.add(trade)
                
                total_val = portfolio.usd_balance + (portfolio.btc_balance * current_price)
                msg = (f"🚨 **{trade_side} EXECUTION** 🚨\n"
                       f"Price: ${current_price:,.2f}\n"
                       f"RSI: {rsi_value:.2f}\n"
                       f"Portfolio Value: ${total_val:,.2f}")
                print(msg)
                send_discord_alert(msg)
            
            session.commit()
            
        except Exception as e:
            print(f"Loop Error: {e}")
            session.rollback()
        finally:
            session.close()
        
        await asyncio.sleep(5)

async def health_check(request):
    return web.Response(text="Advanced Bot Running")

async def start_background_tasks(app):
    app['bot_task'] = asyncio.create_task(trading_loop())

async def cleanup_background_tasks(app):
    app['bot_task'].cancel()
    await app['bot_task']

if __name__ == "__main__":
    init_db()
    app = web.Application()
    app.router.add_get('/', health_check)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    web.run_app(app, port=PORT)