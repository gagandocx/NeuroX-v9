//+------------------------------------------------------------------+
//|                                         NeuroX_Execution.mqh       |
//|                              NeuroX v9.0 - Trade Execution Engine   |
//|                                                                    |
//|  Handles all order execution: market, limit, partial entry.        |
//|  Signal validation, lot normalization, brain overrides.            |
//+------------------------------------------------------------------+
#ifndef NEUROX_EXECUTION_MQH
#define NEUROX_EXECUTION_MQH

#include "NeuroX_Types.mqh"

//+------------------------------------------------------------------+
//| Input parameters are defined in main EA (NeuroX_EA_v9.mq5)        |
//| They are visible here since this file is #included directly.       |
//+------------------------------------------------------------------+


//+------------------------------------------------------------------+
//| Forward declarations from other modules                            |
//+------------------------------------------------------------------+
void TrackNewPosition(ulong ticket, double entryPrice, double volume);
void WriteConfirmation(string action, double lots, double price,
                       double sl, double tp, string status,
                       ulong ticketNum, double profit, double slippage);
void UpdateDailyStats_TradeOpened();

//+------------------------------------------------------------------+
//| Normalize lot size with all broker constraints                     |
//+------------------------------------------------------------------+
double NormalizeLotSize(double rawLot)
{
    if(rawLot <= 0)
        rawLot = InpDefaultLotSize;

    double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double lotSize = MathFloor(rawLot / lotStep) * lotStep;
    lotSize = MathMax(lotSize, InpMinLotSize);
    lotSize = MathMax(lotSize, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN));
    lotSize = MathMin(lotSize, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX));
    lotSize = MathMin(lotSize, InpMaxLotSize);

    // Apply brain lot multiplier
    if(g_brain_lot_mult > 0 && g_brain_lot_mult != 1.0)
    {
        double clampedMult = MathMin(MathMax(g_brain_lot_mult, 0.1), 5.0);
        lotSize = lotSize * clampedMult;
        lotSize = MathFloor(lotSize / lotStep) * lotStep;
        lotSize = MathMax(lotSize, InpMinLotSize);
        lotSize = MathMin(lotSize, InpMaxLotSize);
    }

    return lotSize;
}


//+------------------------------------------------------------------+
//| Calculate SL price based on brain override or fixed input          |
//+------------------------------------------------------------------+
double CalculateSL(double price, bool isBuy, int digits, double pipValue)
{
    double activeSL = (g_brain_sl > 0) ? MathMin(MathMax(g_brain_sl, 0.0), 20.0) : InpFixedSL;
    double sl = 0;

    if(activeSL > 0)
    {
        sl = isBuy ? NormalizeDouble(price - activeSL, digits)
                   : NormalizeDouble(price + activeSL, digits);
    }
    else
    {
        sl = isBuy ? NormalizeDouble(price - g_lastSLPips * pipValue, digits)
                   : NormalizeDouble(price + g_lastSLPips * pipValue, digits);
    }
    return sl;
}

//+------------------------------------------------------------------+
//| Calculate TP price (0 if dynamic trailing mode or no TP)           |
//+------------------------------------------------------------------+
double CalculateTP(double price, bool isBuy, int digits, double pipValue)
{
    // No TP mode: when tp_pips is 0, return 0 (candle-close exit handles it)
    if(g_lastTPPips <= 0)
        return 0;

    // Dynamic trailing mode: if tp_pips >= threshold, set TP=0
    if(g_lastTPPips >= InpDynamicTPThreshold)
        return 0;

    return isBuy ? NormalizeDouble(price + g_lastTPPips * pipValue, digits)
                 : NormalizeDouble(price - g_lastTPPips * pipValue, digits);
}

//+------------------------------------------------------------------+
//| Check if dynamic TP mode is active                                 |
//+------------------------------------------------------------------+
bool IsDynamicTPMode()
{
    return (g_lastTPPips >= InpDynamicTPThreshold);
}


//+------------------------------------------------------------------+
//| Validate signal before execution                                   |
//+------------------------------------------------------------------+
bool ValidateSignal()
{
    // Dedup guard: skip if this signal was already executed
    if(g_lastSignalTime == g_lastExecutedSignalTime)
    {
        g_status = "Signal already executed at " + TimeToString(g_lastSignalTime, TIME_MINUTES);
        return false;
    }

    // Check action is BUY or SELL
    if(g_lastAction != "BUY" && g_lastAction != "SELL")
    {
        g_status = "Signal: HOLD - No action needed";
        return false;
    }

    // Check signal freshness using TimeLocal() (Python writes local timestamps)
    datetime currentTime = TimeLocal();
    if(currentTime - g_lastSignalTime > InpMaxSignalAge)
    {
        g_status = "Signal expired (age > " + IntegerToString(InpMaxSignalAge) + "s)";
        return false;
    }

    // Check minimum confidence - brain dynamic threshold overrides
    double activeMinConf = (g_brain_min_conf > 0) ? MathMin(MathMax(g_brain_min_conf, 0.0), 1.0) : InpMinConfidence;
    if(g_lastConfidence < activeMinConf)
    {
        g_status = "Low confidence: " + DoubleToString(g_lastConfidence, 4) +
                   " (min=" + DoubleToString(activeMinConf, 4) + ")";
        return false;
    }

    // Brain session pause
    if(g_brain_session_active == 0)
    {
        g_status = "Brain: session paused (drawdown/poor conditions)";
        return false;
    }

    // Check lot size validity
    if(g_lastLotSize < 0 || g_lastLotSize > InpMaxLotSize)
    {
        g_status = "Invalid lot size: " + DoubleToString(g_lastLotSize, 2);
        return false;
    }

    // Check symbol matches gold
    if(StringFind(_Symbol, "XAU") < 0 && StringFind(_Symbol, "GOLD") < 0)
    {
        g_status = "Symbol mismatch - attach to XAUUSD chart";
        return false;
    }

    // Check spread is acceptable (reject wide spreads)
    long currentSpread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
    if(currentSpread > 50)
    {
        g_status = "Spread too wide: " + IntegerToString((int)currentSpread) + " pts (max 50)";
        return false;
    }

    // Check max open positions
    int posCount = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(g_position.SelectByIndex(i))
        {
            if(g_position.Magic() == InpMagicNumber &&
               g_position.Symbol() == _Symbol)
            {
                posCount++;
            }
        }
    }
    if(posCount >= InpMaxOpenTrades)
    {
        g_status = "Max positions reached (" + IntegerToString(posCount) + ")";
        return false;
    }

    return true;
}

//+------------------------------------------------------------------+
//| Execute the validated signal (dispatcher)                           |
//+------------------------------------------------------------------+
void ExecuteSignal()
{
    switch(g_lastEntryType)
    {
        case ENTRY_LIMIT:
            ExecuteLimitOrder();
            break;
        case ENTRY_PARTIAL:
            ExecutePartialEntry();
            break;
        default:
            ExecuteMarketOrder();
            break;
    }
}


//+------------------------------------------------------------------+
//| Execute a standard market order                                    |
//+------------------------------------------------------------------+
void ExecuteMarketOrder()
{
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
    double pipValue = point * 10;
    double lotSize = NormalizeLotSize(g_lastLotSize);
    bool dynamicTP = IsDynamicTPMode();

    if(g_lastAction == "BUY")
    {
        double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double sl = CalculateSL(price, true, digits, pipValue);
        double tp = CalculateTP(price, true, digits, pipValue);

        if(g_trade.Buy(lotSize, _Symbol, price, sl, tp,
                       "NeuroX|" + g_lastModel + "|" + g_lastRegime))
        {
            g_tradesExecuted++;
            g_lastExecutedSignalTime = g_lastSignalTime;
            g_status = "BUY executed @ " + DoubleToString(price, digits);
            Print("[NeuroX] BUY ", lotSize, " lots @ ", price,
                  " SL=", sl, " TP=", (dynamicTP ? "DYNAMIC" : DoubleToString(tp, digits)),
                  " Model=", g_lastModel, " Regime=", g_lastRegime);

            double fillPrice = g_trade.ResultPrice();
            double slippage = (fillPrice > 0) ? MathAbs(fillPrice - price) : 0.0;
            WriteConfirmation("BUY", lotSize, (fillPrice > 0 ? fillPrice : price),
                              sl, tp, "FILLED", 0, 0.0, slippage);

            ulong posTicket = g_trade.ResultDeal();
            if(posTicket == 0) posTicket = g_trade.ResultOrder();
            TrackNewPosition(posTicket, price, lotSize);
            UpdateDailyStats_TradeOpened();
        }
        else
        {
            g_status = "BUY FAILED: " + IntegerToString(g_trade.ResultRetcode());
            Print("[NeuroX] BUY FAILED: ", g_trade.ResultRetcode(),
                  " - ", g_trade.ResultRetcodeDescription());
            WriteConfirmation("BUY", lotSize, 0, 0, 0, "FAILED", 0, 0.0, 0.0);
        }
    }

    else if(g_lastAction == "SELL")
    {
        double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double sl = CalculateSL(price, false, digits, pipValue);
        double tp = CalculateTP(price, false, digits, pipValue);

        if(g_trade.Sell(lotSize, _Symbol, price, sl, tp,
                        "NeuroX|" + g_lastModel + "|" + g_lastRegime))
        {
            g_tradesExecuted++;
            g_lastExecutedSignalTime = g_lastSignalTime;
            g_status = "SELL executed @ " + DoubleToString(price, digits);
            Print("[NeuroX] SELL ", lotSize, " lots @ ", price,
                  " SL=", sl, " TP=", (dynamicTP ? "DYNAMIC" : DoubleToString(tp, digits)),
                  " Model=", g_lastModel, " Regime=", g_lastRegime);

            double fillPrice = g_trade.ResultPrice();
            double slippage = (fillPrice > 0) ? MathAbs(fillPrice - price) : 0.0;
            WriteConfirmation("SELL", lotSize, (fillPrice > 0 ? fillPrice : price),
                              sl, tp, "FILLED", 0, 0.0, slippage);

            ulong posTicket = g_trade.ResultDeal();
            if(posTicket == 0) posTicket = g_trade.ResultOrder();
            TrackNewPosition(posTicket, price, lotSize);
            UpdateDailyStats_TradeOpened();
        }
        else
        {
            g_status = "SELL FAILED: " + IntegerToString(g_trade.ResultRetcode());
            Print("[NeuroX] SELL FAILED: ", g_trade.ResultRetcode(),
                  " - ", g_trade.ResultRetcodeDescription());
            WriteConfirmation("SELL", lotSize, 0, 0, 0, "FAILED", 0, 0.0, 0.0);
        }
    }
}


//+------------------------------------------------------------------+
//| Execute a limit order with timeout fallback to market              |
//+------------------------------------------------------------------+
void ExecuteLimitOrder()
{
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
    double pipValue = point * 10;
    double lotSize = NormalizeLotSize(g_lastLotSize);
    bool dynamicTP = IsDynamicTPMode();
    double limitPrice = NormalizeDouble(g_lastLimitPrice, digits);

    // If limit price is 0 or invalid, fall back to market
    if(limitPrice <= 0)
    {
        Print("[NeuroX] LIMIT: Invalid limit price (", g_lastLimitPrice,
              ") - falling back to market order");
        ExecuteMarketOrder();
        return;
    }

    datetime expiration = TimeCurrent() + InpLimitTimeout;

    if(g_lastAction == "BUY")
    {
        double currentAsk = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        if(limitPrice >= currentAsk)
        {
            Print("[NeuroX] LIMIT: BUY limit >= ASK - executing at market");
            ExecuteMarketOrder();
            return;
        }

        double sl = CalculateSL(limitPrice, true, digits, pipValue);
        double tp = CalculateTP(limitPrice, true, digits, pipValue);

        if(g_trade.BuyLimit(lotSize, limitPrice, _Symbol, sl, tp,
                            ORDER_TIME_SPECIFIED, expiration,
                            "NeuroX|LIMIT|" + g_lastModel))
        {
            g_tradesExecuted++;
            g_lastExecutedSignalTime = g_lastSignalTime;
            g_status = "BUY LIMIT @ " + DoubleToString(limitPrice, digits);
            Print("[NeuroX] BUY LIMIT ", lotSize, " lots @ ", limitPrice,
                  " SL=", sl, " Timeout=", InpLimitTimeout, "s");
            WriteConfirmation("BUY", lotSize, limitPrice, sl, tp,
                              "LIMIT_PLACED", 0, 0.0, 0.0);
        }
        else
        {
            Print("[NeuroX] BUY LIMIT FAILED: ", g_trade.ResultRetcode(),
                  " - Falling back to market");
            ExecuteMarketOrder();
        }
    }

    else if(g_lastAction == "SELL")
    {
        double currentBid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        if(limitPrice <= currentBid)
        {
            Print("[NeuroX] LIMIT: SELL limit <= BID - executing at market");
            ExecuteMarketOrder();
            return;
        }

        double sl = CalculateSL(limitPrice, false, digits, pipValue);
        double tp = CalculateTP(limitPrice, false, digits, pipValue);

        if(g_trade.SellLimit(lotSize, limitPrice, _Symbol, sl, tp,
                             ORDER_TIME_SPECIFIED, expiration,
                             "NeuroX|LIMIT|" + g_lastModel))
        {
            g_tradesExecuted++;
            g_lastExecutedSignalTime = g_lastSignalTime;
            g_status = "SELL LIMIT @ " + DoubleToString(limitPrice, digits);
            Print("[NeuroX] SELL LIMIT ", lotSize, " lots @ ", limitPrice,
                  " SL=", sl, " Timeout=", InpLimitTimeout, "s");
            WriteConfirmation("SELL", lotSize, limitPrice, sl, tp,
                              "LIMIT_PLACED", 0, 0.0, 0.0);
        }
        else
        {
            Print("[NeuroX] SELL LIMIT FAILED: ", g_trade.ResultRetcode(),
                  " - Falling back to market");
            ExecuteMarketOrder();
        }
    }
}


//+------------------------------------------------------------------+
//| Execute partial entry: 50/25/25 three-tranche split               |
//+------------------------------------------------------------------+
void ExecutePartialEntry()
{
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
    double pipValue = point * 10;
    double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double totalLot = NormalizeLotSize(g_lastLotSize);
    bool dynamicTP = IsDynamicTPMode();
    double minLot = MathMax(InpMinLotSize, SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN));

    // Split: 50% market, 25% limit T2, 25% limit T3
    double marketLot = MathFloor((totalLot * 0.50) / lotStep) * lotStep;
    double limit2Lot = MathFloor((totalLot * 0.25) / lotStep) * lotStep;
    double limit3Lot = MathFloor((totalLot - marketLot - limit2Lot) / lotStep) * lotStep;

    // If lot too small to split, execute full at market
    if(marketLot < minLot)
    {
        Print("[NeuroX] PARTIAL: Lot too small to split (",
              DoubleToString(totalLot, 2), ") - full market order");
        ExecuteMarketOrder();
        return;
    }

    // Redistribute if limit tranches below minimum
    if(limit2Lot < minLot) { marketLot = totalLot; limit2Lot = 0; limit3Lot = 0; }
    if(limit3Lot < minLot && limit2Lot >= minLot) { limit2Lot += limit3Lot; limit3Lot = 0; }
    if(limit2Lot < minLot) { marketLot = totalLot; limit2Lot = 0; }

    // --- Tranche 1: Market order (50%) ---
    double price = 0, sl = 0, tp = 0;
    bool isBuy = (g_lastAction == "BUY");

    price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                  : SymbolInfoDouble(_Symbol, SYMBOL_BID);
    sl = CalculateSL(price, isBuy, digits, pipValue);
    tp = CalculateTP(price, isBuy, digits, pipValue);


    bool t1Success = false;
    if(isBuy)
        t1Success = g_trade.Buy(marketLot, _Symbol, price, sl, tp,
                                "NeuroX|PARTIAL_T1|" + g_lastModel);
    else
        t1Success = g_trade.Sell(marketLot, _Symbol, price, sl, tp,
                                 "NeuroX|PARTIAL_T1|" + g_lastModel);

    if(t1Success)
    {
        g_tradesExecuted++;
        g_lastExecutedSignalTime = g_lastSignalTime;
        g_status = "PARTIAL " + g_lastAction + " T1 @ " + DoubleToString(price, digits);
        Print("[NeuroX] PARTIAL T1: ", marketLot, " lots @ ", price);

        double fillPrice = g_trade.ResultPrice();
        double slippage = (fillPrice > 0) ? MathAbs(fillPrice - price) : 0.0;
        WriteConfirmation(g_lastAction, marketLot, (fillPrice > 0 ? fillPrice : price),
                          sl, tp, "FILLED", 0, 0.0, slippage);

        ulong posTicket = g_trade.ResultDeal();
        if(posTicket == 0) posTicket = g_trade.ResultOrder();
        TrackNewPosition(posTicket, price, marketLot);
        UpdateDailyStats_TradeOpened();
    }
    else
    {
        Print("[NeuroX] PARTIAL T1 FAILED: ", g_trade.ResultRetcode());
        WriteConfirmation(g_lastAction, marketLot, price, sl, tp, "FAILED", 0, 0.0, 0.0);
        return;
    }

    // --- Tranche 2: Limit order (25%) at configurable ATR offset ---
    if(limit2Lot >= minLot)
    {
        PlacePartialLimit(limit2Lot, price, isBuy, InpPartialT2Offset,
                          digits, pipValue, sl, tp, "T2");
    }

    // --- Tranche 3: Limit order (25%) at deeper offset ---
    if(limit3Lot >= minLot)
    {
        PlacePartialLimit(limit3Lot, price, isBuy, InpPartialT3Offset,
                          digits, pipValue, sl, tp, "T3");
    }
}


//+------------------------------------------------------------------+
//| Place a partial entry limit order at specified offset              |
//+------------------------------------------------------------------+
void PlacePartialLimit(double lotSize, double basePrice, bool isBuy,
                       double offset, int digits, double pipValue,
                       double fallbackSL, double fallbackTP, string tranche)
{
    double limitPrice = isBuy ? NormalizeDouble(basePrice - offset, digits)
                              : NormalizeDouble(basePrice + offset, digits);

    // Use signal limit price if provided
    if(g_lastLimitPrice > 0 && tranche == "T2")
        limitPrice = NormalizeDouble(g_lastLimitPrice, digits);

    datetime expiration = TimeCurrent() + InpLimitTimeout;
    double sl = CalculateSL(limitPrice, isBuy, digits, pipValue);
    double tp = CalculateTP(limitPrice, isBuy, digits, pipValue);

    bool placed = false;
    if(isBuy)
    {
        double currentAsk = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        if(limitPrice < currentAsk)
        {
            placed = g_trade.BuyLimit(lotSize, limitPrice, _Symbol, sl, tp,
                                      ORDER_TIME_SPECIFIED, expiration,
                                      "NeuroX|PARTIAL_" + tranche + "|" + g_lastModel);
        }
    }
    else
    {
        double currentBid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        if(limitPrice > currentBid)
        {
            placed = g_trade.SellLimit(lotSize, limitPrice, _Symbol, sl, tp,
                                       ORDER_TIME_SPECIFIED, expiration,
                                       "NeuroX|PARTIAL_" + tranche + "|" + g_lastModel);
        }
    }

    if(placed)
    {
        Print("[NeuroX] PARTIAL ", tranche, ": ", lotSize,
              " lots LIMIT @ ", DoubleToString(limitPrice, digits));
    }
    else
    {
        // Fallback to market for this tranche
        Print("[NeuroX] PARTIAL ", tranche, " LIMIT FAILED - executing at market");
        double mktPrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                : SymbolInfoDouble(_Symbol, SYMBOL_BID);
        if(isBuy)
            g_trade.Buy(lotSize, _Symbol, mktPrice, fallbackSL, fallbackTP,
                        "NeuroX|PARTIAL_" + tranche + "_MKT|" + g_lastModel);
        else
            g_trade.Sell(lotSize, _Symbol, mktPrice, fallbackSL, fallbackTP,
                         "NeuroX|PARTIAL_" + tranche + "_MKT|" + g_lastModel);
    }
}


//+------------------------------------------------------------------+
//| Handle expired limit orders - fallback to market                   |
//| Called from OnTradeTransaction when ORDER_STATE_EXPIRED detected   |
//+------------------------------------------------------------------+
void HandleExpiredLimitOrder(ulong orderTicket)
{
    if(!HistoryOrderSelect(orderTicket))
        return;

    long magic = HistoryOrderGetInteger(orderTicket, ORDER_MAGIC);
    if(magic != InpMagicNumber)
        return;

    long orderState = HistoryOrderGetInteger(orderTicket, ORDER_STATE);
    if(orderState != ORDER_STATE_EXPIRED)
        return;

    long orderType = HistoryOrderGetInteger(orderTicket, ORDER_TYPE);
    double orderVolume = HistoryOrderGetDouble(orderTicket, ORDER_VOLUME_CURRENT);
    string orderSymbol = HistoryOrderGetString(orderTicket, ORDER_SYMBOL);

    if(orderSymbol != _Symbol) return;
    if(orderType != ORDER_TYPE_BUY_LIMIT && orderType != ORDER_TYPE_SELL_LIMIT) return;
    if(orderVolume <= 0) return;

    Print("[NeuroX] LIMIT EXPIRED: ticket=", orderTicket,
          " type=", (orderType == ORDER_TYPE_BUY_LIMIT ? "BUY_LIMIT" : "SELL_LIMIT"),
          " vol=", DoubleToString(orderVolume, 2), " - MARKET fallback");

    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
    double pipValue = point * 10;
    double lotSize = NormalizeLotSize(orderVolume);
    bool dynamicTP = IsDynamicTPMode();
    bool isBuy = (orderType == ORDER_TYPE_BUY_LIMIT);

    double price = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                         : SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double sl = CalculateSL(price, isBuy, digits, pipValue);
    double tp = CalculateTP(price, isBuy, digits, pipValue);

    bool success = false;
    if(isBuy)
        success = g_trade.Buy(lotSize, _Symbol, price, sl, tp,
                              "NeuroX|LIMIT_EXPIRED_MKT|" + g_lastModel);
    else
        success = g_trade.Sell(lotSize, _Symbol, price, sl, tp,
                               "NeuroX|LIMIT_EXPIRED_MKT|" + g_lastModel);

    if(success)
    {
        Print("[NeuroX] LIMIT->MARKET fallback executed: ", lotSize, " lots @ ", price);
        double fillPrice = g_trade.ResultPrice();
        double slippage = (fillPrice > 0) ? MathAbs(fillPrice - price) : 0.0;
        WriteConfirmation(isBuy ? "BUY" : "SELL", lotSize,
                          (fillPrice > 0 ? fillPrice : price),
                          sl, tp, "FILLED", 0, 0.0, slippage);
        ulong posTicket = g_trade.ResultDeal();
        if(posTicket == 0) posTicket = g_trade.ResultOrder();
        TrackNewPosition(posTicket, price, lotSize);
    }
    else
    {
        Print("[NeuroX] LIMIT->MARKET fallback FAILED: ",
              g_trade.ResultRetcode(), " - ", g_trade.ResultRetcodeDescription());
    }
}

//+------------------------------------------------------------------+
//| Read signal from CSV file (legacy fallback mode)                   |
//+------------------------------------------------------------------+
bool ReadSignalFileCSV()
{
    int fileHandle = FileOpen(InpSignalFile, FILE_READ | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
    if(fileHandle == INVALID_HANDLE)
        return false;

    // Skip header row (11 fields)
    if(!FileIsEnding(fileHandle))
    {
        for(int i = 0; i < 11; i++)
            FileReadString(fileHandle);
    }

    // Read data row
    if(!FileIsEnding(fileHandle))
    {
        string timestamp   = FileReadString(fileHandle);
        string symbol      = FileReadString(fileHandle);
        string action      = FileReadString(fileHandle);
        string confidence  = FileReadString(fileHandle);
        string slPips      = FileReadString(fileHandle);
        string tpPips      = FileReadString(fileHandle);
        string lotSize     = FileReadString(fileHandle);
        string modelName   = FileReadString(fileHandle);
        string regime      = FileReadString(fileHandle);
        string entryType   = FileReadString(fileHandle);
        string limitPrice  = FileReadString(fileHandle);

        g_lastAction     = action;
        g_lastConfidence = StringToDouble(confidence);
        g_lastSLPips     = StringToDouble(slPips);
        g_lastTPPips     = StringToDouble(tpPips);
        g_lastLotSize    = StringToDouble(lotSize);
        g_lastModel      = modelName;
        g_lastRegime     = regime;
        g_lastEntryType  = StringToEntryType(entryType);
        g_lastLimitPrice = StringToDouble(limitPrice);
        g_lastSignalTime = StringToTime(timestamp);
    }
    else
    {
        FileClose(fileHandle);
        return false;
    }

    FileClose(fileHandle);
    return true;
}


//+------------------------------------------------------------------+
//| Write execution confirmation via CSV (legacy fallback)             |
//+------------------------------------------------------------------+
void WriteConfirmationCSV(string action, double lots, double price,
                          double sl, double tp, string status,
                          ulong ticketNum, double profit, double slippage)
{
    int fileHandle = FileOpen(InpConfirmFile, FILE_WRITE | FILE_CSV | FILE_COMMON,
                              ',', CP_UTF8);
    if(fileHandle == INVALID_HANDLE)
    {
        Print("[NeuroX] ERROR: Cannot write confirmation file");
        return;
    }

    // Write header
    FileWrite(fileHandle, "timestamp", "ticket", "symbol", "action",
              "lot_size", "open_price", "sl", "tp", "status", "profit", "slippage");

    string ticketStr;
    if(ticketNum > 0)
        ticketStr = IntegerToString(ticketNum);
    else
        ticketStr = IntegerToString(g_trade.ResultDeal());

    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    FileWrite(fileHandle,
              TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
              ticketStr, _Symbol, action,
              DoubleToString(lots, 2),
              DoubleToString(price, digits),
              DoubleToString(sl, digits),
              DoubleToString(tp, digits),
              status,
              DoubleToString(profit, 2),
              DoubleToString(slippage, 4));

    FileClose(fileHandle);
}

//+------------------------------------------------------------------+
//| Write account balance for Python risk sizing                       |
//+------------------------------------------------------------------+
void WriteBalance()
{
    int fileHandle = FileOpen("neurox_v9_balance.csv", FILE_WRITE | FILE_CSV | FILE_COMMON,
                              ',', CP_UTF8);
    if(fileHandle == INVALID_HANDLE)
        return;

    FileWrite(fileHandle, "timestamp", "balance", "equity");
    FileWrite(fileHandle,
              TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
              DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2),
              DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2));
    FileClose(fileHandle);
}

//+------------------------------------------------------------------+
//| Read Brain settings from Python TradingBrain CSV                   |
//+------------------------------------------------------------------+
void ReadBrainSettingsCSV()
{
    // NOTE: v9 does not write brain_settings.csv (no TradingBrain in v9).
    // This read is kept for forward-compatibility but will no-op (file missing).
    int fh = FileOpen("neurox_v9_brain_settings.csv",
                      FILE_READ | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
    if(fh == INVALID_HANDLE) return;

    // Skip header
    if(!FileIsEnding(fh)) { FileReadString(fh); FileReadString(fh); }

    while(!FileIsEnding(fh))
    {
        string param = FileReadString(fh);
        string val   = FileReadString(fh);
        double v     = StringToDouble(val);

        if     (param == "sl_dollars")      g_brain_sl             = v;
        else if(param == "min_confidence")  g_brain_min_conf       = v;
        else if(param == "lot_multiplier")  g_brain_lot_mult       = v;
        else if(param == "be_profit")       g_brain_be_profit      = v;
        else if(param == "trail_start")     g_brain_trail_start    = v;
        else if(param == "session_active")  g_brain_session_active = (int)v;
    }
    FileClose(fh);
    g_brain_last_read = TimeCurrent();
}

//+------------------------------------------------------------------+
//| Read intelligence file (regime, filters, decision from Python)      |
//+------------------------------------------------------------------+
void ReadIntelligenceFile()
{
    int fileHandle = FileOpen(InpIntelligenceFile, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
    if(fileHandle == INVALID_HANDLE) return;

    if(!FileIsEnding(fileHandle))
    {
        string line = FileReadString(fileHandle);
        FileClose(fileHandle);
        if(StringLen(line) == 0) return;

        // Parse pipe-delimited: regime|atr_value|atr_pass|tick_pct|tick_dir|persistence_count|persistence_dir|strategy|decision|reason|ema_trend
        string fields[];
        int count = StringSplit(line, '|', fields);
        if(count >= 10)
        {
            g_intelRegime      = fields[0];
            g_intelATR         = StringToDouble(fields[1]);
            g_intelATRPass     = (fields[2] == "1");
            g_intelTickPct     = StringToDouble(fields[3]);
            g_intelTickDir     = fields[4];
            g_intelPersistence = (int)StringToInteger(fields[5]);
            g_intelPersistDir  = fields[6];
            g_intelStrategy    = fields[7];
            g_intelDecision    = fields[8];
            g_intelReason      = fields[9];
            g_intelEmaTrend    = (count >= 11) ? fields[10] : "";
        }
    }
    else
        FileClose(fileHandle);
}

//+------------------------------------------------------------------+
//| Read Python bridge status file                                     |
//+------------------------------------------------------------------+
void ReadStatusFile()
{
    int fileHandle = FileOpen(InpStatusFile, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
    if(fileHandle == INVALID_HANDLE) return;

    if(!FileIsEnding(fileHandle))
    {
        string line = FileReadString(fileHandle);
        FileClose(fileHandle);
        if(StringLen(line) == 0) return;

        int sep = StringFind(line, "|");
        if(sep > 0)
        {
            string typeStr = StringSubstr(line, 0, sep);
            g_newsWarning = StringSubstr(line, sep + 1);
            if(typeStr == "NEWS")         g_statusType = STATUS_NEWS;
            else if(typeStr == "WARNING") g_statusType = STATUS_WARNING;
            else if(typeStr == "ERROR")   g_statusType = STATUS_ERROR;
            else                          g_statusType = STATUS_OK;
        }
        else
        {
            g_statusType = STATUS_OK;
            g_newsWarning = line;
        }
    }
    else
        FileClose(fileHandle);
}

#endif // NEUROX_EXECUTION_MQH
