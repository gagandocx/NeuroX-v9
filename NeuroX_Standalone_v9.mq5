//+------------------------------------------------------------------+
//|                                      NeuroX_Standalone_v9.mq5      |
//|                 NeuroX v9.40 - Standalone EMA Trend Scalper         |
//|                                                                    |
//|  Single self-contained EA. No Python, no bridge, no external deps. |
//|  EMA trend filter + candle-close exit + choppy market filter.       |
//|  Implements the exact same strategy as the Python-derived system.   |
//+------------------------------------------------------------------+
#property copyright   "NeuroX"
#property version     "9.40"
#property description "Standalone EMA9 candle-close scalper with 50 EMA trend filter"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//+------------------------------------------------------------------+
//| Input Parameters (matching config.py values exactly)               |
//+------------------------------------------------------------------+
input int    InpMagicNumber             = 20250629;      // Magic Number
input double InpLotSize                 = 0.10;          // Lot Size
input int    InpMaxPositions            = 1;             // Max Open Positions
input int    InpCooldownSeconds         = 1;             // Cooldown Between Trades (sec)
input double InpEmergencyLoss           = 50.0;          // Emergency Loss Limit ($)
input int    InpContractSize            = 100;           // Contract Size (XAUUSD=100)

// EMA Trend Filter
input int    InpEmaTrendPeriod          = 50;            // Main Trend EMA Period
input bool   InpEmaTrendEnabled         = true;          // Enable 50 EMA Trend Filter
input int    InpEmaEntryPeriod          = 9;             // Entry EMA Period
input double InpEmaMaxDistance          = 0.80;          // Max Distance from EMA 9 ($)

// EMA-Based Stop Loss
input int    InpEmaSlPeriod             = 60;            // EMA Period for SL Placement
input bool   InpEmaSlEnabled            = true;          // Use EMA for SL
input double InpEmaSlMinDistance        = 5.00;          // Min EMA SL Distance ($) - safety floor if 60 EMA too close

// Swing SL (fallback when EMA SL disabled)
input int    InpSwingSlLookback         = 10;            // Swing SL Lookback Bars
input double InpSwingSlMinDistance      = 5.00;          // Min Swing SL Distance ($) - safety floor if swing too close

// Breakeven & Trailing
input double InpBreakevenProfitThreshold = 6.00;         // BE Trigger: trade PnL ($) to activate breakeven
input double InpBreakevenLockAmount     = 5.00;          // BE Lock: profit ($) to lock when BE triggers
input double InpTrailDistance           = 1.00;          // Trail: raw price distance ($) behind market after BE

// Choppy Market Filter
input bool   InpChoppyFilterEnabled     = true;          // Enable Choppy Filter
input double InpMinADXThreshold         = 20.0;          // Min ADX for Trend
input double InpChoppinessThreshold     = 61.8;          // Choppiness Index Threshold
input double InpBBWidthSqueezeMult      = 0.5;           // BB Width Squeeze %
input double InpATRRatioThreshold       = 0.75;          // ATR Ratio Threshold
input double InpVarianceRatioThreshold  = 0.5;           // Variance Ratio Threshold
input int    InpRangingFilterAgreement  = 2;             // Votes to Block (of 5)

// Reversal Detection
input bool   InpReversalEnabled         = true;          // Enable Reversal Detection
input double InpReversalBodyMin         = 0.40;          // Min Reversal Body ($)
input double InpReversalBodyRatio       = 0.70;          // Min Body/Range Ratio
input double InpReversalATRMult         = 1.5;           // Reversal ATR Multiplier

// Dashboard
input bool   InpShowDashboard           = true;          // Show Dashboard
input int    InpDashboardScale          = 110;           // Dashboard Scale %

//+------------------------------------------------------------------+
//| Constants                                                          |
//+------------------------------------------------------------------+
#define CHOPPINESS_PERIOD    14
#define VARIANCE_LOOKBACK    19
#define ATR_PERIOD           14
#define BB_PERIOD            20
#define BB_DEVIATION         2.0
#define ADX_PERIOD           14
#define SWING_WIDTH          2
#define REVERSAL_BARS        10

//+------------------------------------------------------------------+
//| Global Variables                                                   |
//+------------------------------------------------------------------+
CTrade         g_trade;
CPositionInfo  g_position;

// Indicator handles
int g_ema9Handle;
int g_ema50Handle;
int g_ema60Handle;
int g_atrHandle;
int g_adxHandle;
int g_bbHandle;

// State tracking
datetime g_lastTradeTime     = 0;
datetime g_lastBarTime       = 0;
datetime g_lastModifyTime    = 0;  // Cooldown for SL modifications
bool     g_beApplied         = false;
double   g_entryPrice        = 0.0;
string   g_entryDirection    = "";
ulong    g_trackedTicket     = 0;

// Daily statistics
int      g_tradesToday       = 0;
int      g_winsToday         = 0;
int      g_lossesToday       = 0;
double   g_realizedPnl       = 0.0;
int      g_lastDay           = 0;

// Dashboard state
string   g_trendStatus       = "WARMUP";
string   g_alignStatus       = "WAITING";
string   g_ema9Direction     = "---";
int      g_choppyVotes       = 0;
string   g_decision          = "WAITING";
string   g_decisionReason    = "";
string   g_reversalStatus    = "CLEAR";
string   g_beStatus          = "INACTIVE";
string   g_slLevelStr        = "---";
double   g_currentEmaDistance = 0.0;

// Dashboard scaled layout
int DASH_X, DASH_Y, DASH_WIDTH, DASH_LINE_H, DASH_MARGIN_L, DASH_VALUE_COL, DASH_FONT_SIZE;

//+------------------------------------------------------------------+
//| Expert initialization                                              |
//+------------------------------------------------------------------+
int OnInit()
{
   g_trade.SetExpertMagicNumber(InpMagicNumber);
   g_trade.SetDeviationInPoints(10);
   g_trade.SetTypeFilling(ORDER_FILLING_IOC);

   // Create indicator handles
   g_ema9Handle  = iMA(_Symbol, PERIOD_M1, InpEmaEntryPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_ema50Handle = iMA(_Symbol, PERIOD_M1, InpEmaTrendPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_ema60Handle = iMA(_Symbol, PERIOD_M1, InpEmaSlPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_atrHandle   = iATR(_Symbol, PERIOD_M1, ATR_PERIOD);
   g_adxHandle   = iADX(_Symbol, PERIOD_M5, ADX_PERIOD);
   g_bbHandle    = iBands(_Symbol, PERIOD_M1, BB_PERIOD, 0, BB_DEVIATION, PRICE_CLOSE);

   if(g_ema9Handle == INVALID_HANDLE || g_ema50Handle == INVALID_HANDLE ||
      g_ema60Handle == INVALID_HANDLE || g_atrHandle == INVALID_HANDLE ||
      g_adxHandle == INVALID_HANDLE || g_bbHandle == INVALID_HANDLE)
   {
      Print("[NeuroX Standalone] FATAL: Failed to create indicator handles!");
      return INIT_FAILED;
   }

   // Initialize state
   g_lastBarTime = iTime(_Symbol, PERIOD_M1, 0);
   g_beApplied = false;
   g_entryPrice = 0.0;
   g_entryDirection = "";
   g_trackedTicket = 0;

   MqlDateTime dt;
   TimeCurrent(dt);
   g_lastDay = dt.day;

   Print("[NeuroX Standalone v9.40] Initialized. Magic=", InpMagicNumber,
         " Lot=", DoubleToString(InpLotSize, 2),
         " TrendEMA=", InpEmaTrendPeriod,
         " EntryEMA=", InpEmaEntryPeriod,
         " SL_EMA=", InpEmaSlPeriod,
         " MaxDist=$", DoubleToString(InpEmaMaxDistance, 2));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                            |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   // Release indicator handles
   if(g_ema9Handle != INVALID_HANDLE)  IndicatorRelease(g_ema9Handle);
   if(g_ema50Handle != INVALID_HANDLE) IndicatorRelease(g_ema50Handle);
   if(g_ema60Handle != INVALID_HANDLE) IndicatorRelease(g_ema60Handle);
   if(g_atrHandle != INVALID_HANDLE)   IndicatorRelease(g_atrHandle);
   if(g_adxHandle != INVALID_HANDLE)   IndicatorRelease(g_adxHandle);
   if(g_bbHandle != INVALID_HANDLE)    IndicatorRelease(g_bbHandle);

   // Remove dashboard objects
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
   if(bid <= 0.0) return;

   // --- Day rollover ---
   CheckDayRollover();

   // --- Read all indicator values ---
   double ema9Val = 0.0, ema50Val = 0.0, ema60Val = 0.0;
   double atrVal = 0.0, adxVal = 100.0;
   double bbUpper = 0.0, bbLower = 0.0;

   double buf[1];
   if(CopyBuffer(g_ema9Handle, 0, 0, 1, buf) > 0)  ema9Val = buf[0];
   if(CopyBuffer(g_ema50Handle, 0, 0, 1, buf) > 0) ema50Val = buf[0];
   if(CopyBuffer(g_ema60Handle, 0, 0, 1, buf) > 0) ema60Val = buf[0];
   if(CopyBuffer(g_atrHandle, 0, 0, 1, buf) > 0)   atrVal = buf[0];
   if(CopyBuffer(g_adxHandle, 0, 0, 1, buf) > 0)   adxVal = buf[0]; // Main ADX line (buffer 0)
   if(CopyBuffer(g_bbHandle, 1, 0, 1, buf) > 0)    bbUpper = buf[0]; // Upper band
   if(CopyBuffer(g_bbHandle, 2, 0, 1, buf) > 0)    bbLower = buf[0]; // Lower band

   // --- Determine allowed direction (50 EMA + 9 EMA trend filter) ---
   string allowedDirection = "";
   g_trendStatus = "WARMUP";
   g_alignStatus = "WAITING";
   g_ema9Direction = "---";

   if(ema9Val > 0.0 && bid > 0.0)
   {
      // EMA 9 direction
      if(bid > ema9Val)
         g_ema9Direction = "P>EMA9 BUY $" + DoubleToString(MathAbs(bid - ema9Val), 2);
      else if(bid < ema9Val)
         g_ema9Direction = "P<EMA9 SELL $" + DoubleToString(MathAbs(bid - ema9Val), 2);
      else
         g_ema9Direction = "FLAT";

      if(InpEmaTrendEnabled && ema50Val > 0.0)
      {
         bool priceAboveEma50 = (bid > ema50Val);
         bool priceAboveEma9  = (bid > ema9Val);
         bool priceBelowEma50 = (bid < ema50Val);
         bool priceBelowEma9  = (bid < ema9Val);

         if(priceAboveEma50 && priceAboveEma9)
         {
            allowedDirection = "BUY";
            g_trendStatus = "BULLISH";
            g_alignStatus = "ALIGNED";
         }
         else if(priceBelowEma50 && priceBelowEma9)
         {
            allowedDirection = "SELL";
            g_trendStatus = "BEARISH";
            g_alignStatus = "ALIGNED";
         }
         else
         {
            allowedDirection = "";
            g_trendStatus = "CONFLICTING";
            g_alignStatus = "CONFLICTING";
         }
      }
      else
      {
         // Trend filter disabled or EMA50 not ready
         if(InpEmaTrendEnabled && ema50Val <= 0.0)
         {
            g_trendStatus = "WARMUP";
            g_alignStatus = "WAITING";
         }
         else
         {
            g_trendStatus = "DISABLED";
            g_alignStatus = "FILTER OFF";
         }
         // Use EMA9 only for direction
         if(bid > ema9Val)
            allowedDirection = "BUY";
         else if(bid < ema9Val)
            allowedDirection = "SELL";
      }
   }

   // --- Compute EMA distance ---
   g_currentEmaDistance = (ema9Val > 0.0) ? MathAbs(bid - ema9Val) : 0.0;

   // --- Compute choppy filter indicators ---
   double computedATR = atrVal;
   double avgATR = ComputeAvgATR();
   double varianceRatio = ComputeVarianceRatio();
   double choppinessIndex = ComputeChoppinessIndex();

   // Count choppy votes
   g_choppyVotes = CountChoppyVotes(adxVal, choppinessIndex, bbUpper, bbLower, bid,
                                     computedATR, avgATR, varianceRatio);
   bool isChoppy = (InpChoppyFilterEnabled && g_choppyVotes >= InpRangingFilterAgreement);

   // --- Detect SL hit (tracked position disappeared) ---
   DetectSLHit();

   // --- Manage existing positions ---
   ManageExistingPositions(bid, ema9Val, ema50Val, ema60Val);

   // --- Check candle close for exit ---
   CheckCandleCloseExit(bid);

   // --- Check reversal detection ---
   if(InpReversalEnabled && g_trackedTicket > 0)
      CheckReversalExit(bid);

   // --- Entry logic ---
   g_decision = "WAITING";
   g_decisionReason = "";

   if(allowedDirection != "" && bid > 0.0)
   {
      if(isChoppy)
      {
         g_decision = "FILTERED";
         g_decisionReason = "CHOPPY_MARKET";
      }
      else if(g_currentEmaDistance > InpEmaMaxDistance)
      {
         g_decision = "FILTERED";
         g_decisionReason = "EMA_DISTANCE";
      }
      else if(CountMyPositions() >= InpMaxPositions)
      {
         g_decision = "MAX_POS";
         g_decisionReason = "";
      }
      else if(g_trackedTicket > 0)
      {
         g_decision = "HOLDING";
         g_decisionReason = "CANDLE_WAIT";
      }
      else if((TimeCurrent() - g_lastTradeTime) >= InpCooldownSeconds)
      {
         // All clear - try entry
         TryEntry(allowedDirection, bid, ema60Val);
      }
      else
      {
         g_decision = "COOLDOWN";
         g_decisionReason = "COOLDOWN";
      }
   }
   else if(bid > 0.0 && ema9Val <= 0.0)
   {
      g_decision = "WAITING";
      g_decisionReason = "NEED_EMA";
   }
   else if(g_trendStatus == "CONFLICTING")
   {
      g_decision = "FILTERED";
      g_decisionReason = "EMA_CONFLICTING";
   }

   // --- Emergency close ---
   CheckEmergencyClose();

   // --- Update dashboard ---
   if(InpShowDashboard)
      UpdateDashboard(bid, ema9Val, ema50Val, ema60Val);
}


//+------------------------------------------------------------------+
//| Try to open a new position                                         |
//+------------------------------------------------------------------+
void TryEntry(string direction, double price, double ema60Val)
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

   // Compute SL level
   // Fix #1: SL distance computed from execution price (ask for BUY, bid for SELL)
   double slPrice = 0.0;
   if(InpEmaSlEnabled && ema60Val > 0.0)
   {
      // EMA-based SL at 60 EMA level
      double slDistance = 0.0;
      if(direction == "BUY")
      {
         slDistance = MathAbs(ask - ema60Val);
         if(slDistance < InpEmaSlMinDistance)
            slDistance = InpEmaSlMinDistance;
         slPrice = NormalizeDouble(ask - slDistance, digits);
      }
      else
      {
         slDistance = MathAbs(bid - ema60Val);
         if(slDistance < InpEmaSlMinDistance)
            slDistance = InpEmaSlMinDistance;
         slPrice = NormalizeDouble(bid + slDistance, digits);
      }
   }
   else
   {
      // Swing-based SL
      slPrice = ComputeSwingSL(direction, price);
      slPrice = NormalizeDouble(slPrice, digits);
   }

   g_slLevelStr = "$" + DoubleToString(slPrice, 2);

   // Execute trade (no TP - candle close exit)
   bool success = false;
   if(direction == "BUY")
   {
      success = g_trade.Buy(InpLotSize, _Symbol, ask, slPrice, 0, "NeuroX|Standalone");
   }
   else if(direction == "SELL")
   {
      success = g_trade.Sell(InpLotSize, _Symbol, bid, slPrice, 0, "NeuroX|Standalone");
   }

   if(success && g_trade.ResultRetcode() == TRADE_RETCODE_DONE)
   {
      g_lastTradeTime = TimeCurrent();
      g_tradesToday++;
      // Fix #4: Store preliminary ticket, will be validated on next cycle
      g_trackedTicket = g_trade.ResultDeal();
      if(g_trackedTicket == 0)
         g_trackedTicket = g_trade.ResultOrder();
      g_entryPrice = g_trade.ResultPrice();
      g_entryDirection = direction;
      g_beApplied = false;
      g_decision = "TRADING";
      g_decisionReason = "";
      g_beStatus = "ARMED $" + DoubleToString((int)InpBreakevenProfitThreshold, 0) + "+";

      Print("[NeuroX Standalone] ENTRY ", direction, " @ ",
            DoubleToString(g_entryPrice, digits),
            " SL=", DoubleToString(slPrice, digits),
            " Lot=", DoubleToString(InpLotSize, 2));
   }
}

//+------------------------------------------------------------------+
//| Compute Swing-based SL (fractal swing high/low detection)          |
//+------------------------------------------------------------------+
double ComputeSwingSL(string direction, double entryPrice)
{
   int barsNeeded = InpSwingSlLookback + SWING_WIDTH + 1;
   double highs[], lows[];
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows, true);

   if(CopyHigh(_Symbol, PERIOD_M1, 0, barsNeeded, highs) < barsNeeded ||
      CopyLow(_Symbol, PERIOD_M1, 0, barsNeeded, lows) < barsNeeded)
   {
      // Not enough data - use minimum distance
      if(direction == "BUY")
         return entryPrice - InpSwingSlMinDistance;
      else
         return entryPrice + InpSwingSlMinDistance;
   }

   if(direction == "BUY")
   {
      // Find last swing low
      double swingLow = FindLastSwingLow(lows, InpSwingSlLookback);
      if(swingLow > 0.0 && swingLow < entryPrice)
      {
         double distance = entryPrice - swingLow;
         if(distance >= InpSwingSlMinDistance)
            return swingLow;
      }
      return entryPrice - InpSwingSlMinDistance;
   }
   else
   {
      // Find last swing high
      double swingHigh = FindLastSwingHigh(highs, InpSwingSlLookback);
      if(swingHigh > 0.0 && swingHigh > entryPrice)
      {
         double distance = swingHigh - entryPrice;
         if(distance >= InpSwingSlMinDistance)
            return swingHigh;
      }
      return entryPrice + InpSwingSlMinDistance;
   }
}

//+------------------------------------------------------------------+
//| Find last swing high using fractal detection                       |
//+------------------------------------------------------------------+
double FindLastSwingHigh(const double &highs[], int lookback)
{
   int total = ArraySize(highs);
   if(total < (SWING_WIDTH * 2 + 1)) return 0.0;

   // Scan from most recent back (series array: index 0 = current bar)
   for(int i = SWING_WIDTH; i < lookback && i < total - SWING_WIDTH; i++)
   {
      double high = highs[i];
      bool isSwing = true;

      // Check bars on each side
      for(int j = 1; j <= SWING_WIDTH; j++)
      {
         if(highs[i - j] >= high || highs[i + j] >= high)
         {
            isSwing = false;
            break;
         }
      }

      if(isSwing)
         return high;
   }
   return 0.0;
}

//+------------------------------------------------------------------+
//| Find last swing low using fractal detection                        |
//+------------------------------------------------------------------+
double FindLastSwingLow(const double &lows[], int lookback)
{
   int total = ArraySize(lows);
   if(total < (SWING_WIDTH * 2 + 1)) return 0.0;

   // Scan from most recent back (series array: index 0 = current bar)
   for(int i = SWING_WIDTH; i < lookback && i < total - SWING_WIDTH; i++)
   {
      double low = lows[i];
      bool isSwing = true;

      // Check bars on each side
      for(int j = 1; j <= SWING_WIDTH; j++)
      {
         if(lows[i - j] <= low || lows[i + j] <= low)
         {
            isSwing = false;
            break;
         }
      }

      if(isSwing)
         return low;
   }
   return 0.0;
}


//+------------------------------------------------------------------+
//| Manage existing positions (breakeven + tight trailing)             |
//+------------------------------------------------------------------+
void ManageExistingPositions(double currentPrice, double ema9Val,
                             double ema50Val, double ema60Val)
{
   if(g_trackedTicket == 0) return;

   // Find our tracked position
   bool found = false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i)) continue;
      if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;

      ulong ticket = g_position.Ticket();
      if(ticket != g_trackedTicket) continue;

      found = true;
      int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      double entryPrice = g_position.PriceOpen();
      double currentSL = g_position.StopLoss();
      double currentTP = g_position.TakeProfit();
      bool isBuy = (g_position.PositionType() == POSITION_TYPE_BUY);
      double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                           : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      // --- $5 Actual PnL Breakeven ---
      // Minimum stop distance from broker
      double minStopDist = (SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) + 1)
                           * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
      double currentBid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double currentAsk = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

      if(!g_beApplied)
      {
         double priceDiff = isBuy ? (price - entryPrice) : (entryPrice - price);
         double actualPnl = priceDiff * InpLotSize * InpContractSize;

         if(actualPnl >= InpBreakevenProfitThreshold)
         {
            // Convert dollar lock amount to price distance
            double lockDist = InpBreakevenLockAmount / (InpLotSize * InpContractSize);
            double newSL = 0.0;
            if(isBuy)
               newSL = NormalizeDouble(entryPrice + lockDist, digits);
            else
               newSL = NormalizeDouble(entryPrice - lockDist, digits);

            // Validate against minimum stop distance
            bool validStop = true;
            if(isBuy && newSL >= currentBid - minStopDist)
               validStop = false;
            if(!isBuy && newSL <= currentAsk + minStopDist)
               validStop = false;

            // Never widen SL - only tighten
            bool shouldModify = false;
            if(validStop)
            {
               if(isBuy)
               {
                  if(newSL > currentSL || currentSL == 0.0)
                     shouldModify = true;
               }
               else
               {
                  if(currentSL == 0.0 || newSL < currentSL)
                     shouldModify = true;
               }
            }

            // Cooldown: max one modify per second
            if(shouldModify && (TimeCurrent() - g_lastModifyTime) >= 1)
            {
               if(g_trade.PositionModify(ticket, newSL, currentTP))
               {
                  g_beApplied = true;
                  g_lastModifyTime = TimeCurrent();
                  g_beStatus = "LOCKED $" + DoubleToString(InpBreakevenLockAmount, 2);
                  Print("[NeuroX Standalone] BREAKEVEN: Ticket ", ticket,
                        " SL=", DoubleToString(newSL, digits),
                        " LockDist=", DoubleToString(lockDist, digits),
                        " PnL=$", DoubleToString(actualPnl, 2));
               }
            }
         }
      }
      else
      {
         // --- Tight trailing after breakeven ---
         // Trail SL behind current price by InpTrailDistance
         // Only move SL in favorable direction (never widen)
         double trailSL = 0.0;
         if(isBuy)
            trailSL = NormalizeDouble(price - InpTrailDistance, digits);
         else
            trailSL = NormalizeDouble(price + InpTrailDistance, digits);

         // Validate against minimum stop distance
         bool validTrail = true;
         if(isBuy && trailSL >= currentBid - minStopDist)
            validTrail = false;
         if(!isBuy && trailSL <= currentAsk + minStopDist)
            validTrail = false;

         bool shouldTrail = false;
         if(validTrail)
         {
            if(isBuy)
            {
               // For BUY: new trail SL must be higher than current SL
               if(trailSL > currentSL && currentSL > 0.0)
                  shouldTrail = true;
            }
            else
            {
               // For SELL: new trail SL must be lower than current SL
               if(trailSL < currentSL)
                  shouldTrail = true;
            }
         }

         // Cooldown: max one modify per second
         if(shouldTrail && (TimeCurrent() - g_lastModifyTime) >= 1)
         {
            if(g_trade.PositionModify(ticket, trailSL, currentTP))
            {
               g_lastModifyTime = TimeCurrent();
               g_beStatus = "TRAIL $" + DoubleToString(InpTrailDistance, 2);
               g_slLevelStr = "$" + DoubleToString(trailSL, 2);
               Print("[NeuroX Standalone] TRAIL: Ticket ", ticket,
                     " SL=", DoubleToString(trailSL, digits),
                     " Price=", DoubleToString(price, digits),
                     " Dist=$", DoubleToString(InpTrailDistance, 2));
            }
         }
      }
      break;
   }

   // If position not found but we were tracking one, it was closed externally
   if(!found && g_trackedTicket > 0)
   {
      // Will be caught by DetectSLHit()
   }
}

//+------------------------------------------------------------------+
//| Check candle close for exit (only if in profit)                    |
//+------------------------------------------------------------------+
void CheckCandleCloseExit(double currentPrice)
{
   if(g_trackedTicket == 0) return;

   datetime currentBarTime = iTime(_Symbol, PERIOD_M1, 0);
   if(currentBarTime == 0) return;

   // Detect new bar formation
   if(g_lastBarTime == 0)
   {
      g_lastBarTime = currentBarTime;
      return;
   }

   if(currentBarTime != g_lastBarTime)
   {
      // New bar formed - previous candle closed
      g_lastBarTime = currentBarTime;

      // Check if position exists and is in profit
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!g_position.SelectByIndex(i)) continue;
         if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;
         if(g_position.Ticket() != g_trackedTicket) continue;

         // Fix #2: Use broker-reported total PnL (includes swap + commission)
         double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();

         if(profit > 0.0)
         {
            // In profit - close the position
            if(g_trade.PositionClose(g_trackedTicket))
            {
               Print("[NeuroX Standalone] CANDLE CLOSE EXIT: Ticket ", g_trackedTicket,
                     " PnL=$", DoubleToString(profit, 2));
               RecordClose(profit);
               ResetTracking();
            }
         }
         // If in loss - keep position open, SL protects downside
         break;
      }
   }
}


//+------------------------------------------------------------------+
//| Advanced M1 Reversal Detection                                     |
//+------------------------------------------------------------------+
void CheckReversalExit(double currentPrice)
{
   if(g_trackedTicket == 0) return;

   // Get current forming bar (index 0) plus completed bars for range comparison
   double open[], high[], low[], close[];
   ArraySetAsSeries(open, true);
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   ArraySetAsSeries(close, true);

   // Fix #5: Only require 4 bars minimum (current bar + 3 completed) to match Python's 3-bar minimum
   int barsCopied = CopyOpen(_Symbol, PERIOD_M1, 0, REVERSAL_BARS + 1, open);
   if(barsCopied < 4) return;
   int barsHigh = CopyHigh(_Symbol, PERIOD_M1, 0, REVERSAL_BARS + 1, high);
   if(barsHigh < 4) return;
   int barsLow = CopyLow(_Symbol, PERIOD_M1, 0, REVERSAL_BARS + 1, low);
   if(barsLow < 4) return;
   int barsClose = CopyClose(_Symbol, PERIOD_M1, 0, REVERSAL_BARS + 1, close);
   if(barsClose < 4) return;

   // Use the minimum number of bars actually available
   int availableBars = MathMin(MathMin(barsCopied, barsHigh), MathMin(barsLow, barsClose));

   // Analyze current forming bar (index 0)
   double barOpen = open[0];
   double barHigh = high[0];
   double barLow = low[0];
   double barClose = close[0];

   if(barHigh <= 0.0 || barLow <= 0.0 || barHigh == barLow) return;

   double body = MathAbs(barClose - barOpen);
   double candleRange = barHigh - barLow;

   // Check minimum body size
   if(body < InpReversalBodyMin)
   {
      g_reversalStatus = "CLEAR";
      return;
   }

   // Check body ratio
   double bodyRatio = body / candleRange;
   if(bodyRatio < InpReversalBodyRatio)
   {
      g_reversalStatus = "CLEAR";
      return;
   }

   // Check candle direction is against our trade
   string candleDir = (barClose > barOpen) ? "BUY" : "SELL";
   if(g_entryDirection == "BUY" && candleDir != "SELL")
   {
      g_reversalStatus = "CLEAR";
      return;
   }
   if(g_entryDirection == "SELL" && candleDir != "BUY")
   {
      g_reversalStatus = "CLEAR";
      return;
   }

   // Check candle range vs recent average range (use available completed bars, up to REVERSAL_BARS)
   double sumRange = 0.0;
   int rangeCount = 0;
   int maxRange = MathMin(REVERSAL_BARS, availableBars - 1); // exclude current bar (index 0)
   for(int i = 1; i <= maxRange; i++)
   {
      double r = high[i] - low[i];
      if(r > 0.0)
      {
         sumRange += r;
         rangeCount++;
      }
   }

   if(rangeCount == 0)
   {
      g_reversalStatus = "CLEAR";
      return;
   }

   double avgRange = sumRange / rangeCount;
   if(candleRange < InpReversalATRMult * avgRange)
   {
      g_reversalStatus = "CLEAR";
      return;
   }

   // ALL conditions met - reversal detected, close position immediately
   g_reversalStatus = "DETECTED";

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i)) continue;
      if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;
      if(g_position.Ticket() != g_trackedTicket) continue;

      double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();
      if(g_trade.PositionClose(g_trackedTicket))
      {
         Print("[NeuroX Standalone] REVERSAL EXIT: Ticket ", g_trackedTicket,
               " PnL=$", DoubleToString(profit, 2),
               " Body=$", DoubleToString(body, 2),
               " Range=$", DoubleToString(candleRange, 2));
         RecordClose(profit);
         ResetTracking();
      }
      break;
   }
}

//+------------------------------------------------------------------+
//| Detect SL hit (tracked position disappeared from broker)           |
//+------------------------------------------------------------------+
void DetectSLHit()
{
   if(g_trackedTicket == 0) return;

   // Check if position still exists
   bool positionExists = false;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i)) continue;
      if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;
      if(g_position.Ticket() == g_trackedTicket)
      {
         positionExists = true;
         break;
      }
   }

   // Fix #4: If tracked ticket not found, scan by magic/symbol and adopt newest position
   if(!positionExists)
   {
      ulong newestTicket = 0;
      datetime newestTime = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!g_position.SelectByIndex(i)) continue;
         if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;
         datetime posTime = (datetime)g_position.Time();
         if(posTime > newestTime)
         {
            newestTime = posTime;
            newestTicket = g_position.Ticket();
         }
      }

      if(newestTicket > 0)
      {
         // Adopt the found position (ticket mismatch resolved)
         Print("[NeuroX Standalone] TICKET MISMATCH: Expected ", g_trackedTicket,
               " not found. Adopting ticket ", newestTicket);
         g_trackedTicket = newestTicket;
         // Update entry info from adopted position
         if(g_position.SelectByTicket(newestTicket))
         {
            g_entryPrice = g_position.PriceOpen();
            g_entryDirection = (g_position.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
         }
         return;
      }

      // Position truly gone - look up deal history for profit
      double closedProfit = 0.0;
      if(HistorySelect(TimeCurrent() - 300, TimeCurrent()))
      {
         for(int d = HistoryDealsTotal() - 1; d >= 0; d--)
         {
            ulong dealTicket = HistoryDealGetTicket(d);
            if(dealTicket == 0) continue;
            long dealPosId = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
            if((ulong)dealPosId == g_trackedTicket &&
               HistoryDealGetInteger(dealTicket, DEAL_ENTRY) == DEAL_ENTRY_OUT)
            {
               closedProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                            + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                            + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
               break;
            }
         }
      }

      Print("[NeuroX Standalone] SL HIT: Ticket ", g_trackedTicket,
            " PnL=$", DoubleToString(closedProfit, 2));
      RecordClose(closedProfit);
      ResetTracking();
   }
}


//+------------------------------------------------------------------+
//| Compute Choppiness Index manually                                  |
//| CI = 100 * ln(sum_ATR_N / (HH - LL)) / ln(N)                     |
//+------------------------------------------------------------------+
double ComputeChoppinessIndex()
{
   int period = CHOPPINESS_PERIOD;
   double atrBuf[];
   ArraySetAsSeries(atrBuf, true);

   // Get ATR values for the period
   if(CopyBuffer(g_atrHandle, 0, 0, period, atrBuf) < period)
      return 0.0;

   // Sum of ATR over N bars
   double sumATR = 0.0;
   for(int i = 0; i < period; i++)
      sumATR += atrBuf[i];

   // Get highest high and lowest low over N bars
   double highs[], lows[];
   ArraySetAsSeries(highs, true);
   ArraySetAsSeries(lows, true);

   if(CopyHigh(_Symbol, PERIOD_M1, 0, period, highs) < period) return 0.0;
   if(CopyLow(_Symbol, PERIOD_M1, 0, period, lows) < period) return 0.0;

   double highestHigh = highs[0];
   double lowestLow = lows[0];
   for(int i = 1; i < period; i++)
   {
      if(highs[i] > highestHigh) highestHigh = highs[i];
      if(lows[i] < lowestLow) lowestLow = lows[i];
   }

   double range = highestHigh - lowestLow;
   if(range <= 0.0) return 0.0;

   // CI = 100 * ln(sumATR / range) / ln(N)
   double ci = 100.0 * MathLog(sumATR / range) / MathLog((double)period);
   return ci;
}

//+------------------------------------------------------------------+
//| Compute Average ATR (average of ATR values over the period)        |
//+------------------------------------------------------------------+
double ComputeAvgATR()
{
   int period = ATR_PERIOD;
   double atrBuf[];
   ArraySetAsSeries(atrBuf, true);

   // Fix #3: Match Python's 14-bar ATR average (was 42, now 14)
   int barsNeeded = period;
   if(CopyBuffer(g_atrHandle, 0, 0, barsNeeded, atrBuf) < barsNeeded)
      return 0.0;

   double sum = 0.0;
   for(int i = 0; i < barsNeeded; i++)
      sum += atrBuf[i];

   return sum / barsNeeded;
}

//+------------------------------------------------------------------+
//| Compute Variance Ratio from close price increments                 |
//| Matches Python: actual_walk_var / expected_walk_var                 |
//+------------------------------------------------------------------+
double ComputeVarianceRatio()
{
   int lookback = VARIANCE_LOOKBACK;
   double closes[];
   ArraySetAsSeries(closes, true);

   // Need lookback + 1 closes to get 'lookback' increments
   if(CopyClose(_Symbol, PERIOD_M1, 0, lookback + 1, closes) < lookback + 1)
      return 1.0;  // Default: not ranging

   // Compute increments (close[i] - close[i+1] since array is series)
   double increments[];
   ArrayResize(increments, lookback);
   for(int i = 0; i < lookback; i++)
      increments[i] = closes[i] - closes[i + 1];

   // Compute variance of increments
   double sumInc = 0.0;
   for(int i = 0; i < lookback; i++)
      sumInc += increments[i];
   double meanInc = sumInc / lookback;

   double varInc = 0.0;
   for(int i = 0; i < lookback; i++)
   {
      double diff = increments[i] - meanInc;
      varInc += diff * diff;
   }
   varInc /= lookback;

   if(varInc <= 0.0) return 1.0;

   // Full move: newest close - oldest close
   // closes[0] is most recent, closes[lookback] is oldest
   double fullMove = closes[0] - closes[lookback];

   // Expected walk variance for random walk: n * var_increments
   double expectedWalkVar = lookback * varInc;
   // Actual walk variance: full_move^2
   double actualWalkVar = fullMove * fullMove;

   if(expectedWalkVar <= 0.0) return 1.0;

   return actualWalkVar / expectedWalkVar;
}

//+------------------------------------------------------------------+
//| Count choppy market filter votes (5 indicators)                    |
//+------------------------------------------------------------------+
int CountChoppyVotes(double adxVal, double choppinessIdx,
                     double bbUpper, double bbLower, double price,
                     double currentATR, double avgATR, double varRatio)
{
   if(!InpChoppyFilterEnabled) return 0;

   int votes = 0;

   // 1. ADX < threshold = no trend
   if(adxVal < InpMinADXThreshold)
      votes++;

   // 2. Choppiness Index > threshold = choppy
   if(choppinessIdx > 0.0 && choppinessIdx > InpChoppinessThreshold)
      votes++;

   // 3. Bollinger Band Width squeeze
   if(bbUpper > 0.0 && bbLower > 0.0 && price > 0.0)
   {
      double bbWidth = bbUpper - bbLower;
      double bbWidthPct = (bbWidth / price) * 100.0;
      if(bbWidthPct < InpBBWidthSqueezeMult)
         votes++;
   }

   // 4. ATR Ratio: current/average < threshold
   if(currentATR > 0.0 && avgATR > 0.0)
   {
      double atrRatio = currentATR / avgATR;
      if(atrRatio < InpATRRatioThreshold)
         votes++;
   }

   // 5. Variance Ratio < threshold = mean-reverting
   if(varRatio > 0.0 && varRatio < InpVarianceRatioThreshold)
      votes++;

   return votes;
}


//+------------------------------------------------------------------+
//| Emergency close all if floating loss exceeds limit                 |
//+------------------------------------------------------------------+
void CheckEmergencyClose()
{
   double totalLoss = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i)) continue;
      if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;
      totalLoss += g_position.Profit() + g_position.Swap() + g_position.Commission();
   }

   if(totalLoss < -InpEmergencyLoss)
   {
      Print("[NeuroX Standalone] EMERGENCY: Loss=$",
            DoubleToString(MathAbs(totalLoss), 2),
            " > limit $", DoubleToString(InpEmergencyLoss, 2));

      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         if(!g_position.SelectByIndex(i)) continue;
         if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol) continue;

         double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();
         g_trade.PositionClose(g_position.Ticket());
         RecordClose(profit);
      }
      ResetTracking();
   }
}

//+------------------------------------------------------------------+
//| Day rollover check and reset                                       |
//+------------------------------------------------------------------+
void CheckDayRollover()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   if(dt.day != g_lastDay)
   {
      Print("[NeuroX Standalone] Day rollover. Yesterday: ",
            g_tradesToday, " trades, P&L=$",
            DoubleToString(g_realizedPnl, 2));
      g_tradesToday  = 0;
      g_winsToday    = 0;
      g_lossesToday  = 0;
      g_realizedPnl  = 0.0;
      g_lastDay      = dt.day;
   }
}

//+------------------------------------------------------------------+
//| Record a closed trade for daily stats                              |
//+------------------------------------------------------------------+
void RecordClose(double profit)
{
   g_realizedPnl += profit;
   if(profit > 0.0)
      g_winsToday++;
   else if(profit < 0.0)
      g_lossesToday++;
}

//+------------------------------------------------------------------+
//| Reset position tracking state                                      |
//+------------------------------------------------------------------+
void ResetTracking()
{
   g_trackedTicket = 0;
   g_entryPrice = 0.0;
   g_entryDirection = "";
   g_beApplied = false;
   g_beStatus = "INACTIVE";
   g_reversalStatus = "CLEAR";
   g_slLevelStr = "---";
}

//+------------------------------------------------------------------+
//| Count positions with our magic number                              |
//+------------------------------------------------------------------+
int CountMyPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i)) continue;
      if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
         count++;
   }
   return count;
}


//+------------------------------------------------------------------+
//| Dashboard Layout Constants                                         |
//+------------------------------------------------------------------+
#define DASH_BASE_X          10
#define DASH_BASE_Y          30
#define DASH_BASE_WIDTH      310
#define DASH_BASE_LINE_H     18
#define DASH_BASE_MARGIN_L   20
#define DASH_BASE_VALUE_COL  160
#define DASH_BASE_FONT_SIZE  9
#define DASH_FONT            "Consolas"

// Color scheme
#define CLR_TITLE       clrGold
#define CLR_HEADER      clrDeepSkyBlue
#define CLR_LABEL       clrSilver
#define CLR_VALUE       clrWhite
#define CLR_POSITIVE    clrLime
#define CLR_NEGATIVE    clrRed
#define CLR_NEUTRAL     clrSilver
#define CLR_ACCENT      clrGold
#define CLR_BG_PANEL    C'20,20,30'

//+------------------------------------------------------------------+
//| Compute scaled dashboard layout from InpDashboardScale             |
//+------------------------------------------------------------------+
void DashComputeScale()
{
   double scale = MathMax(50.0, MathMin(200.0, (double)InpDashboardScale)) / 100.0;
   DASH_X         = (int)(DASH_BASE_X * scale);
   DASH_Y         = (int)(DASH_BASE_Y * scale);
   DASH_WIDTH     = (int)(DASH_BASE_WIDTH * scale);
   DASH_LINE_H    = (int)(DASH_BASE_LINE_H * scale);
   DASH_MARGIN_L  = (int)(DASH_BASE_MARGIN_L * scale);
   DASH_VALUE_COL = (int)(DASH_BASE_VALUE_COL * scale);
   DASH_FONT_SIZE = (int)(DASH_BASE_FONT_SIZE * scale);
   if(DASH_LINE_H < 10) DASH_LINE_H = 10;
   if(DASH_FONT_SIZE < 6) DASH_FONT_SIZE = 6;
   if(DASH_WIDTH < 200) DASH_WIDTH = 200;
}

//+------------------------------------------------------------------+
//| Create or update a label object                                    |
//+------------------------------------------------------------------+
void DashLabel(string name, int x, int y, string text, color clr, int fontSize = -1)
{
   if(fontSize < 0) fontSize = DASH_FONT_SIZE;
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
   ObjectSetString(0, objName, OBJPROP_FONT, DASH_FONT);
}

//+------------------------------------------------------------------+
//| Create or update background panel                                  |
//+------------------------------------------------------------------+
void DashBackground(string name, int x, int y, int width, int height, color bgColor)
{
   string objName = "NXS_" + name;
   if(ObjectFind(0, objName) < 0)
   {
      ObjectCreate(0, objName, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, objName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, objName, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, objName, OBJPROP_HIDDEN, true);
      ObjectSetInteger(0, objName, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, objName, OBJPROP_BACK, false);
   }
   ObjectSetInteger(0, objName, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, objName, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, objName, OBJPROP_XSIZE, width);
   ObjectSetInteger(0, objName, OBJPROP_YSIZE, height);
   ObjectSetInteger(0, objName, OBJPROP_BGCOLOR, bgColor);
   ObjectSetInteger(0, objName, OBJPROP_COLOR, clrDimGray);
   ObjectSetInteger(0, objName, OBJPROP_WIDTH, 1);
}

//+------------------------------------------------------------------+
//| Draw section separator                                             |
//+------------------------------------------------------------------+
void DashSeparator(int &y, string label)
{
   y += 4;
   DashLabel("sep_" + label, DASH_X + DASH_MARGIN_L, y,
             "--- " + label + " ---", CLR_HEADER, DASH_FONT_SIZE - 1);
   y += DASH_LINE_H;
}

//+------------------------------------------------------------------+
//| Draw a label:value row                                             |
//+------------------------------------------------------------------+
void DashRow(int &y, string id, string label, string value, color valClr = CLR_VALUE)
{
   DashLabel(id + "_l", DASH_X + DASH_MARGIN_L, y, label, CLR_LABEL);
   DashLabel(id + "_v", DASH_X + DASH_VALUE_COL, y, value, valClr);
   y += DASH_LINE_H;
}


//+------------------------------------------------------------------+
//| Main dashboard update                                              |
//+------------------------------------------------------------------+
void UpdateDashboard(double bid, double ema9Val, double ema50Val, double ema60Val)
{
   DashComputeScale();
   int y = DASH_Y + 10;

   // Background panel
   DashBackground("bg", DASH_X, DASH_Y, DASH_WIDTH, 480, CLR_BG_PANEL);

   // --- HEADER ---
   DashLabel("title", DASH_X + DASH_MARGIN_L, y,
             "NeuroX v9 Standalone", CLR_TITLE, DASH_FONT_SIZE + 2);
   y += DASH_LINE_H + 2;
   DashLabel("subtitle", DASH_X + DASH_MARGIN_L, y,
             "EMA9 Candle-Close Scalper v9.40", CLR_ACCENT, DASH_FONT_SIZE);
   y += DASH_LINE_H + 4;

   // --- STRATEGY ---
   DashSeparator(y, "STRATEGY");

   // 50 EMA Trend
   string trendStr = g_trendStatus;
   color trendClr = CLR_NEUTRAL;
   if(trendStr == "BULLISH")       trendClr = CLR_POSITIVE;
   else if(trendStr == "BEARISH")  trendClr = CLR_NEGATIVE;
   else if(trendStr == "CONFLICTING") trendClr = clrOrange;
   else if(trendStr == "WARMUP")   trendClr = clrYellow;
   if(ema50Val > 0.0)
      trendStr = trendStr + " (" + DoubleToString(ema50Val, 2) + ")";
   DashRow(y, "st_ema50", IntegerToString(InpEmaTrendPeriod) + " EMA Trend:", trendStr, trendClr);

   // EMA Alignment
   color alignClr = CLR_NEUTRAL;
   if(g_alignStatus == "ALIGNED")        alignClr = CLR_POSITIVE;
   else if(g_alignStatus == "CONFLICTING") alignClr = clrOrange;
   else if(g_alignStatus == "WAITING")    alignClr = clrYellow;
   DashRow(y, "st_align", "EMA Alignment:", g_alignStatus, alignClr);

   // EMA 9 Direction
   color ema9Clr = CLR_NEUTRAL;
   if(StringFind(g_ema9Direction, "BUY") >= 0)       ema9Clr = CLR_POSITIVE;
   else if(StringFind(g_ema9Direction, "SELL") >= 0) ema9Clr = CLR_NEGATIVE;
   else if(g_ema9Direction == "WARMUP")              ema9Clr = clrYellow;
   DashRow(y, "st_ema9", "EMA 9:", g_ema9Direction, ema9Clr);

   // Market Filter (choppy votes)
   string filterStr = IntegerToString(g_choppyVotes) + "/5";
   color filterClr = CLR_POSITIVE;
   if(g_choppyVotes >= InpRangingFilterAgreement)
   {
      filterStr += " CHOPPY";
      filterClr = CLR_NEGATIVE;
   }
   else
   {
      filterStr += " TRENDING";
      filterClr = CLR_POSITIVE;
   }
   DashRow(y, "st_filter", "Market Filter:", filterStr, filterClr);

   // EMA Distance
   string emaDistStr = "---";
   color emaDistClr = CLR_NEUTRAL;
   if(ema9Val > 0.0 && bid > 0.0)
   {
      emaDistStr = "$" + DoubleToString(g_currentEmaDistance, 2) +
                   " / $" + DoubleToString(InpEmaMaxDistance, 2);
      emaDistClr = (g_currentEmaDistance <= InpEmaMaxDistance) ? CLR_POSITIVE : CLR_NEGATIVE;
   }
   DashRow(y, "st_dist", "EMA Distance:", emaDistStr, emaDistClr);

   // SL Level
   color slClr = (g_slLevelStr == "---") ? CLR_NEUTRAL : CLR_ACCENT;
   string slDisplayStr = g_slLevelStr;
   if(InpEmaSlEnabled && g_trackedTicket > 0)
      slDisplayStr = "EMA" + IntegerToString(InpEmaSlPeriod) + " " + g_slLevelStr;
   DashRow(y, "st_sl", "SL Level:", slDisplayStr, slClr);

   // Breakeven status
   color beClr = CLR_NEUTRAL;
   if(StringFind(g_beStatus, "LOCKED") >= 0)     beClr = CLR_POSITIVE;
   else if(StringFind(g_beStatus, "ARMED") >= 0) beClr = clrYellow;
   DashRow(y, "st_be", "Breakeven:", g_beStatus, beClr);

   // Candle Close countdown
   int secRemaining = 60 - (int)(TimeCurrent() % 60);
   string candleStr = IntegerToString(secRemaining) + "s";
   color candleClr = (secRemaining <= 10) ? clrYellow : CLR_VALUE;
   DashRow(y, "st_candle", "Candle Close:", candleStr, candleClr);

   // Reversal status
   color revClr = CLR_POSITIVE;
   if(g_reversalStatus == "DETECTED") revClr = CLR_NEGATIVE;
   DashRow(y, "st_rev", "Reversal:", g_reversalStatus, revClr);

   // Decision
   string decStr = g_decision;
   color decClr = CLR_NEUTRAL;
   if(g_decision == "TRADING")       decClr = CLR_POSITIVE;
   else if(g_decision == "HOLDING")  decClr = CLR_POSITIVE;
   else if(g_decision == "COOLDOWN") decClr = clrYellow;
   else if(g_decision == "FILTERED") decClr = CLR_NEGATIVE;
   DashRow(y, "st_dec", "Decision:", decStr, decClr);

   // Filter reason
   if(g_decision == "FILTERED" && StringLen(g_decisionReason) > 0)
      DashRow(y, "st_reason", "Reason:", g_decisionReason, CLR_NEGATIVE);

   y += 4;

   // --- POSITION ---
   DashSeparator(y, "POSITION");

   int openPos = CountMyPositions();
   DashRow(y, "pos_cnt", "Open:", IntegerToString(openPos));

   double floatingPL = CalculateFloatingPL();
   color plColor = (floatingPL >= 0) ? CLR_POSITIVE : CLR_NEGATIVE;
   string plSign = (floatingPL >= 0) ? "+" : "";
   DashRow(y, "pos_pl", "Floating P/L:",
           plSign + "$" + DoubleToString(floatingPL, 2), plColor);
   y += 4;

   // --- DAILY P&L ---
   DashSeparator(y, "DAILY P&L");

   color dailyClr = (g_realizedPnl >= 0) ? CLR_POSITIVE : CLR_NEGATIVE;
   string dailySign = (g_realizedPnl >= 0) ? "+" : "";
   DashRow(y, "day_pnl", "Realized:",
           dailySign + "$" + DoubleToString(g_realizedPnl, 2), dailyClr);

   DashRow(y, "day_wl", "W / L:",
           IntegerToString(g_winsToday) + " / " + IntegerToString(g_lossesToday), CLR_VALUE);

   int closed = g_winsToday + g_lossesToday;
   double winRate = (closed > 0) ? (double)g_winsToday / (double)closed * 100.0 : 0.0;
   color wrClr = (winRate >= 60) ? CLR_POSITIVE : (winRate >= 45) ? CLR_VALUE : CLR_NEGATIVE;
   DashRow(y, "day_wr", "Win Rate:", DoubleToString(winRate, 1) + "%", wrClr);
   y += 4;

   // --- Resize background to fit ---
   int finalHeight = y - DASH_Y + DASH_LINE_H;
   ObjectSetInteger(0, "NXS_bg", OBJPROP_YSIZE, finalHeight);

   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Calculate total floating P/L for this EA                           |
//+------------------------------------------------------------------+
double CalculateFloatingPL()
{
   double totalPL = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(!g_position.SelectByIndex(i)) continue;
      if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
         totalPL += g_position.Profit() + g_position.Swap() + g_position.Commission();
   }
   return totalPL;
}
//+------------------------------------------------------------------+
