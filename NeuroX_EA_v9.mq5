//+------------------------------------------------------------------+
//|                                              NeuroX_EA_v9.mq5      |
//|                              NeuroX v9.0 - AI Trading System       |
//|                                                                    |
//|  Complete rewrite: modular architecture, named pipe bridge,        |
//|  position reconciliation, daily P&L tracking, all parameters       |
//|  configurable.                                                     |
//|                                                                    |
//|  Architecture:                                                     |
//|    NeuroX_Types.mqh          - Shared types, structs, globals      |
//|    NeuroX_Execution.mqh      - Order execution engine              |
//|    NeuroX_Position.mqh       - Position management & trailing      |
//|    NeuroX_Dashboard.mqh      - On-chart professional dashboard     |
//|    NeuroX_Pipe.mqh           - High-speed bridge (pipe + CSV)      |
//|    NeuroX_Reconciliation.mqh - State recovery on restart           |
//|                                                                    |
//|  Communication:                                                    |
//|    BRIDGE_CSV  - Legacy CSV file bridge (original)                 |
//|    BRIDGE_PIPE - Flag-based shared memory (<1ms latency)           |
//|    BRIDGE_AUTO - Try pipe first, auto-fallback to CSV              |
//+------------------------------------------------------------------+
#property copyright "NeuroX"
#property version   "9.40"
#property description "NeuroX v9.0 - Pure Momentum HF Scalper"
#property description "Named Pipe Bridge | Position Reconciliation | Daily P&L"
#property strict

//+------------------------------------------------------------------+
//| Include Modules (MUST be before inputs that use custom enums)      |
//| Files are in MQL5/Include/NeuroX/ folder                           |
//+------------------------------------------------------------------+
#include <NeuroX\NeuroX_Types.mqh>
#include <NeuroX\NeuroX_Position.mqh>
#include <NeuroX\NeuroX_Execution.mqh>
#include <NeuroX\NeuroX_Pipe.mqh>
#include <NeuroX\NeuroX_Reconciliation.mqh>
#include <NeuroX\NeuroX_Dashboard.mqh>


//+------------------------------------------------------------------+
//| Input Parameters - ALL configurable (no magic numbers)             |
//+------------------------------------------------------------------+

// ═══════════════════════════════════════════════════════════════════
// BRIDGE COMMUNICATION
// ═══════════════════════════════════════════════════════════════════
input ENUM_BRIDGE_MODE InpBridgeMode = BRIDGE_AUTO;           // Bridge mode (Auto/Pipe/CSV)
input string   InpSignalFile       = "neurox_v9_signal.csv";       // [CSV] Signal file name
input string   InpConfirmFile      = "neurox_v9_confirm.csv";      // [CSV] Confirmation file name
input string   InpExitFile         = "neurox_v9_exit.csv";         // [CSV] Exit signal file name
input string   InpHeartbeatFile    = "neurox_v9_heartbeat.txt";    // [CSV] Heartbeat file name
input string   InpStatusFile       = "neurox_v9_status.txt";       // [CSV] Status file name
input string   InpIntelligenceFile = "neurox_v9_intelligence.txt"; // Intelligence file name
input int      InpPipeReconnectInterval = 5;                  // [Pipe] Reconnection interval (sec)
input int      InpMaxSignalAge     = 30;                      // Max signal age (seconds)

// ═══════════════════════════════════════════════════════════════════
// TRADE EXECUTION
// ═══════════════════════════════════════════════════════════════════
input int      InpMagicNumber      = 20250629;  // Magic number for orders (unique to v9)
input int      InpSlippage         = 5;         // Slippage in points (tight HF fills)
input int      InpMaxOpenTrades    = 5;         // Max simultaneous positions
input double   InpMaxLotSize       = 1.0;       // Maximum lot size
input double   InpMinLotSize       = 0.05;      // Minimum lot size
input double   InpDefaultLotSize   = 0.10;      // Default lot (if signal=0)
input double   InpMinConfidence    = 0.10;      // Minimum confidence to trade
input double   InpFixedSL          = 2.00;      // Fixed SL in $ (0=use signal)
input int      InpEmaFastPeriod    = 9;         // EMA Fast period (crossover)
input int      InpEmaSlowPeriod    = 15;        // EMA Slow period (crossover)
input double   InpEmaMaxDistance   = 1.00;      // EMA max distance ($) - block trades when overextended
input int      InpMinADX           = 20;        // Min ADX to allow trading (below = ranging/choppy)
input ENUM_TIMEFRAMES InpADXTimeframe = PERIOD_M5; // ADX timeframe (M5 recommended)
input double   InpDynamicTPThreshold = 9990.0;  // TP pips threshold for dynamic mode
input int      InpLimitTimeout     = 30;        // Limit order timeout (seconds)
input double   InpPartialT2Offset  = 0.30;      // Partial entry T2 offset ($)
input double   InpPartialT3Offset  = 0.60;      // Partial entry T3 offset ($)


// ═══════════════════════════════════════════════════════════════════
// TRAILING STOP PARAMETERS
// ═══════════════════════════════════════════════════════════════════
input double   InpBreakevenProfit  = 0.30;      // Profit $ to move SL to breakeven
input double   InpBEProfitBuffer   = 0.05;      // Extra $ above entry for BE SL
input double   InpTrailStart       = 0.60;      // Profit $ to start trailing
input double   InpTrailTight       = 1.20;      // Profit $ for tight trail
input double   InpTrailVeryTight   = 2.00;      // Profit $ for very tight trail
input double   InpTrailDist1       = 0.40;      // Trail distance Tier 2 ($)
input double   InpTrailDist2       = 0.25;      // Trail distance Tier 3 ($)
input double   InpTrailDist3       = 0.15;      // Trail distance Tier 4 ($)

// ═══════════════════════════════════════════════════════════════════
// POSITION MANAGEMENT
// ═══════════════════════════════════════════════════════════════════
input int      InpMomentumLookback = 30;        // Momentum lookback (seconds)
input int      InpMaxHoldNoProfit  = 120;       // Max hold without profit (sec)
input double   InpMinProfitTarget  = 1.00;      // Min profit $ to keep position
input double   InpMomentumReverse  = 0.50;      // $ reversal to close on fade
input double   InpEmergencyLossLimit = 50.0;    // Emergency close-all loss ($)

// ═══════════════════════════════════════════════════════════════════
// DASHBOARD
// ═══════════════════════════════════════════════════════════════════
input bool     InpShowDashboard    = true;      // Show on-chart dashboard
input int      InpDashboardScale   = 110;       // Dashboard scale % (50-200)

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
    // Configure trade object
    g_trade.SetExpertMagicNumber(InpMagicNumber);
    g_trade.SetDeviationInPoints(InpSlippage);
    g_trade.SetTypeFilling(ORDER_FILLING_FOK);

    // Set up 100ms timer (backup signal reader + heartbeat)
    EventSetMillisecondTimer(100);

    // Initialize pipe bridge
    PipeInit();

    // RECONCILIATION: Recover state after restart
    FullReconciliation();

    g_status = "Ready - v" + NEUROX_VERSION + " | " +
               EnumToString(InpBridgeMode);

    Print("[NeuroX] ══════════════════════════════════════════");
    Print("[NeuroX] EA v", NEUROX_VERSION, " initialized");
    Print("[NeuroX] Magic=", InpMagicNumber,
          " Bridge=", EnumToString(InpBridgeMode));
    Print("[NeuroX] Min confidence=", InpMinConfidence,
          " Max trades=", InpMaxOpenTrades);
    Print("[NeuroX] SL=$", InpFixedSL,
          " Emergency=$", InpEmergencyLossLimit);
    Print("[NeuroX] Trail: BE=$", InpBreakevenProfit,
          " T2=$", InpTrailDist1,
          " T3=$", InpTrailDist2,
          " T4=$", InpTrailDist3);
    Print("[NeuroX] Partial entry offsets: T2=$", InpPartialT2Offset,
          " T3=$", InpPartialT3Offset);
    Print("[NeuroX] ══════════════════════════════════════════");

    return INIT_SUCCEEDED;
}


//+------------------------------------------------------------------+
//| Expert deinitialization function                                    |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    RemoveDashboard();
    PipeDeinit();

    Print("[NeuroX] EA removed. Reason=", reason,
          " Trades executed=", g_tradesExecuted,
          " Daily P&L=$", DoubleToString(g_dailyStats.realized_pnl, 2));
}

//+------------------------------------------------------------------+
//| Timer function - 100ms interval                                    |
//| Safety net for signal reading + periodic maintenance               |
//+------------------------------------------------------------------+
void OnTimer()
{
    // Day rollover check (reset daily stats at midnight)
    CheckDayRollover();

    // Read signal (unified: pipe or CSV based on mode)
    if(ReadSignal())
    {
        g_signalsRead++;
        if(ValidateSignal())
            ExecuteSignal();
    }

    // NOTE: v9 has no Python-side brain settings writer. This call is a
    // no-op (file will not exist) but is retained for forward-compatibility.
    ReadBrainSettings();

    // Process exit signals from Smart Exit Manager
    ProcessExitSignalsUnified();

    // Read Python bridge status
    ReadStatusUnified();

    // Read intelligence file (regime, filters, decision)
    ReadIntelligenceFile();

    // Update heartbeat age (cached for dashboard)
    UpdateHeartbeatAge();

    // Pipe reconnection attempt (rate-limited internally)
    PipeReconnect();

    // Update dashboard (throttled to 500ms)
    if(InpShowDashboard)
    {
        static uint lastDashUpdate = 0;
        uint now = GetTickCount();
        if(now - lastDashUpdate >= 500)
        {
            UpdateDashboard();
            lastDashUpdate = now;
        }
    }
}


//+------------------------------------------------------------------+
//| Expert tick function - minimal and fast for HF execution           |
//+------------------------------------------------------------------+
void OnTick()
{
    // Read signal on every tick for instant execution (no rate limiting)
    if(ReadSignal())
    {
        g_signalsRead++;
        if(ValidateSignal())
            ExecuteSignal();
    }

    // Tick-by-tick position management (trailing stops)
    ManageOpenPositions();

    // Write tick price for Python trailing stop manager
    WriteMT5Heartbeat();
}

//+------------------------------------------------------------------+
//| Trade transaction handler - detects expired limit orders           |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
    // Only care about order removal (pending order expired/deleted)
    if(trans.type != TRADE_TRANSACTION_ORDER_DELETE)
        return;

    ulong orderTicket = trans.order;
    if(orderTicket == 0)
        return;

    // Delegate to execution module
    HandleExpiredLimitOrder(orderTicket);
}
//+------------------------------------------------------------------+
