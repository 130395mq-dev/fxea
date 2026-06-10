from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import anthropic
import json
from datetime import datetime

app = FastAPI(title="Gold Scalping AI Server")

client = anthropic.Anthropic()

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
    type: str        # "BUY" or "SELL"
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
    candles_m1: List[Candle]   # oxirgi 50 ta M1 shamcha
    candles_m5: List[Candle]   # oxirgi 20 ta M5 shamcha
    open_positions: List[OpenPosition]
    account_balance: float
    account_equity: float
    account_margin: float
    account_free_margin: float
    server_time: str

class AIDecision(BaseModel):
    action: str           # "BUY", "SELL", "CLOSE_ALL", "CLOSE_PROFIT", "WAIT"
    lot: float
    take_profit: float    # pip
    stop_loss: float      # pip
    reason: str
    risk_level: str       # "LOW", "MEDIUM", "HIGH"
    grid_step: float      # pip


# ─── Yordamchi funksiyalar ────────────────────────────────────────
def calculate_indicators(candles: List[Candle]) -> dict:
    if len(candles) < 21:
        return {}

    closes = [c.close for c in candles]

    # EMA hisoblash
    def ema(data, period):
        k = 2 / (period + 1)
        ema_val = data[0]
        for price in data[1:]:
            ema_val = price * k + ema_val * (1 - k)
        return ema_val

    ema8  = ema(closes[-8:],  8)
    ema21 = ema(closes[-21:], 21)

    # ATR hisoblash (14 davr)
    atr_period = min(14, len(candles) - 1)
    true_ranges = []
    for i in range(1, atr_period + 1):
        c = candles[-i]
        p = candles[-i - 1]
        tr = max(c.high - c.low,
                 abs(c.high - p.close),
                 abs(c.low  - p.close))
        true_ranges.append(tr)
    atr = sum(true_ranges) / len(true_ranges)

    # RSI hisoblash (14 davr)
    rsi_period = min(14, len(closes) - 1)
    gains, losses = [], []
    for i in range(-rsi_period, 0):
        diff = closes[i] - closes[i - 1]
        (gains if diff > 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / rsi_period if gains else 0
    avg_loss = sum(losses) / rsi_period if losses else 0.0001
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))

    # Trend yo'nalishi
    trend = "UP" if ema8 > ema21 else "DOWN" if ema8 < ema21 else "SIDEWAYS"

    return {
        "ema8": round(ema8, 2),
        "ema21": round(ema21, 2),
        "atr": round(atr, 2),
        "rsi": round(rsi, 2),
        "trend": trend,
    }


def check_trading_session(server_time: str) -> dict:
    """London + NY sessiyasini tekshirish"""
    try:
        dt = datetime.fromisoformat(server_time)
        hour = dt.hour
        # London: 07:00-17:00, NY overlap: 12:00-17:00
        if 7 <= hour < 17:
            session = "LONDON" if hour < 12 else "LONDON_NY"
            return {"active": True, "session": session}
        return {"active": False, "session": "CLOSED"}
    except Exception:
        return {"active": True, "session": "UNKNOWN"}


def calculate_lot(balance: float, risk_percent: float,
                  stop_loss_pip: float, pip_value: float = 0.01) -> float:
    """Risk asosida lot hisoblash"""
    risk_amount = balance * (risk_percent / 100)
    lot = risk_amount / (stop_loss_pip * pip_value)
    lot = round(max(0.01, min(lot, 0.5)), 2)
    return lot


def get_grid_status(positions: List[OpenPosition]) -> dict:
    if not positions:
        return {"count": 0, "avg_price": 0, "total_profit": 0,
                "direction": None, "worst_price": 0}

    total_profit = sum(p.profit for p in positions)
    avg_price    = sum(p.open_price * p.lot for p in positions) / sum(p.lot for p in positions)
    direction    = positions[0].type if positions else None
    worst_price  = (min(p.open_price for p in positions)
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

    # 1. Indikatorlar
    ind_m1 = calculate_indicators(data.candles_m1)
    ind_m5 = calculate_indicators(data.candles_m5)

    # 2. Sessiya
    session = check_trading_session(data.server_time)

    # 3. Grid holati
    grid = get_grid_status(data.open_positions)

    # 4. Drawdown tekshirish
    drawdown_pct = ((data.account_balance - data.account_equity)
                    / data.account_balance * 100) if data.account_balance > 0 else 0

    # 5. AI prompt
    prompt = f"""
Siz professional XAUUSD (Gold) scalping trader AI siz.
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
### M1 (tezkor signal):
- EMA8: {ind_m1.get('ema8', 'N/A')}
- EMA21: {ind_m1.get('ema21', 'N/A')}
- ATR: {ind_m1.get('atr', 'N/A')} (volatillik)
- RSI: {ind_m1.get('rsi', 'N/A')}
- Trend: {ind_m1.get('trend', 'N/A')}

### M5 (asosiy trend):
- EMA8: {ind_m5.get('ema8', 'N/A')}
- EMA21: {ind_m5.get('ema21', 'N/A')}
- ATR: {ind_m5.get('atr', 'N/A')}
- RSI: {ind_m5.get('rsi', 'N/A')}
- Trend: {ind_m5.get('trend', 'N/A')}

## Grid Holati
- Ochiq pozitsiyalar: {grid['count']} ta
- O'rtacha narx: {grid['avg_price']}
- Jami foyda/zarar: ${grid['total_profit']:.2f}
- Yo'nalish: {grid['direction']}
- Eng yomon narx: {grid['worst_price']}

## Qaror Qoidalari
1. Spread > 40 pip bo'lsa → WAIT
2. Sessiya yopiq bo'lsa → WAIT (yoki foydali pozitsiyalarni yop)
3. Drawdown > 15% bo'lsa → CLOSE_ALL
4. Grid 5 tadan oshsa → yangi ochma
5. Scalping: TP = 50-80 pip, SL = 30-40 pip (spread hisobga olingan)
6. M5 trend bilan M1 signal mos kelsa → KUCHLI signal
7. RSI: >75 = o'ta sotib olingan, <25 = o'ta sotilgan
8. Ochiq pozitsiyalar foyda ko'rsatsa va trend o'zgarsa → CLOSE_PROFIT

## Muhim
- XAUUSD cent account: 1 lot = 100 oz, pip = $0.01
- Kunlik maqsad: $10, maksimal zarar: $4
- Lot: 0.01 dan 0.10 gacha (xavfsiz)

Faqat JSON formatda javob bering, boshqa hech narsa yozmang:
{{
  "action": "BUY|SELL|WAIT|CLOSE_ALL|CLOSE_PROFIT",
  "lot": 0.01,
  "take_profit": 60,
  "stop_loss": 35,
  "reason": "qisqa sabab o'zbek tilida",
  "risk_level": "LOW|MEDIUM|HIGH",
  "grid_step": 40
}}
"""

    # 6. Claude API ga so'rov
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()

    # 7. JSON parse
    try:
        # ```json ... ``` ni tozalash
        clean = response_text.replace("```json", "").replace("```", "").strip()
        decision = json.loads(clean)
        return AIDecision(**decision)
    except Exception as e:
        # Xatolik bo'lsa xavfsiz qaror
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
    return {"status": "ok", "server": "Gold Scalping AI"}


@app.get("/")
async def root():
    return {"message": "Gold Scalping AI Server ishlayapti! ✅"}
