# Gold AI Grid Tizimi — O'rnatish Qo'llanmasi

## Tizim Tuzilmasi
```
GitHub (kod) → Railway (AI Server) ↔ MT5 (EA)
```

---

## 1-QADAM: GitHub ga Yuklash

1. GitHub da yangi repo oching: `gold-ai-grid`
2. Quyidagi fayllarni yuklang:
   - `main.py`
   - `requirements.txt`
   - `Procfile`

---

## 2-QADAM: Railway Deploy

1. https://railway.app ga kiring
2. "New Project" → "Deploy from GitHub repo"
3. `gold-ai-grid` ni tanlang
4. **Environment Variables** ga qo'shing:
   ```
   ANTHROPIC_API_KEY = sk-ant-xxxxxxxx (Anthropic API key)
   ```
5. Deploy bo'lgandan keyin URL oling:
   ```
   https://gold-ai-grid-xxxx.railway.app
   ```

---

## 3-QADAM: MT5 EA O'rnatish

1. `GoldAIGrid.mq5` faylini oling
2. MT5 → `File → Open Data Folder`
3. `MQL5/Experts/` papkasiga ko'chiring
4. MT5 → `Navigator → Expert Advisors` → Refresh
5. `GoldAIGrid` ni XAUUSD chartiga tashlang

### EA Sozlamalari:
| Parametr | Qiymat |
|---|---|
| AI_SERVER_URL | Railway URL ingiz |
| SYMBOL | XAUUSDc |
| AI_INTERVAL | 30 (sekund) |
| MAX_GRID | 5 |
| GRID_STEP | 40 |
| DAILY_TARGET | 10.0 |
| DAILY_MAX_LOSS | 4.0 |
| MAX_DRAWDOWN | 15.0 |

---

## 4-QADAM: MT5 WebRequest Ruxsati

1. MT5 → `Tools → Options → Expert Advisors`
2. ✅ "Allow WebRequest for listed URL"
3. Railway URL ni qo'shing

---

## Muhim Eslatmalar

- ⚠️ Avval **Demo account** da sinab ko'ring!
- ✅ Exness Cent account: XAUUSDc symbol ishlatadi
- 💰 Tavsiya depozit: $200 cent
- 🕐 London + NY sessiyasida ishlaydi (07:00-17:00 UTC)

---

## Tizim Ishlash Tartibi

```
1. MT5 yoqiladi
2. Har 30 sekundda AI ga so'rov
3. AI tahlil qiladi → qaror beradi
4. EA qarorni bajaradi
5. Kunlik $10 yutilsa → to'xtaydi
6. Drawdown 15% ga yetsa → hammasi yopiladi
```
