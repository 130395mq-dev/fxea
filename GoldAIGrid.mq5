//+------------------------------------------------------------------+
//| Gold Scalping AI Grid EA                                         |
//| XAUUSD - Exness Cent Account                                     |
//+------------------------------------------------------------------+
#property copyright "Gold AI Grid"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

CTrade        trade;
CPositionInfo posInfo;

//--- Input parametrlar
input string   AI_SERVER_URL  = "https://your-app.railway.app/analyze";
input string   SYMBOL         = "XAUUSDc";    // Exness cent symbol
input int      AI_INTERVAL    = 30;           // sekundda bir marta AI so'rovi
input int      MAX_GRID       = 5;            // maksimal grid soni
input double   GRID_STEP      = 40;           // pip orasidagi masofa
input double   DAILY_TARGET   = 10.0;         // kunlik maqsad ($)
input double   DAILY_MAX_LOSS = 4.0;          // kunlik max zarar ($)
input double   MAX_DRAWDOWN   = 15.0;         // % drawdown limiti
input bool     USE_NEWS_FILTER = true;        // yangiliklar filtri

//--- Global o'zgaruvchilar
datetime lastAICall   = 0;
double   dayStartBalance = 0;
datetime dayStartTime    = 0;
double   pipValue        = 0.1; // XAUUSD cent uchun

//+------------------------------------------------------------------+
//| EA ishga tushishi                                                |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("Gold AI Grid EA ishga tushdi");
   dayStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   dayStartTime    = TimeCurrent();
   trade.SetExpertMagicNumber(20240101);
   trade.SetDeviationInPoints(30);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Har tikda ishlaydigan funksiya                                   |
//+------------------------------------------------------------------+
void OnTick()
{
   // Kunlik limitlarni tekshirish
   if (!CheckDailyLimits()) return;

   // Drawdown tekshirish
   if (!CheckDrawdown()) return;

   // AI ga so'rov vaqti kelganmi?
   if (TimeCurrent() - lastAICall < AI_INTERVAL) return;
   lastAICall = TimeCurrent();

   // Ma'lumotlarni yig'ish
   string jsonData = CollectMarketData();
   if (jsonData == "") return;

   // AI ga so'rov yuborish
   string aiResponse = SendToAI(jsonData);
   if (aiResponse == "") return;

   // AI qarorini bajarish
   ExecuteAIDecision(aiResponse);
}

//+------------------------------------------------------------------+
//| Kunlik limitlar tekshiruvi                                       |
//+------------------------------------------------------------------+
bool CheckDailyLimits()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double dailyPnL = balance - dayStartBalance;

   // Yangi kun boshlanganmi?
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   MqlDateTime dtStart;
   TimeToStruct(dayStartTime, dtStart);
   if (dt.day != dtStart.day) {
      dayStartBalance = balance;
      dayStartTime    = TimeCurrent();
      Print("Yangi kun boshlandi. Balans: ", balance);
      return true;
   }

   // Kunlik maqsadga yetdikmi?
   if (dailyPnL >= DAILY_TARGET) {
      CloseAllPositions("Kunlik maqsad yutildi!");
      Print("Kunlik maqsad $", DAILY_TARGET, " ga yetdi. Bugun to'xtaydi.");
      return false;
   }

   // Kunlik max zarar?
   if (dailyPnL <= -DAILY_MAX_LOSS) {
      CloseAllPositions("Kunlik max zarar!");
      Print("Kunlik max zarar $", DAILY_MAX_LOSS, " ga yetdi. Bugun to'xtaydi.");
      return false;
   }

   return true;
}

//+------------------------------------------------------------------+
//| Drawdown tekshiruvi                                              |
//+------------------------------------------------------------------+
bool CheckDrawdown()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   if (balance <= 0) return false;

   double drawdown = (balance - equity) / balance * 100;
   if (drawdown >= MAX_DRAWDOWN) {
      CloseAllPositions("MAX DRAWDOWN!");
      Print("Drawdown ", drawdown, "% ga yetdi! Hammasi yopildi.");
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Bozor ma'lumotlarini yig'ish                                     |
//+------------------------------------------------------------------+
string CollectMarketData()
{
   double bid    = SymbolInfoDouble(SYMBOL, SYMBOL_BID);
   double ask    = SymbolInfoDouble(SYMBOL, SYMBOL_ASK);
   double spread = (ask - bid) / SymbolInfoDouble(SYMBOL, SYMBOL_POINT) / 10;

   // M1 shamchalar (oxirgi 50 ta)
   string candlesM1 = GetCandles(SYMBOL, PERIOD_M1, 50);
   // M5 shamchalar (oxirgi 20 ta)
   string candlesM5 = GetCandles(SYMBOL, PERIOD_M5, 20);

   // Ochiq pozitsiyalar
   string positions = GetOpenPositions();

   // Vaqt
   datetime now = TimeCurrent();
   string timeStr = TimeToString(now, TIME_DATE|TIME_MINUTES|TIME_SECONDS);

   string json = "{";
   json += "\"symbol\":\"" + SYMBOL + "\",";
   json += "\"current_price\":" + DoubleToString(bid, 2) + ",";
   json += "\"spread\":" + DoubleToString(spread, 1) + ",";
   json += "\"bid\":" + DoubleToString(bid, 2) + ",";
   json += "\"ask\":" + DoubleToString(ask, 2) + ",";
   json += "\"candles_m1\":" + candlesM1 + ",";
   json += "\"candles_m5\":" + candlesM5 + ",";
   json += "\"open_positions\":" + positions + ",";
   json += "\"account_balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + ",";
   json += "\"account_equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2) + ",";
   json += "\"account_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2) + ",";
   json += "\"account_free_margin\":" + DoubleToString(AccountInfoDouble(ACCOUNT_FREEMARGIN), 2) + ",";
   json += "\"server_time\":\"" + timeStr + "\"";
   json += "}";

   return json;
}

//+------------------------------------------------------------------+
//| Shamchalarni JSON ga o'girish                                    |
//+------------------------------------------------------------------+
string GetCandles(string sym, ENUM_TIMEFRAMES tf, int count)
{
   MqlRates rates[];
   int copied = CopyRates(sym, tf, 0, count, rates);
   if (copied <= 0) return "[]";

   string result = "[";
   for (int i = 0; i < copied; i++) {
      if (i > 0) result += ",";
      result += "{";
      result += "\"time\":" + IntegerToString(rates[i].time) + ",";
      result += "\"open\":" + DoubleToString(rates[i].open, 2) + ",";
      result += "\"high\":" + DoubleToString(rates[i].high, 2) + ",";
      result += "\"low\":" + DoubleToString(rates[i].low, 2) + ",";
      result += "\"close\":" + DoubleToString(rates[i].close, 2) + ",";
      result += "\"volume\":" + IntegerToString(rates[i].tick_volume);
      result += "}";
   }
   result += "]";
   return result;
}

//+------------------------------------------------------------------+
//| Ochiq pozitsiyalarni JSON ga o'girish                            |
//+------------------------------------------------------------------+
string GetOpenPositions()
{
   string result = "[";
   bool first = true;
   for (int i = PositionsTotal() - 1; i >= 0; i--) {
      if (!posInfo.SelectByIndex(i)) continue;
      if (posInfo.Symbol() != SYMBOL) continue;
      if (posInfo.Magic() != 20240101) continue;

      if (!first) result += ",";
      first = false;

      string posType = (posInfo.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
      result += "{";
      result += "\"ticket\":" + IntegerToString(posInfo.Ticket()) + ",";
      result += "\"type\":\"" + posType + "\",";
      result += "\"lot\":" + DoubleToString(posInfo.Volume(), 2) + ",";
      result += "\"open_price\":" + DoubleToString(posInfo.PriceOpen(), 2) + ",";
      result += "\"current_price\":" + DoubleToString(posInfo.PriceCurrent(), 2) + ",";
      result += "\"profit\":" + DoubleToString(posInfo.Profit(), 2) + ",";
      result += "\"stop_loss\":" + DoubleToString(posInfo.StopLoss(), 2) + ",";
      result += "\"take_profit\":" + DoubleToString(posInfo.TakeProfit(), 2);
      result += "}";
   }
   result += "]";
   return result;
}

//+------------------------------------------------------------------+
//| AI serverga so'rov yuborish                                      |
//+------------------------------------------------------------------+
string SendToAI(string jsonData)
{
   char post[], result[];
   string headers = "Content-Type: application/json\r\n";
   StringToCharArray(jsonData, post, 0, StringLen(jsonData));

   int res = WebRequest("POST", AI_SERVER_URL, headers, 10000, post, result, headers);

   if (res == 200) {
      return CharArrayToString(result);
   } else {
      Print("AI server xatosi: ", res);
      return "";
   }
}

//+------------------------------------------------------------------+
//| AI qarorini bajarish                                             |
//+------------------------------------------------------------------+
void ExecuteAIDecision(string response)
{
   // JSON dan qiymatlarni olish
   string action    = ExtractString(response, "action");
   double lot       = ExtractDouble(response, "lot");
   double tp        = ExtractDouble(response, "take_profit");
   double sl        = ExtractDouble(response, "stop_loss");
   string reason    = ExtractString(response, "reason");
   string riskLevel = ExtractString(response, "risk_level");

   Print("AI Qaror: ", action, " | Lot: ", lot, " | TP: ", tp,
         " | SL: ", sl, " | Risk: ", riskLevel, " | Sabab: ", reason);

   double point  = SymbolInfoDouble(SYMBOL, SYMBOL_POINT);
   double bid    = SymbolInfoDouble(SYMBOL, SYMBOL_BID);
   double ask    = SymbolInfoDouble(SYMBOL, SYMBOL_ASK);
   double tpPips = tp * point * 10;
   double slPips = sl * point * 10;

   // Grid soni tekshiruvi
   int gridCount = CountOurPositions();

   if (action == "BUY" && gridCount < MAX_GRID) {
      double tpPrice = ask + tpPips;
      double slPrice = ask - slPips;
      if (trade.Buy(lot, SYMBOL, ask, slPrice, tpPrice, "AI Grid BUY"))
         Print("BUY ochildi: ", ask, " TP:", tpPrice, " SL:", slPrice);
   }
   else if (action == "SELL" && gridCount < MAX_GRID) {
      double tpPrice = bid - tpPips;
      double slPrice = bid + slPips;
      if (trade.Sell(lot, SYMBOL, bid, slPrice, tpPrice, "AI Grid SELL"))
         Print("SELL ochildi: ", bid, " TP:", tpPrice, " SL:", slPrice);
   }
   else if (action == "CLOSE_ALL") {
      CloseAllPositions("AI: " + reason);
   }
   else if (action == "CLOSE_PROFIT") {
      CloseProfitablePositions();
   }
   else if (action == "WAIT") {
      Print("AI: Kutilmoqda — ", reason);
   }
}

//+------------------------------------------------------------------+
//| Bizning pozitsiyalar sonini hisoblash                            |
//+------------------------------------------------------------------+
int CountOurPositions()
{
   int count = 0;
   for (int i = PositionsTotal() - 1; i >= 0; i--) {
      if (posInfo.SelectByIndex(i) &&
          posInfo.Symbol() == SYMBOL &&
          posInfo.Magic() == 20240101)
         count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Barcha pozitsiyalarni yopish                                     |
//+------------------------------------------------------------------+
void CloseAllPositions(string reason)
{
   Print("Barcha pozitsiyalar yopilmoqda: ", reason);
   for (int i = PositionsTotal() - 1; i >= 0; i--) {
      if (posInfo.SelectByIndex(i) &&
          posInfo.Symbol() == SYMBOL &&
          posInfo.Magic() == 20240101)
         trade.PositionClose(posInfo.Ticket());
   }
}

//+------------------------------------------------------------------+
//| Faqat foydali pozitsiyalarni yopish                              |
//+------------------------------------------------------------------+
void CloseProfitablePositions()
{
   for (int i = PositionsTotal() - 1; i >= 0; i--) {
      if (posInfo.SelectByIndex(i) &&
          posInfo.Symbol() == SYMBOL &&
          posInfo.Magic() == 20240101 &&
          posInfo.Profit() > 0)
         trade.PositionClose(posInfo.Ticket());
   }
}

//+------------------------------------------------------------------+
//| JSON dan string qiymat olish                                     |
//+------------------------------------------------------------------+
string ExtractString(string json, string key)
{
   string searchKey = "\"" + key + "\":\"";
   int start = StringFind(json, searchKey);
   if (start < 0) return "";
   start += StringLen(searchKey);
   int end = StringFind(json, "\"", start);
   if (end < 0) return "";
   return StringSubstr(json, start, end - start);
}

//+------------------------------------------------------------------+
//| JSON dan double qiymat olish                                     |
//+------------------------------------------------------------------+
double ExtractDouble(string json, string key)
{
   string searchKey = "\"" + key + "\":";
   int start = StringFind(json, searchKey);
   if (start < 0) return 0;
   start += StringLen(searchKey);
   int end = start;
   while (end < StringLen(json)) {
      string ch = StringSubstr(json, end, 1);
      if (ch == "," || ch == "}" || ch == " ") break;
      end++;
   }
   return StringToDouble(StringSubstr(json, start, end - start));
}

//+------------------------------------------------------------------+
//| EA to'xtaganda                                                   |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("Gold AI Grid EA to'xtadi. Sabab: ", reason);
}
