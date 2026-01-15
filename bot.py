import asyncio
import json
import os
import logging
import pandas as pd
import pandas_ta as ta
import websockets
import numpy as np
from datetime import datetime, timezone
from aiohttp import web, ClientSession
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, inspect
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trading_bot_pro.db")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("QuantBotPro")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

Base = declarative_base()

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    symbol = Column(String, default="BTC/USD")
    side = Column(String)
    price = Column(Float)
    quantity = Column(Float)
    usd_balance = Column(Float)
    btc_balance = Column(Float)
    reason = Column(String)

class PriceLog(Base):
    __tablename__ = 'prices'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    price = Column(Float)

class IndicatorLog(Base):
    __tablename__ = 'indicators'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    rsi = Column(Float)
    sma_20 = Column(Float)
    ema_200 = Column(Float)

class Portfolio(Base):
    __tablename__ = 'portfolio'
    id = Column(Integer, primary_key=True)
    usd_balance = Column(Float, default=10000.0)
    btc_balance = Column(Float, default=0.0)
    in_position = Column(Boolean, default=False)
    entry_price = Column(Float, default=0.0)
    highest_price = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    if not engine: return
    Base.metadata.create_all(engine)
    session = SessionLocal()
    if not session.query(Portfolio).first():
        session.add(Portfolio(usd_balance=10000.0, btc_balance=0.0))
        session.commit()
    session.close()

async def send_discord_alert(http_session, message):
    if DISCORD_WEBHOOK:
        try:
            await http_session.post(DISCORD_WEBHOOK, json={"content": message, "username": "Quant Bot Pro"})
        except Exception as e:
            logger.error(f"Discord Error: {e}")

class StrategyEngine:
    def __init__(self):
        self.df = pd.DataFrame()

    def update(self, candle):
        new_row = {
            'timestamp': pd.to_datetime(candle['t'], unit='ms'),
            'open': float(candle['o']), 'high': float(candle['h']),
            'low': float(candle['l']), 'close': float(candle['c']),
            'volume': float(candle['v'])
        }
        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True).tail(300)

    def analyze(self):
        if self.df.empty: return None

        # Check data sufficiency
        has_enough_data = len(self.df) >= 200
        
        # Calculate Indicators (Safe Mode)
        if len(self.df) >= 14: self.df.ta.rsi(length=14, append=True)
        if len(self.df) >= 20: self.df.ta.sma(length=20, append=True)
        if len(self.df) >= 200: self.df.ta.ema(length=200, append=True)
        if len(self.df) >= 35: self.df.ta.macd(append=True)

        curr = self.df.iloc[-1]
        prev = self.df.iloc[-2] if len(self.df) > 1 else curr
        
        # --- CRITICAL FIX: Convert NumPy types to Python floats ---
        def safe_float(val):
            if hasattr(val, "item"): 
                return float(val.item())  # Handle numpy types
            try:
                return float(val)
            except:
                return 0.0

        return {
            'ready': has_enough_data,
            'price': safe_float(curr['close']),
            'rsi': safe_float(curr.get('RSI_14', 50)),
            'sma_20': safe_float(curr.get('SMA_20', 0)),
            'ema_200': safe_float(curr.get('EMA_200', 0)),
            'macd_h': safe_float(curr.get('MACDh_12_26_9', 0)),
            'macd_h_prev': safe_float(prev.get('MACDh_12_26_9', 0))
        }

async def process_market_update(signals, http_session):
    with SessionLocal() as session:
        # 1. Log Price (Converted to native float)
        session.add(PriceLog(price=signals['price']))
        session.add(IndicatorLog(
            rsi=signals['rsi'], 
            sma_20=signals['sma_20'], 
            ema_200=signals['ema_200']
        ))
        
        portfolio = session.query(Portfolio).first()
        
        # 2. Warmup Check
        if not signals['ready']:
            logger.info(f"❄️ Warming up... Data points: {len(signals.get('ema_200_hist', [])) if isinstance(signals.get('ema_200_hist'), list) else 'Collecting...'}")
            session.commit()
            return

        # 3. Trade Logic
        price = signals['price']
        trade_side = None
        reason = ""
        
        # Simple trend check
        is_uptrend = price > signals['ema_200']
        
        if not portfolio.in_position:
            # Buy Condition
            if is_uptrend and signals['rsi'] < 40 and signals['macd_h'] > signals['macd_h_prev']:
                trade_side = "BUY"
                reason = "Uptrend RSI Pullback"
                qty = (portfolio.usd_balance * 0.99) / price
                portfolio.btc_balance = float(qty)
                portfolio.usd_balance -= float(qty * price)
                portfolio.in_position = True
                portfolio.entry_price = price
                portfolio.highest_price = price

        elif portfolio.in_position:
            # Manage Position
            if price > portfolio.highest_price:
                portfolio.highest_price = price
            
            pnl = (price - portfolio.entry_price) / portfolio.entry_price
            drawdown = (portfolio.highest_price - price) / portfolio.highest_price
            
            # Sell Conditions
            if signals['rsi'] > 70:
                trade_side = "SELL"
                reason = "RSI Overbought"
            elif drawdown > 0.015:
                trade_side = "SELL"
                reason = "Trailing Stop (1.5%)"
            elif pnl < -0.02:
                trade_side = "SELL"
                reason = "Stop Loss (-2%)"

            if trade_side == "SELL":
                portfolio.usd_balance += float(portfolio.btc_balance * price)
                portfolio.btc_balance = 0.0
                portfolio.in_position = False

        if trade_side:
            new_trade = Trade(
                symbol="BTC/USD", side=trade_side, price=price, 
                quantity=portfolio.btc_balance if trade_side=="BUY" else 0,
                usd_balance=float(portfolio.usd_balance), btc_balance=float(portfolio.btc_balance),
                reason=reason
            )
            session.add(new_trade)
            msg = f"🚨 **{trade_side}** | Price: ${price:,.2f} | RSI: {signals['rsi']:.1f} | Reason: {reason}"
            logger.info(msg)
            await send_discord_alert(http_session, msg)
        
        portfolio.last_updated = datetime.now(timezone.utc)
        session.commit()

async def market_data_loop(http_session):
    strategy = StrategyEngine()
    logger.info(f"🚀 Real-Time Trading Engine Started")
    
    while True:
        try:
            async for websocket in websockets.connect(BINANCE_WS_URL):
                try:
                    while True:
                        msg = await websocket.recv()
                        data = json.loads(msg)
                        candle = data['k']
                        
                        if candle['x']: # Candle closed
                            strategy.update(candle)
                            signals = strategy.analyze()
                            if signals:
                                await process_market_update(signals, http_session)
                                logger.info(f"Tick: ${signals['price']:,.2f} | RSI: {signals['rsi']:.1f}")
                        
                except websockets.ConnectionClosed:
                    logger.warning("Reconnecting...")
                    break
        except Exception as e:
            logger.error(f"Error: {e}")
            await asyncio.sleep(5)

async def health_check(request):
    return web.Response(text="Bot Active")

async def start_background_tasks(app):
    app['http_session'] = ClientSession()
    app['bot_task'] = asyncio.create_task(market_data_loop(app['http_session']))

async def cleanup_background_tasks(app):
    app['bot_task'].cancel()
    await app['http_session'].close()

if __name__ == "__main__":
    init_db()
    app = web.Application()
    app.router.add_get('/', health_check)
    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)
    web.run_app(app, port=PORT)