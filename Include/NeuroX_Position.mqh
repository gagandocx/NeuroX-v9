//+------------------------------------------------------------------+
//|                                          NeuroX_Position.mqh       |
//|                              NeuroX v9.0 - Position Management     |
//|                                                                    |
//|  Position tracking, progressive trailing stops, momentum exits,    |
//|  time-based exits, emergency close, exit signal processing,        |
//|  and daily performance statistics.                                 |
//+------------------------------------------------------------------+
#ifndef NEUROX_POSITION_MQH
#define NEUROX_POSITION_MQH

#include "NeuroX_Types.mqh"

//+------------------------------------------------------------------+
//| Input parameters are defined in main EA (NeuroX_EA_v9.mq5)        |
//| They are visible here since this file is #included directly.       |
//+------------------------------------------------------------------+


//+------------------------------------------------------------------+
//| Forward declarations                                               |
//+------------------------------------------------------------------+
void WriteConfirmation(string action, double lots, double price,
                       double sl, double tp, string status,
                       ulong ticketNum, double profit, double slippage);
void WriteBalance();

//+------------------------------------------------------------------+
//| Track a new position                                               |
//+------------------------------------------------------------------+
void TrackNewPosition(ulong ticket, double entryPrice, double volume)
{
    // FIFO overflow protection
    if(g_trackedCount >= MAX_TRACKED_POSITIONS)
    {
        Print("[NeuroX] WARNING: Position tracking overflow! FIFO removing oldest. ",
              "Ticket=", g_tracked[0].ticket, " to make room for ", ticket);
        for(int j = 0; j < g_trackedCount - 1; j++)
            g_tracked[j] = g_tracked[j + 1];
        g_trackedCount--;
    }

    g_tracked[g_trackedCount].ticket      = ticket;
    g_tracked[g_trackedCount].entry_time  = TimeCurrent();
    g_tracked[g_trackedCount].entry_price = entryPrice;
    g_tracked[g_trackedCount].volume      = volume;
    g_tracked[g_trackedCount].active      = true;
    g_trackedCount++;

    Print("[NeuroX] Tracking position ticket=", ticket,
          " entry=", DoubleToString(entryPrice, 2),
          " vol=", DoubleToString(volume, 2),
          " tracked=", g_trackedCount, "/", MAX_TRACKED_POSITIONS);
}

//+------------------------------------------------------------------+
//| Remove a tracked position                                          |
//+------------------------------------------------------------------+
void UntrackPosition(ulong ticket)
{
    for(int i = 0; i < g_trackedCount; i++)
    {
        if(g_tracked[i].ticket == ticket)
        {
            for(int j = i; j < g_trackedCount - 1; j++)
                g_tracked[j] = g_tracked[j + 1];
            g_trackedCount--;
            return;
        }
    }
}


//+------------------------------------------------------------------+
//| Get entry time for a tracked position                              |
//+------------------------------------------------------------------+
datetime GetTrackedEntryTime(ulong ticket)
{
    for(int i = 0; i < g_trackedCount; i++)
        if(g_tracked[i].ticket == ticket)
            return g_tracked[i].entry_time;
    return 0;
}

//+------------------------------------------------------------------+
//| Get entry price for a tracked position                             |
//+------------------------------------------------------------------+
double GetTrackedEntryPrice(ulong ticket)
{
    for(int i = 0; i < g_trackedCount; i++)
        if(g_tracked[i].ticket == ticket)
            return g_tracked[i].entry_price;
    return 0;
}

//+------------------------------------------------------------------+
//| Initialize daily stats for a new day                               |
//+------------------------------------------------------------------+
void InitDailyStats()
{
    g_dailyStats.date            = TimeCurrent();
    g_dailyStats.starting_equity = AccountInfoDouble(ACCOUNT_EQUITY);
    g_dailyStats.realized_pnl   = 0.0;
    g_dailyStats.trades_total    = 0;
    g_dailyStats.trades_won      = 0;
    g_dailyStats.trades_lost     = 0;
    g_dailyStats.largest_win     = 0.0;
    g_dailyStats.largest_loss    = 0.0;
    g_dailyStats.gross_profit    = 0.0;
    g_dailyStats.gross_loss      = 0.0;
    g_dailyStats.consecutive_wins   = 0;
    g_dailyStats.consecutive_losses = 0;
    g_dailyStats.max_consecutive_wins   = 0;
    g_dailyStats.max_consecutive_losses = 0;
}

//+------------------------------------------------------------------+
//| Check if a new day has started (reset daily stats)                 |
//+------------------------------------------------------------------+
void CheckDayRollover()
{
    MqlDateTime now, stored;
    TimeCurrent(now);
    TimeToStruct(g_dailyStats.date, stored);

    if(now.day != stored.day || now.mon != stored.mon || now.year != stored.year)
    {
        Print("[NeuroX] Day rollover detected. Yesterday: ",
              g_dailyStats.trades_total, " trades, P&L=$",
              DoubleToString(g_dailyStats.realized_pnl, 2));
        InitDailyStats();
    }
}


//+------------------------------------------------------------------+
//| Update daily stats when a trade is opened                          |
//+------------------------------------------------------------------+
void UpdateDailyStats_TradeOpened()
{
    g_dailyStats.trades_total++;
}

//+------------------------------------------------------------------+
//| Update daily stats when a trade is closed                          |
//+------------------------------------------------------------------+
void UpdateDailyStats_TradeClosed(double profit)
{
    g_dailyStats.realized_pnl += profit;

    if(profit > 0)
    {
        g_dailyStats.trades_won++;
        g_dailyStats.gross_profit += profit;
        if(profit > g_dailyStats.largest_win)
            g_dailyStats.largest_win = profit;

        // Streak tracking
        g_dailyStats.consecutive_wins++;
        g_dailyStats.consecutive_losses = 0;
        if(g_dailyStats.consecutive_wins > g_dailyStats.max_consecutive_wins)
            g_dailyStats.max_consecutive_wins = g_dailyStats.consecutive_wins;
    }
    else if(profit < 0)
    {
        g_dailyStats.trades_lost++;
        g_dailyStats.gross_loss += MathAbs(profit);
        if(profit < g_dailyStats.largest_loss)
            g_dailyStats.largest_loss = profit;

        // Streak tracking
        g_dailyStats.consecutive_losses++;
        g_dailyStats.consecutive_wins = 0;
        if(g_dailyStats.consecutive_losses > g_dailyStats.max_consecutive_losses)
            g_dailyStats.max_consecutive_losses = g_dailyStats.consecutive_losses;
    }
}

//+------------------------------------------------------------------+
//| Get daily win rate as percentage                                    |
//+------------------------------------------------------------------+
double GetDailyWinRate()
{
    int closed = g_dailyStats.trades_won + g_dailyStats.trades_lost;
    if(closed == 0) return 0.0;
    return (double)g_dailyStats.trades_won / (double)closed * 100.0;
}

//+------------------------------------------------------------------+
//| Get profit factor                                                  |
//+------------------------------------------------------------------+
double GetProfitFactor()
{
    if(g_dailyStats.gross_loss == 0) return (g_dailyStats.gross_profit > 0) ? 99.9 : 0.0;
    return g_dailyStats.gross_profit / g_dailyStats.gross_loss;
}


//+------------------------------------------------------------------+
//| Detect broker-closed positions (SL/TP hit)                         |
//+------------------------------------------------------------------+
void DetectBrokerClosedPositions()
{
    for(int t = g_trackedCount - 1; t >= 0; t--)
    {
        ulong trackedTicket = g_tracked[t].ticket;
        if(!PositionSelectByTicket(trackedTicket))
        {
            // Position no longer exists - broker closed it
            double entryPriceTracked = g_tracked[t].entry_price;
            double trackedVol = g_tracked[t].volume;
            double closePrice = 0.0;
            double closedProfit = 0.0;
            double closedVolume = trackedVol;
            string closedAction = "BUY";

            // Search deal history for the close deal
            if(HistorySelect(TimeCurrent() - 300, TimeCurrent()))
            {
                for(int d = HistoryDealsTotal() - 1; d >= 0; d--)
                {
                    ulong dealTicket = HistoryDealGetTicket(d);
                    if(dealTicket == 0) continue;
                    long dealPosId = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
                    if((ulong)dealPosId == trackedTicket &&
                       HistoryDealGetInteger(dealTicket, DEAL_ENTRY) == DEAL_ENTRY_OUT)
                    {
                        closePrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
                        closedProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                                     + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                                     + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
                        closedVolume = HistoryDealGetDouble(dealTicket, DEAL_VOLUME);
                        long dealType = HistoryDealGetInteger(dealTicket, DEAL_TYPE);
                        closedAction = (dealType == DEAL_TYPE_SELL) ? "BUY" : "SELL";
                        break;
                    }
                }
            }

            // Fallback if deal history lookup failed
            if(closePrice == 0.0)
            {
                closePrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                closedAction = (closePrice >= entryPriceTracked) ? "BUY" : "SELL";
            }

            int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
            Print("[NeuroX] SL/TP HIT: Ticket ", trackedTicket,
                  " Entry=", DoubleToString(entryPriceTracked, digits),
                  " Close=", DoubleToString(closePrice, digits),
                  " P&L=$", DoubleToString(closedProfit, 2));

            WriteConfirmation(closedAction, closedVolume, closePrice, 0, 0, "CLOSED",
                              trackedTicket, closedProfit, 0.0);
            UpdateDailyStats_TradeClosed(closedProfit);
            UntrackPosition(trackedTicket);
        }
    }
}


//+------------------------------------------------------------------+
//| Manage open positions with breakeven SL only                       |
//| Called on EVERY TICK for real-time position management              |
//| Candle-close exit and reversal detection handled by Python.         |
//| EA only handles: $5 BE move and emergency close.                   |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
    double pipValue = point * 10;
    datetime currentTime = TimeCurrent();
    int positionsManaged = 0;
    string trailInfo = "";

    // Detect broker-closed positions first (SL hits)
    DetectBrokerClosedPositions();

    // Loop through all positions with this EA's magic number
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(!g_position.SelectByIndex(i))
            continue;
        if(g_position.Magic() != InpMagicNumber || g_position.Symbol() != _Symbol)
            continue;

        ulong ticket = g_position.Ticket();
        double entryPrice = g_position.PriceOpen();
        double currentSL = g_position.StopLoss();
        double currentTP = g_position.TakeProfit();
        double volume = g_position.Volume();
        double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();
        ENUM_POSITION_TYPE posType = g_position.PositionType();
        bool isBuy = (posType == POSITION_TYPE_BUY);

        double currentPrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                                    : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

        positionsManaged++;

        // Get or register entry time
        datetime entryTime = GetTrackedEntryTime(ticket);
        if(entryTime == 0)
        {
            TrackNewPosition(ticket, entryPrice, volume);
            entryTime = currentTime;
        }

        // --- BREAKEVEN LOGIC: $6 profit -> move SL to entry + lockDist ---
        // Brain-controlled threshold or default $6/$5
        double beProfit = (g_brain_be_profit > 0) ? g_brain_be_profit : InpBreakevenProfit;
        // Convert dollar lock amount to price distance using lot size and contract size
        // Lock $5 profit: lockDist = $5 / (0.10 lots * 100 contract) = $0.50
        double beLock = InpBreakevenLock / (InpDefaultLotSize * 100.0);

        // Minimum stop distance from broker
        double minStopDist = (SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) + 1)
                             * SymbolInfoDouble(_Symbol, SYMBOL_POINT);
        double currentBid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        double currentAsk = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

        if(profit >= beProfit)
        {
            double newSL = 0;
            if(isBuy)
                newSL = NormalizeDouble(entryPrice + beLock, digits);
            else
                newSL = NormalizeDouble(entryPrice - beLock, digits);

            // Validate against minimum stop distance
            bool validStop = true;
            if(isBuy && newSL >= currentBid - minStopDist)
                validStop = false;
            if(!isBuy && newSL <= currentAsk + minStopDist)
                validStop = false;

            // Only move SL in favorable direction (never widen)
            bool shouldModify = false;
            if(validStop)
            {
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
            }

            // Cooldown: max one modify per second
            if(shouldModify && (currentTime - g_lastModifyAttempt) >= 1)
            {
                if(g_trade.PositionModify(ticket, newSL, currentTP))
                {
                    g_lastModifyAttempt = currentTime;
                    Print("[NeuroX] BE MOVE: Ticket ", ticket,
                          " SL=", DoubleToString(newSL, digits),
                          " LockDist=", DoubleToString(beLock, digits),
                          " (profit $", DoubleToString(profit, 2), " >= $",
                          DoubleToString(beProfit, 2), ")");
                }
            }

            // --- Tight trailing after breakeven ---
            // After BE is locked, trail SL behind price by InpTrailAfterBE
            // NO cooldown here - trail must update every tick as price moves
            double trailSL = 0;
            if(isBuy)
                trailSL = NormalizeDouble(currentPrice - InpTrailAfterBE, digits);
            else
                trailSL = NormalizeDouble(currentPrice + InpTrailAfterBE, digits);

            // Validate against minimum stop distance
            bool validTrail = true;
            if(isBuy && trailSL >= currentBid - minStopDist)
                validTrail = false;
            if(!isBuy && trailSL <= currentAsk + minStopDist)
                validTrail = false;

            // Refresh current SL (may have been updated by BE move above)
            if(g_position.SelectByTicket(ticket))
                currentSL = g_position.StopLoss();

            bool shouldTrail = false;
            if(validTrail)
            {
                if(isBuy)
                {
                    if(trailSL > currentSL && currentSL > 0)
                        shouldTrail = true;
                }
                else
                {
                    if(trailSL < currentSL)
                        shouldTrail = true;
                }
            }

            if(shouldTrail)
            {
                if(g_trade.PositionModify(ticket, trailSL, currentTP))
                {
                    g_lastModifyAttempt = currentTime;
                    Print("[NeuroX] TRAIL: Ticket ", ticket,
                          " SL=", DoubleToString(trailSL, digits),
                          " Price=", DoubleToString(currentPrice, digits),
                          " Dist=$", DoubleToString(InpTrailAfterBE, 2));
                }
            }
            else
            {
                // Debug: print why trail was blocked (throttled to once per second)
                static datetime s_lastTrailDebug = 0;
                if(currentTime - s_lastTrailDebug >= 1)
                {
                    s_lastTrailDebug = currentTime;
                    Print("[NeuroX] TRAIL BLOCKED: Ticket ", ticket,
                          " trailSL=", DoubleToString(trailSL, digits),
                          " currentSL=", DoubleToString(currentSL, digits),
                          " price=", DoubleToString(currentPrice, digits),
                          " validTrail=", validTrail,
                          " isBuy=", isBuy);
                }
            }
            trailInfo = "TRAIL P:" + DoubleToString(profit, 2);
        }
        else
        {
            trailInfo = "Wait P:" + DoubleToString(profit, 2);
        }
    }

    // Update trail status for dashboard
    if(positionsManaged == 0)
        g_trailStatus = "No positions";
    else if(trailInfo != "")
        g_trailStatus = trailInfo;
    else
        g_trailStatus = IntegerToString(positionsManaged) + " pos managed";
}


//+------------------------------------------------------------------+
//| Emergency close all positions if floating loss exceeds limit       |
//+------------------------------------------------------------------+
void CheckEmergencyCloseAll()
{
    // Cooldown: 5 seconds between triggers
    if(TimeCurrent() - g_lastEmergencyClose < 5)
        return;

    double totalFloatingLoss = 0.0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(g_position.SelectByIndex(i))
        {
            if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
                totalFloatingLoss += g_position.Profit() + g_position.Swap() + g_position.Commission();
        }
    }

    if(totalFloatingLoss < -InpEmergencyLossLimit)
    {
        Print("[NeuroX] EMERGENCY: Floating loss $",
              DoubleToString(MathAbs(totalFloatingLoss), 2),
              " exceeds $", DoubleToString(InpEmergencyLossLimit, 2),
              " limit. Closing ALL!");
        g_status = "EMERGENCY CLOSE: Loss > $" + DoubleToString(InpEmergencyLossLimit, 0);
        g_lastEmergencyClose = TimeCurrent();

        for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
            if(g_position.SelectByIndex(i))
            {
                if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
                {
                    ulong ticket = g_position.Ticket();
                    double volume = g_position.Volume();
                    double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();

                    if(g_position.PositionType() == POSITION_TYPE_BUY)
                    {
                        double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                        g_trade.Sell(volume, _Symbol, price, 0, 0, "NeuroX|Emergency");
                    }
                    else
                    {
                        double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                        g_trade.Buy(volume, _Symbol, price, 0, 0, "NeuroX|Emergency");
                    }
                    Print("[NeuroX] Emergency closed ticket ", ticket);
                    UpdateDailyStats_TradeClosed(profit);
                    UntrackPosition(ticket);
                }
            }
        }
    }
}


//+------------------------------------------------------------------+
//| Process exit signals from Python Smart Exit Manager               |
//+------------------------------------------------------------------+
void ProcessExitSignals()
{
    int fileHandle = FileOpen(InpExitFile, FILE_READ | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
    if(fileHandle == INVALID_HANDLE)
        return;

    // Skip header (6 fields)
    if(!FileIsEnding(fileHandle))
    {
        for(int i = 0; i < 6; i++)
            FileReadString(fileHandle);
    }

    while(!FileIsEnding(fileHandle))
    {
        string timestamp = FileReadString(fileHandle);
        string ticket    = FileReadString(fileHandle);
        string action    = FileReadString(fileHandle);
        string lotPct    = FileReadString(fileHandle);
        string newSL     = FileReadString(fileHandle);
        string reason    = FileReadString(fileHandle);

        if(StringLen(ticket) == 0) break;

        long ticketNum = StringToInteger(ticket);
        double lotPercent = StringToDouble(lotPct);
        double newStopLoss = StringToDouble(newSL);

        Print("[NeuroX] Exit signal: ticket=", ticket,
              " action=", action, " lot_pct=", lotPct,
              " new_sl=", newSL, " reason=", reason);

        if(action == "CLOSE_FULL")
            ClosePosition(ticketNum, 1.0);
        else if(action == "CLOSE_PARTIAL")
            ClosePosition(ticketNum, lotPercent);
        else if(action == "MODIFY_SL")
            ModifyPositionSL(ticketNum, newStopLoss);
    }

    FileClose(fileHandle);
    FileDelete(InpExitFile, FILE_COMMON);
}


//+------------------------------------------------------------------+
//| Close a position (full or partial)                                 |
//+------------------------------------------------------------------+
void ClosePosition(long ticket, double lotPercent)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(g_position.SelectByIndex(i))
        {
            if(g_position.Magic() == InpMagicNumber &&
               g_position.Ticket() == (ulong)ticket)
            {
                double volume = g_position.Volume();
                double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
                double closeVolume = NormalizeDouble(volume * lotPercent,
                    (int)MathLog10(1.0 / lotStep));

                double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
                closeVolume = MathMax(closeVolume, minLot);
                closeVolume = MathMin(closeVolume, volume);

                bool success = false;
                double profit = g_position.Profit() + g_position.Swap() + g_position.Commission();

                if(g_position.PositionType() == POSITION_TYPE_BUY)
                {
                    double price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                    success = g_trade.Sell(closeVolume, _Symbol, price, 0, 0, "NeuroX|SmartExit");
                }
                else
                {
                    double price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                    success = g_trade.Buy(closeVolume, _Symbol, price, 0, 0, "NeuroX|SmartExit");
                }

                if(success && g_trade.ResultRetcode() == TRADE_RETCODE_DONE)
                {
                    Print("[NeuroX] SmartExit: Closed ", closeVolume, " lots of ticket ", ticket);
                    // Scale profit by close percentage
                    double closedProfit = profit * (closeVolume / volume);
                    UpdateDailyStats_TradeClosed(closedProfit);
                    if(lotPercent >= 1.0)
                        UntrackPosition((ulong)ticket);
                }
                else
                {
                    Print("[NeuroX] SmartExit: CLOSE FAILED ticket=", ticket,
                          " retcode=", g_trade.ResultRetcode());
                }
                return;
            }
        }
    }
    Print("[NeuroX] SmartExit: Ticket ", ticket, " not found");
}


//+------------------------------------------------------------------+
//| Modify stop loss for a position                                    |
//+------------------------------------------------------------------+
void ModifyPositionSL(long ticket, double newSL)
{
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(g_position.SelectByIndex(i))
        {
            if(g_position.Magic() == InpMagicNumber &&
               g_position.Ticket() == (ulong)ticket)
            {
                int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
                double sl = NormalizeDouble(newSL, digits);
                double tp = g_position.TakeProfit();

                if(g_trade.PositionModify((ulong)ticket, sl, tp))
                {
                    Print("[NeuroX] SmartExit: SL modified to ",
                          DoubleToString(sl, digits), " ticket=", ticket);
                }
                else
                {
                    Print("[NeuroX] SmartExit: SL modify FAILED ticket=",
                          ticket, " error=", g_trade.ResultRetcode());
                }
                return;
            }
        }
    }
    Print("[NeuroX] SmartExit: Ticket ", ticket, " not found for SL modify");
}

//+------------------------------------------------------------------+
//| Calculate total floating P/L for this EA                           |
//+------------------------------------------------------------------+
double CalculateFloatingPL()
{
    double totalPL = 0.0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(g_position.SelectByIndex(i))
        {
            if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
                totalPL += g_position.Profit() + g_position.Swap() + g_position.Commission();
        }
    }
    return totalPL;
}

//+------------------------------------------------------------------+
//| Count open positions for this EA                                   |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
    int count = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(g_position.SelectByIndex(i))
        {
            if(g_position.Magic() == InpMagicNumber && g_position.Symbol() == _Symbol)
                count++;
        }
    }
    return count;
}

#endif // NEUROX_POSITION_MQH
