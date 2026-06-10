from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import json
import os
import httpx
from datetime import datetime

app = FastAPI(title="Gold Scalping AI Server")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ─── Ma'lumot modellari ───────────────────────────────────────────
class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

class OpenPosition(BaseModel):
    ticket: int
    type: str
    lot: float
    open_price: float
    current_price: float
    profit: float
    stop_loss: float
    take_profit: float

class MarketData(BaseModel):
    symbol: str
    current_price: float
    spread: float
    bid: float
    ask: float
    candles_m1: List[Candle]
    candles_m5: List[Candle]
    open_positions: List[OpenPosition]
    account_balance: float
    account_equity: float
    account_margin: float
    account_free_margin: float
    server_time: str

class AIDecision(BaseModel):
    action: str
    lot: float
    take_profit: float
    stop_loss: float
    reason: str
    risk_level: str
    grid_step: float


# ─── Yordamchi funksiyalar ────────────────────────────────────────
def calculate_indicators(candles: List[Candle]) -> dict:
    if len(candles) < 21:
        return {}

    closes = [c.close for c in candles]

    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    ema8  = ema(closes[-8:],  8)
    ema21 = ema(closes[-21:], 21)

    atr_period = min(14, len(candles) - 1)
    true_ranges = []
    for i in range(1, atr_period + 1):
        c = candles[-i]
        p = candles[-i - 1]
        tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        true_ranges.append(tr)
    atr = sum(true_ranges) / len(true_ranges)

    rsi_period = min(14, len(closes) - 1)
    gains, losses = [], []
    for i in range(-rsi_period, 0):
        diff = closes[i] - closes[i - 1]
        (gains if diff > 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / rsi_period if gains else 0
    avg_loss = sum(losses) / rsi_period if losses else 0.0001
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))

    trend = "UP" if ema8 > ema21 else "DOWN" if ema8 < ema21 else "SIDEWAYS"

    return {
        "ema8": round(ema8, 2),
        "ema21": round(ema21, 2),
        "atr": round(atr, 2),
        "rsi": round(rsi, 2),
        "trend": trend,
    }


def check_trading_session(server_time: str) -> dict:
    try:
        dt = datetime.fromisoformat(server_time)
        hour = dt.hour
        if 7 <= hour < 17:
            session = "LONDON" if hour < 12 else "LONDON_NY"
            return {"active": True, "session": session}
        return {"active": False, "session": "CLOSED"}
    except Exception:
        return {"active": True, "session": "UNKNOWN"}


def get_grid_status(positions: List[OpenPosition]) -> dict:
    if not positions:
        return {"count": 0, "avg_price": 0, "total_profit": 0,
                "direction": None, "worst_price": 0}

    total_profit = sum(p.profit for p in positions)
    avg_price = sum(p.open_price * p.lot for p in positions) / sum(p.lot for p in positions)
    direction = positions[0].type if positions else None
    worst_price = (min(p.open_price for p in positions)
                   if direction == "BUY"
                   else max(p.open_price for p in positions))

    return {
        "count": len(positions),
        "avg_price": round(avg_price, 2),
        "total_profit": round(total_profit, 2),
        "direction": direction,
        "worst_price": round(worst_price, 2),
    }


# ─── Asosiy endpoint ─────────────────────────────────────────────
@app.post("/analyze", response_model=AIDecision)
async def analyze_market(data: MarketData):

    ind_m1 = calculate_indicators(data.candles_m1)
    ind_m5 = calculate_indicators(data.candles_m5)
    session = check_trading_session(data.server_time)
    grid = get_grid_status(data.open_positions)

    drawdown_pct = ((data.account_balance - data.account_equity)
                    / data.account_balance * 100) if data.account_balance > 0 else 0

    prompt = f"""Siz professional XAUUSD (Gold) scalping trader AI siz.
Quyidagi bozor ma'lumotlarini tahlil qiling va aniq qaror qabul qiling.

## Joriy Holat
- Narx: {data.current_price}
- Spread: {data.spread:.1f} pip
- Balans: ${data.account_balance:.2f}
- Kapital: ${data.account_equity:.2f}
- Erkin margin: ${data.account_free_margin:.2f}
- Drawdown: {drawdown_pct:.1f}%
- Sessiya: {session['session']} (Faol: {session['active']})

## Texnik Indikatorlar
### M1:
- EMA8: {ind_m1.get('ema8', 'N/A')}, EMA21: {ind_m1.get('ema21', 'N/A')}
- ATR: {ind_m1.get('atr', 'N/A')}, RSI: {ind_m1.get('rsi', 'N/A')}
- Trend: {ind_m1.get('trend', 'N/A')}

### M5:
- EMA8: {ind_m5.get('ema8', 'N/A')}, EMA21: {ind_m5.get('ema21', 'N/A')}
- ATR: {ind_m5.get('atr', 'N/A')}, RSI: {ind_m5.get('rsi', 'N/A')}
- Trend: {ind_m5.get('trend', 'N/A')}

## Grid Holati
- Ochiq: {grid['count']} ta, O'rtacha narx: {grid['avg_price']}
- Jami P/L: ${grid['total_profit']:.2f}, Yo'nalish: {grid['direction']}

## Qoidalar
1. Spread > 40 pip → WAIT
2. Sessiya yopiq → WAIT
3. Drawdown > 15% → CLOSE_ALL
4. Grid 5 tadan oshsa → yangi ochma
5. TP = 50-80 pip, SL = 30-40 pip
6. RSI > 75 = SELL signal, RSI < 25 = BUY signal
7. M5 va M1 trend bir xil bo'lsa → kuchli signal

Faqat JSON formatda javob ber, boshqa hech narsa yozma:
{{"action": "BUY|SELL|WAIT|CLOSE_ALL|CLOSE_PROFIT", "lot": 0.01, "take_profit": 60, "stop_loss": 35, "reason": "sabab uzbek tilida", "risk_level": "LOW|MEDIUM|HIGH", "grid_step": 40}}"""

    # Groq API ga so'rov
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.1
            },
            timeout=15.0
        )

    response_text = response.json()["choices"][0]["message"]["content"].strip()

    try:
        clean = response_text.replace("```json", "").replace("```", "").strip()
        decision = json.loads(clean)
        return AIDecision(**decision)
    except Exception as e:
        return AIDecision(
            action="WAIT",
            lot=0.01,
            take_profit=60,
            stop_loss=35,
            reason=f"Tahlil xatosi: {str(e)}",
            risk_level="LOW",
            grid_step=40
        )


# ─── Sog'liq tekshiruvi ───────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "server": "Gold Scalping AI", "ai": "Groq LLaMA"}

@app.get("/")
async def root():
    return {"message": "Gold Scalping AI Server ishlayapti! ✅"}
