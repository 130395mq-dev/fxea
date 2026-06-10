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


def calculate_indicators(candles: List[Candle]) -> dict:
    if len(candles) < 21:
        return {"ema8": 0, "ema21": 0, "atr": 0, "rsi": 50, "trend": "SIDEWAYS"}

    closes = [c.close for c in candles]

    def ema(data, period):
        k = 2 / (period + 1)
        v = data[0]
        for p in data[1:]:
            v = p * k + v * (1 - k)
        return v

    ema8  = ema(closes[-8:],  8)
    ema21 = ema(closes[-21:], 21)

    atr_period = min(14, len(candles) - 1)
    trs = []
    for i in range(1, atr_period + 1):
        c, p = candles[-i], candles[-i-1]
        trs.append(max(c.high-c.low, abs(c.high-p.close), abs(c.low-p.close)))
    atr = sum(trs) / len(trs) if trs else 0

    rsi_period = min(14, len(closes) - 1)
    gains, losses = [], []
    for i in range(-rsi_period, 0):
        d = closes[i] - closes[i-1]
        (gains if d > 0 else losses).append(abs(d))
    ag = sum(gains)/rsi_period if gains else 0
    al = sum(losses)/rsi_period if losses else 0.0001
    rsi = 100 - (100 / (1 + ag/al))

    diff = abs(ema8 - ema21)
    if diff < 0.3:
        trend = "SIDEWAYS"
    elif ema8 > ema21:
        trend = "UP"
    else:
        trend = "DOWN"

    return {"ema8": round(ema8,2), "ema21": round(ema21,2),
            "atr": round(atr,2), "rsi": round(rsi,2), "trend": trend}


def check_session(server_time: str) -> dict:
    try:
        hour = datetime.fromisoformat(server_time).hour
        if 7 <= hour < 17:
            return {"active": True, "session": "LONDON" if hour < 12 else "LONDON_NY"}
        return {"active": False, "session": "CLOSED"}
    except:
        return {"active": True, "session": "UNKNOWN"}


def get_grid_status(positions: List[OpenPosition]) -> dict:
    if not positions:
        return {"count": 0, "avg_price": 0, "total_profit": 0, "direction": "NONE"}
    total_lot = sum(p.lot for p in positions)
    avg_price = sum(p.open_price * p.lot for p in positions) / total_lot if total_lot > 0 else 0
    return {
        "count": len(positions),
        "avg_price": round(avg_price, 2),
        "total_profit": round(sum(p.profit for p in positions), 2),
        "direction": positions[0].type
    }


@app.post("/analyze", response_model=AIDecision)
async def analyze_market(data: MarketData):

    m1 = calculate_indicators(data.candles_m1)
    m5 = calculate_indicators(data.candles_m5)
    session = check_session(data.server_time)
    grid = get_grid_status(data.open_positions)
    drawdown = ((data.account_balance - data.account_equity) / data.account_balance * 100) if data.account_balance > 0 else 0

    # M5 trend asosiy yo'nalish
    main_trend = m5["trend"]
    grid_dir   = grid["direction"]

    prompt = f"""Sen XAUUSD scalping trader AI san. Qat'iy qoidalarga amal qil.

BOZOR:
- Narx: {data.current_price}, Spread: {data.spread:.0f} pip
- Balans: ${data.account_balance:.2f}, Drawdown: {drawdown:.1f}%
- Sessiya: {session['session']} (Faol: {session['active']})

INDIKATORLAR:
- M5 trend: {m5['trend']} | EMA8={m5['ema8']} EMA21={m5['ema21']} | RSI={m5['rsi']:.1f} | ATR={m5['atr']:.1f}
- M1 trend: {m1['trend']} | EMA8={m1['ema8']} EMA21={m1['ema21']} | RSI={m1['rsi']:.1f}

GRID:
- Ochiq: {grid['count']} ta | Yo'nalish: {grid_dir} | O'rtacha: {grid['avg_price']} | P/L: ${grid['total_profit']:.2f}

QATIY QOIDALAR (buzib bo'lmaydi):
1. Spread > 40 pip → WAIT
2. Sessiya yopiq → WAIT
3. Drawdown > 15% → CLOSE_ALL
4. Grid 5 tadan oshgan → WAIT
5. M5 trend DOWN bo'lsa → FAQAT SELL yoki WAIT (BUY MUTLAQO YO'Q)
6. M5 trend UP bo'lsa → FAQAT BUY yoki WAIT (SELL MUTLAQO YO'Q)
7. M5 trend SIDEWAYS → WAIT (kirmaydi)
8. Grid ochiq BUY bo'lsa → SELL ochma, faqat BUY yoki WAIT
9. Grid ochiq SELL bo'lsa → BUY ochma, faqat SELL yoki WAIT
10. M1 va M5 trend bir xil bo'lsagina kir
11. ATR < 0.5 → WAIT (harakat yo'q)
12. Kuchli trend (EMA farqi katta) + RSI haddan oshgan → WAIT

Faqat JSON, boshqa hech narsa yozma:
{{"action":"BUY|SELL|WAIT|CLOSE_ALL|CLOSE_PROFIT","lot":0.01,"take_profit":150,"stop_loss":80,"reason":"sabab uzbekcha","risk_level":"LOW|MEDIUM|HIGH","grid_step":40}}"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 150, "temperature": 0.1},
                timeout=15.0
            )
        text = resp.json()["choices"][0]["message"]["content"].strip()
        clean = text.replace("```json","").replace("```","").strip()
        decision = json.loads(clean)

        # Xavfsizlik filtri — server tomonidan ham tekshirish
        action = decision.get("action", "WAIT")
        if main_trend == "DOWN" and action == "BUY":
            decision["action"] = "WAIT"
            decision["reason"] = "M5 trend DOWN — BUY bloklanди"
        elif main_trend == "UP" and action == "SELL":
            decision["action"] = "WAIT"
            decision["reason"] = "M5 trend UP — SELL bloklanди"
        elif main_trend == "SIDEWAYS":
            decision["action"] = "WAIT"
            decision["reason"] = "Sideways bozor — kutilmoqda"
        elif grid_dir == "BUY" and action == "SELL":
            decision["action"] = "WAIT"
            decision["reason"] = "BUY grid ochiq — SELL bloklanди"
        elif grid_dir == "SELL" and action == "BUY":
            decision["action"] = "WAIT"
            decision["reason"] = "SELL grid ochiq — BUY bloklanди"

        return AIDecision(**decision)

    except Exception as e:
        return AIDecision(action="WAIT", lot=0.01, take_profit=150,
                         stop_loss=80, reason=f"Xato: {str(e)}", risk_level="LOW", grid_step=40)


@app.get("/health")
async def health():
    return {"status": "ok", "server": "Gold Scalping AI", "ai": "Groq LLaMA"}

@app.get("/")
async def root():
    return {"message": "Gold Scalping AI Server ishlayapti! ✅"}
