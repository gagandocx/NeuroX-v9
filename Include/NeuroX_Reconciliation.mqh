//+------------------------------------------------------------------+
//|                                     NeuroX_Reconciliation.mqh      |
//|                              NeuroX v9.0 - Position Reconciliation  |
//|                                                                    |
//|  On EA init/restart, scans all open positions belonging to this     |
//|  EA (by magic number) and rebuilds the internal tracking arrays.    |
//|  Also recovers daily stats from today's closed deals in history.    |
//|                                                                    |
//|  This ensures no position is "orphaned" after:                     |
//|    - EA restart (manual or crash)                                  |
//|    - Terminal restart                                               |
//|    - Timeframe change                                              |
//|    - Template change                                                |
//+------------------------------------------------------------------+
#ifndef NEUROX_RECONCILIATION_MQH
#define NEUROX_RECONCILIATION_MQH

#include "NeuroX_Types.mqh"

//+------------------------------------------------------------------+
//| Input parameters are defined in main EA (NeuroX_EA_v9.mq5)        |
//| They are visible here since this file is #included directly.       |
//+------------------------------------------------------------------+


//+------------------------------------------------------------------+
//| Forward declarations                                               |
//+------------------------------------------------------------------+
void TrackNewPosition(ulong ticket, double entryPrice, double volume);
void InitDailyStats();
void UpdateDailyStats_TradeClosed(double profit);

//+------------------------------------------------------------------+
//| Reconcile open positions on EA init                                 |
//|                                                                    |
//| Scans all currently open positions matching our magic number and   |
//| symbol, then registers them in the tracking arrays so that:        |
//|   - Trailing stop management works immediately                     |
//|   - Time-based exits have correct entry time                       |
//|   - Momentum detection knows position direction                    |
//|   - Broker SL/TP hit detection works for all positions             |
//|                                                                    |
//| For entry time, we look up the opening deal in trade history.      |
//| If history lookup fails, we use TimeCurrent() as a safe fallback   |
//| (this means time-based exit may trigger early, which is safer      |
//| than never triggering).                                            |
//+------------------------------------------------------------------+
int ReconcileOpenPositions()
{
    int reconciled = 0;
    CPositionInfo pos;

    Print("[NeuroX] Reconciliation: Scanning open positions for magic=",
          InpMagicNumber, " symbol=", _Symbol);

    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(!pos.SelectByIndex(i))
            continue;

        if(pos.Magic() != InpMagicNumber)
            continue;

        if(pos.Symbol() != _Symbol)
            continue;

        ulong ticket = pos.Ticket();
        double entryPrice = pos.PriceOpen();
        double volume = pos.Volume();
        datetime entryTime = 0;

        // Try to find actual entry time from deal history
        entryTime = LookupPositionOpenTime(ticket);

        // If history lookup failed, use position's time field
        if(entryTime == 0)
            entryTime = (datetime)PositionGetInteger(POSITION_TIME);

        // Register in tracking array
        if(g_trackedCount < MAX_TRACKED_POSITIONS)
        {
            g_tracked[g_trackedCount].ticket      = ticket;
            g_tracked[g_trackedCount].entry_time  = entryTime;
            g_tracked[g_trackedCount].entry_price = entryPrice;
            g_tracked[g_trackedCount].volume      = volume;
            g_tracked[g_trackedCount].active      = true;
            g_trackedCount++;
            reconciled++;

            string typeStr = (pos.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
            double profit = pos.Profit() + pos.Swap() + pos.Commission();
            int holdSec = (int)(TimeCurrent() - entryTime);

            Print("[NeuroX] Reconciled: ticket=", ticket,
                  " ", typeStr, " ", DoubleToString(volume, 2), " lots",
                  " @ ", DoubleToString(entryPrice, 2),
                  " P&L=$", DoubleToString(profit, 2),
                  " held=", holdSec, "s");
        }
        else
        {
            Print("[NeuroX] WARNING: Tracking array full during reconciliation! ",
                  "Ticket ", ticket, " NOT tracked.");
        }
    }

    Print("[NeuroX] Reconciliation complete: ", reconciled,
          " positions recovered. Tracked=", g_trackedCount,
          "/", MAX_TRACKED_POSITIONS);

    return reconciled;
}


//+------------------------------------------------------------------+
//| Look up the actual open time of a position from deal history       |
//+------------------------------------------------------------------+
datetime LookupPositionOpenTime(ulong positionTicket)
{
    // Select history for last 7 days (covers weekend gaps)
    datetime fromTime = TimeCurrent() - 7 * 24 * 3600;
    if(!HistorySelect(fromTime, TimeCurrent()))
        return 0;

    for(int d = 0; d < HistoryDealsTotal(); d++)
    {
        ulong dealTicket = HistoryDealGetTicket(d);
        if(dealTicket == 0) continue;

        // Match by position ID and entry type
        long dealPosId = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
        if((ulong)dealPosId != positionTicket)
            continue;

        long dealEntry = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
        if(dealEntry == DEAL_ENTRY_IN)
        {
            return (datetime)HistoryDealGetInteger(dealTicket, DEAL_TIME);
        }
    }

    return 0;  // Not found in history
}

//+------------------------------------------------------------------+
//| Recover today's daily stats from closed deal history               |
//|                                                                    |
//| After EA restart, we scan all closed deals from today to rebuild   |
//| the DailyStats (wins, losses, P&L, streaks). This ensures the     |
//| dashboard shows accurate daily performance even after restart.     |
//+------------------------------------------------------------------+
void RecoverDailyStats()
{
    // Initialize fresh
    InitDailyStats();

    // Get start of today (00:00:00)
    MqlDateTime now;
    TimeCurrent(now);
    now.hour = 0;
    now.min  = 0;
    now.sec  = 0;
    datetime todayStart = StructToTime(now);

    if(!HistorySelect(todayStart, TimeCurrent()))
    {
        Print("[NeuroX] Reconciliation: Cannot load today's history");
        return;
    }

    int dealsRecovered = 0;

    for(int d = 0; d < HistoryDealsTotal(); d++)
    {
        ulong dealTicket = HistoryDealGetTicket(d);
        if(dealTicket == 0) continue;

        // Only our EA's deals
        long dealMagic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);
        if(dealMagic != InpMagicNumber) continue;

        // Only our symbol
        string dealSymbol = HistoryDealGetString(dealTicket, DEAL_SYMBOL);
        if(dealSymbol != _Symbol) continue;

        // Only closing deals (DEAL_ENTRY_OUT)
        long dealEntry = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
        if(dealEntry != DEAL_ENTRY_OUT) continue;

        // Get P&L including swap and commission
        double profit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                      + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                      + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);

        UpdateDailyStats_TradeClosed(profit);
        dealsRecovered++;
    }

    if(dealsRecovered > 0)
    {
        Print("[NeuroX] Daily stats recovered: ", dealsRecovered, " closed deals today",
              " | P&L=$", DoubleToString(g_dailyStats.realized_pnl, 2),
              " | Win rate=", DoubleToString(GetDailyWinRate(), 1), "%",
              " | W/L=", g_dailyStats.trades_won, "/", g_dailyStats.trades_lost);
    }
    else
    {
        Print("[NeuroX] Daily stats: No closed deals today (fresh session)");
    }
}


//+------------------------------------------------------------------+
//| Count pending orders belonging to this EA                          |
//| (Used during reconciliation to report full state)                  |
//+------------------------------------------------------------------+
int ReconcilePendingOrders()
{
    int pending = 0;

    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        ulong orderTicket = OrderGetTicket(i);
        if(orderTicket == 0) continue;

        long orderMagic = OrderGetInteger(ORDER_MAGIC);
        string orderSymbol = OrderGetString(ORDER_SYMBOL);

        if(orderMagic == InpMagicNumber && orderSymbol == _Symbol)
        {
            long orderType = OrderGetInteger(ORDER_TYPE);
            double orderPrice = OrderGetDouble(ORDER_PRICE_OPEN);
            double orderVolume = OrderGetDouble(ORDER_VOLUME_CURRENT);
            datetime orderExpiry = (datetime)OrderGetInteger(ORDER_TIME_EXPIRATION);

            string typeStr = "UNKNOWN";
            if(orderType == ORDER_TYPE_BUY_LIMIT)       typeStr = "BUY_LIMIT";
            else if(orderType == ORDER_TYPE_SELL_LIMIT)  typeStr = "SELL_LIMIT";
            else if(orderType == ORDER_TYPE_BUY_STOP)    typeStr = "BUY_STOP";
            else if(orderType == ORDER_TYPE_SELL_STOP)   typeStr = "SELL_STOP";

            Print("[NeuroX] Pending order found: ticket=", orderTicket,
                  " ", typeStr, " ", DoubleToString(orderVolume, 2), " lots",
                  " @ ", DoubleToString(orderPrice, 2),
                  " expires=", TimeToString(orderExpiry, TIME_SECONDS));
            pending++;
        }
    }

    if(pending > 0)
        Print("[NeuroX] Reconciliation: ", pending, " pending orders active");

    return pending;
}

//+------------------------------------------------------------------+
//| Full reconciliation entry point (called from OnInit)               |
//+------------------------------------------------------------------+
void FullReconciliation()
{
    Print("[NeuroX] ═══════════════════════════════════════════════");
    Print("[NeuroX] RECONCILIATION - Recovering state after restart");
    Print("[NeuroX] ═══════════════════════════════════════════════");

    // 1. Recover open positions into tracking arrays
    int positions = ReconcileOpenPositions();

    // 2. Check for pending orders
    int pending = ReconcilePendingOrders();

    // 3. Reset daily stats fresh (do not recover prior session stats)
    InitDailyStats();

    // 4. Summary
    Print("[NeuroX] ═══════════════════════════════════════════════");
    Print("[NeuroX] Reconciliation summary:");
    Print("[NeuroX]   Open positions tracked: ", positions);
    Print("[NeuroX]   Pending orders:         ", pending);
    Print("[NeuroX]   Daily stats:            RESET (fresh session)");
    Print("[NeuroX] ═══════════════════════════════════════════════");
}

#endif // NEUROX_RECONCILIATION_MQH
