//+------------------------------------------------------------------+
//|                                      NeuroX_Standalone_v9.mq5      |
//|                    NeuroX v9.0 - Standalone Pure Momentum Scalper   |
//|                                                                    |
//|  Single self-contained EA. No Python, no bridge, no external deps. |
//|  Tick-based momentum detection + progressive trailing stops.       |
//+------------------------------------------------------------------+
#property copyright   "NeuroX"
#property version     "9.0"
#property description "Standalone HFT scalper - pure tick momentum"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//+------------------------------------------------------------------+
//| Input Parameters                                                   |
//+------------------------------------------------------------------+
input int    InpMagicNumber       = 20250629;
input double InpLotSize           = 0.01;
input double InpMomentumThreshold = 0.30;
input int    InpMomentumLookback  = 20;
input double InpSL                = 2.00;
input int    InpCooldown          = 5;
input int    InpMaxHold           = 120;
input double InpBreakeven         = 0.30;
input double InpBEBuffer          = 0.05;
input double InpTrailStart        = 0.60;
input double InpTrailTight        = 1.20;
input double InpTrailVeryTight    = 2.00;
input double InpTrailDist1        = 0.40;
input double InpTrailDist2        = 0.25;
input double InpTrailDist3        = 0.15;
input double InpEmergencyLoss     = 50.0;
input int    InpMaxOpenTrades     = 1;
input bool   InpShowDashboard     = true;

//+------------------------------------------------------------------+
//| Global Variables                                                   |
//+------------------------------------------------------------------+
CTrade         g_trade;
CPositionInfo  g_position;

// Ring buffer for tick prices
#define RING_SIZE 30
double   g_ticks[RING_SIZE];
int      g_tickIdx       = 0;
int      g_tickCount     = 0;

// State
datetime g_lastTradeTime = 0;
int      g_tradesToday   = 0;
int      g_winsToday     = 0;
int      g_lossesToday   = 0;
double   g_realizedPnl   = 0.0;
int      g_lastDay       = 0;
string   g_momentum      = "FLAT";
string   g_trailTier     = "---";

//+------------------------------------------------------------------+
//| Expert initialization                                              |
//+------------------------------------------------------------------+
int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(10);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);

   ArrayInitialize(g_ticks, 0.0);
   g_tickIdx   = 0;
   g_tickCount = 0;

   MqlDateTime dt;
   TimeCurrent(dt);
   g_lastDay = dt.day;

   Print("[NeuroX Standalone] Initialized. Magic=", InpMagicNumber,
         " Lot=", InpLotSize, " Threshold=$", InpMomentumThreshold);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   ObjectsDeleteAll(0, "NXS_");
   Comment("");
   ChartRedraw(0);
   Print("[NeuroX Standalone] Removed. Reason=", reason);
}

//+------------------------------------------------------------------+
//| Main tick handler                                                  |
//+------------------------------------------------------------------+
void OnTick()
{
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

   // --- Day rollover ---
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.day != g_lastDay)
   {
      g_tradesToday  = 0;
      g_winsToday    = 0;
      g_lossesToday  = 0;
      g_realizedPnl  = 0.0;
      g_lastDay      = dt.day;
   }

   // --- Ring buffer update ---
   g_ticks[g_tickIdx] = bid;
   g_tickIdx = (g_tickIdx + 1) % RING_SIZE;
   if(g_tickCount < RING_SIZE)
      g_tickCount++;

   // --- Momentum detection ---
   g_momentum = "FLAT";
   if(g_tickCount >= InpMomentumLookback + 1)
   {
      int oldIdx = (g_tickIdx - InpMomentumLookback - 1 + RING_SIZE) % RING_SIZE;
      double diff = bid - g_ticks[oldIdx];
      if(diff > InpMomentumThreshold)
         g_momentum = "BUY";
      else if(diff < -InpMomentumThreshold)
         g_momentum = "SELL";
   }

   // --- Emergency close ---
   CheckEmergencyClose();

   // --- Position management ---
   ManagePositions();

   // --- Entry logic ---
   if(g_momentum != "FLAT")
      TryEntry();

   // --- Dashboard ---
   if(InpShowDashboard)
      UpdateDashboard();
}

//+------------------------------------------------------------------+
//| Try to open a new position                                         |
//+------------------------------------------------------------------+
void TryEntry()
{
   // Cooldown check
   if((TimeCurrent() - g_lastTradeTime) < InpCooldown)
      return;

   // Max positions check
   if(CountMyPositions() >= InpMaxOpenTrades)
      return;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   bool success = false;
   if(g_momentum == "BUY")
   {
      double sl = NormalizeDouble(ask - InpSL, digits);
      success = g_trade.Buy(InpLotSize, _Symbol, ask, sl, 0, "NeuroX|Standalone");
   }
   else if(g_momentum == "SELL")
   {
      double sl = NormalizeDouble(bid + InpSL, digits);
      success = g_trade.Sell(InpLotSize, _Symbol, bid, sl, 0, "NeuroX|Standalone");
   }

   if(success && g_trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      g_lastTradeTime = TimeCurrent();
      g_tradesToday++;
      Print("[NeuroX] ENTRY ", g_momentum, " @ ",
            DoubleToString(g_trade.ResultPrice(), digits));
   }
}

//+------------------------------------------------------------------+
//| Manage open positions - trailing stops and exits                   |
//+------------------------------------------------------------------+
void ManagePositions()
{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   datetime now = TimeCurrent();
   g_trailTier = "---";

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i))
         continue;
      if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol)
         continue;

      ulong  ticket     = g_position.Ticket();
      double entryPrice = g_position.PriceOpen();
      double currentSL  = g_position.StopLoss();
      double currentTP  = g_position.TakeProfit();
      double volume     = g_position.Volume();
      double profit     = g_position.Profit() + g_position.Swap() + g_position.Commission();
      bool   isBuy      = (g_position.PositionType() == POSITION_TYPE_BUY);
      double price      = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      datetime openTime = (datetime)PositionGetInteger(POSITION_TIME);
      int holdSec       = (int)(now - openTime);

      // --- Exit: momentum reversal (held > 10s) ---
      if(holdSec > 10)
      {
         if((isBuy && g_momentum == "SELL") || (!isBuy && g_momentum == "BUY"))
         {
            Print("[NeuroX] MOMENTUM REVERSAL EXIT ticket=", ticket,
                  " profit=$", DoubleToString(profit, 2));
            g_trade.PositionClose(ticket);
            RecordClose(profit);
            continue;
         }
      }

      // --- Exit: time-based (held > MaxHold without $1 profit) ---
      if(holdSec > InpMaxHold && profit < 1.0)
      {
         Print("[NeuroX] TIME EXIT ticket=", ticket,
               " held=", holdSec, "s profit=$", DoubleToString(profit, 2));
         g_trade.PositionClose(ticket);
         RecordClose(profit);
         continue;
      }

      // --- Progressive trailing stop ---
      double newSL = currentSL;
      string tier  = "Init";

      if(profit >= InpTrailVeryTight)
      {
         // Tier 4: very tight trail
         newSL = isBuy ? NormalizeDouble(price - InpTrailDist3, digits)
                       : NormalizeDouble(price + InpTrailDist3, digits);
         tier = "T4($" + DoubleToString(InpTrailDist3, 2) + ")";
      }
      else if(profit >= InpTrailTight)
      {
         // Tier 3: tight trail
         newSL = isBuy ? NormalizeDouble(price - InpTrailDist2, digits)
                       : NormalizeDouble(price + InpTrailDist2, digits);
         tier = "T3($" + DoubleToString(InpTrailDist2, 2) + ")";
      }
      else if(profit >= InpTrailStart)
      {
         // Tier 2: standard trail
         newSL = isBuy ? NormalizeDouble(price - InpTrailDist1, digits)
                       : NormalizeDouble(price + InpTrailDist1, digits);
         tier = "T2($" + DoubleToString(InpTrailDist1, 2) + ")";
      }
      else if(profit >= InpBreakeven)
      {
         // Tier 1: breakeven + buffer
         newSL = isBuy ? NormalizeDouble(entryPrice + InpBEBuffer, digits)
                       : NormalizeDouble(entryPrice - InpBEBuffer, digits);
         tier = "BE+";
      }

      g_trailTier = tier;

      // Never widen SL - only tighten
      bool shouldModify = false;
      if(isBuy)
      {
         if(newSL > currentSL)
            shouldModify = true;
      }
      else
      {
         if(currentSL == 0 || newSL < currentSL)
            shouldModify = true;
      }

      if(shouldModify)
      {
         if(g_trade.PositionModify(ticket, newSL, currentTP))
         {
            Print("[NeuroX] TRAIL ", tier, " ticket=", ticket,
                  " SL=", DoubleToString(newSL, digits),
                  " profit=$", DoubleToString(profit, 2));
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Emergency close all if floating loss exceeds limit                 |
//+------------------------------------------------------------------+
void CheckEmergencyClose()
{
   double totalLoss = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i))
         continue;
      if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol)
         continue;
      totalLoss += g_position.Profit() + g_position.Swap() + g_position.Commission();
   }

   if(totalLoss < -InpEmergencyLoss)
   {
      Print("[NeuroX] EMERGENCY CLOSE: Loss=$", DoubleToString(MathAbs(totalLoss), 2),
            " > limit $", DoubleToString(InpEmergencyLoss, 2));
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!g_position.SelectByIndex(i))
            continue;
         if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol)
            continue;
         double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();
         g_trade.PositionClose(g_position.Ticket());
         RecordClose(profit);
      }
   }
}

//+------------------------------------------------------------------+
//| Record a closed trade for daily stats                              |
//+------------------------------------------------------------------+
void RecordClose(double profit)
{
   g_realizedPnl += profit;
   if(profit > 0)
      g_winsToday++;
   else if(profit < 0)
      g_lossesToday++;
}

//+------------------------------------------------------------------+
//| Count positions with our magic number                              |
//+------------------------------------------------------------------+
int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i))
         continue;
      if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
         count++;
   }
   return count;
}

//+------------------------------------------------------------------+
//| Dashboard - minimal top-left panel                                 |
//+------------------------------------------------------------------+
void UpdateDashboard()
{
   int x = 10;
   int y = 30;
   int lineH = 18;

   // Title
   DashLabel("title", x, y, "NeuroX v9 Standalone", clrGold, 10);
   y += lineH + 4;

   // Momentum direction
   color dirClr = clrSilver;
   if(g_momentum == "BUY")       dirClr = clrLime;
   else if(g_momentum == "SELL") dirClr = clrRed;
   DashLabel("mom_l", x, y, "Momentum:", clrSilver, 9);
   DashLabel("mom_v", x + 100, y, g_momentum, dirClr, 9);
   y += lineH;

   // Floating P&L
   double floatPnl = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i))
         continue;
      if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
         floatPnl += g_position.Profit() + g_position.Swap() + g_position.Commission();
   }
   color pnlClr = (floatPnl >= 0) ? clrLime : clrRed;
   string pnlStr = (floatPnl >= 0) ? "+" : "";
   pnlStr += "$" + DoubleToString(floatPnl, 2);
   DashLabel("pnl_l", x, y, "P&L:", clrSilver, 9);
   DashLabel("pnl_v", x + 100, y, pnlStr, pnlClr, 9);
   y += lineH;

   // Trail tier
   DashLabel("trail_l", x, y, "Trail:", clrSilver, 9);
   DashLabel("trail_v", x + 100, y, g_trailTier, clrGold, 9);
   y += lineH;

   // Trades today
   DashLabel("trd_l", x, y, "Trades:", clrSilver, 9);
   DashLabel("trd_v", x + 100, y, IntegerToString(g_tradesToday), clrWhite, 9);
   y += lineH;

   // Win rate
   int closed = g_winsToday + g_lossesToday;
   double winRate = (closed > 0) ? (double)g_winsToday / (double)closed * 100.0 : 0.0;
   color wrClr = (winRate >= 60) ? clrLime : (winRate >= 45) ? clrWhite : clrRed;
   DashLabel("wr_l", x, y, "Win Rate:", clrSilver, 9);
   DashLabel("wr_v", x + 100, y, DoubleToString(winRate, 1) + "%", wrClr, 9);
   y += lineH;

   // Realized P&L
   color realClr = (g_realizedPnl >= 0) ? clrLime : clrRed;
   string realStr = (g_realizedPnl >= 0) ? "+" : "";
   realStr += "$" + DoubleToString(g_realizedPnl, 2);
   DashLabel("real_l", x, y, "Realized:", clrSilver, 9);
   DashLabel("real_v", x + 100, y, realStr, realClr, 9);

   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Helper: create or update a chart label                             |
//+------------------------------------------------------------------+
void DashLabel(string name, int x, int y, string text, color clr, int fontSize)
{
   string objName = "NXS_" + name;
   if(ObjectFind(0, objName) < 0)
   {
      ObjectCreate(0, objName, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, objName, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
   }
   ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, objName, OBJPROP_TEXT, text);
   ObjectSetInteger(0, objName, OBJPROP_COLOR, clr);
   ObjectSetInteger(0, objName, OBJPROP_FONTSIZE, fontSize);
   ObjectSetString(0, objName, OBJPROP_FONT, "Consolas");
}
//+------------------------------------------------------------------+
