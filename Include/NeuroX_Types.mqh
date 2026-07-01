//+------------------------------------------------------------------+
//|                                              NeuroX_Types.mqh      |
//|                              NeuroX v9.0 - Shared Types & Structs  |
//|                                                                    |
//|  Shared structures, enums, constants, and global state used        |
//|  across all NeuroX include files.                                  |
//+------------------------------------------------------------------+
#ifndef NEUROX_TYPES_MQH
#define NEUROX_TYPES_MQH

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>

//+------------------------------------------------------------------+
//| Version & Build Info                                                |
//+------------------------------------------------------------------+
#define NEUROX_VERSION        "9.40"
#define NEUROX_BUILD          "20250703"
#define NEUROX_NAME           "NeuroX"

//+------------------------------------------------------------------+
//| Position Tracking Constants                                        |
//+------------------------------------------------------------------+
#define MAX_TRACKED_POSITIONS 100

//+------------------------------------------------------------------+
//| Named Pipe Constants                                               |
//+------------------------------------------------------------------+
#define PIPE_BUFFER_SIZE      4096
#define PIPE_SIGNAL_NAME      "\\\\.\\pipe\\neurox_signal"
#define PIPE_CONFIRM_NAME     "\\\\.\\pipe\\neurox_confirm"
#define PIPE_EXIT_NAME        "\\\\.\\pipe\\neurox_exit"
#define PIPE_HEARTBEAT_NAME   "\\\\.\\pipe\\neurox_heartbeat"
#define PIPE_BRAIN_NAME       "\\\\.\\pipe\\neurox_brain"
#define PIPE_STATUS_NAME      "\\\\.\\pipe\\neurox_status"

//+------------------------------------------------------------------+
//| Enumerations                                                       |
//+------------------------------------------------------------------+
enum ENUM_ENTRY_TYPE
{
    ENTRY_MARKET = 0,       // Standard market order
    ENTRY_LIMIT = 1,        // Limit order with timeout
    ENTRY_PARTIAL = 2       // Partial entry (50/25/25 split)
};

enum ENUM_BRIDGE_MODE
{
    BRIDGE_CSV = 0,         // Legacy CSV file bridge
    BRIDGE_PIPE = 1,        // Named pipe (recommended)
    BRIDGE_AUTO = 2         // Try pipe first, fallback to CSV
};

enum ENUM_TRAIL_TIER
{
    TRAIL_INIT = 0,         // Initial SL (no trailing yet)
    TRAIL_BREAKEVEN = 1,    // Breakeven + buffer
    TRAIL_STANDARD = 2,     // Standard trail distance
    TRAIL_TIGHT = 3,        // Tight trail distance
    TRAIL_VERY_TIGHT = 4    // Very tight trail distance
};

enum ENUM_BRAIN_STATE
{
    BRAIN_ACTIVE = 1,       // Trading allowed
    BRAIN_PAUSED = 0        // Trading paused (drawdown/poor session)
};

enum ENUM_STATUS_TYPE
{
    STATUS_OK = 0,
    STATUS_NEWS = 1,
    STATUS_WARNING = 2,
    STATUS_ERROR = 3
};

//+------------------------------------------------------------------+
//| Signal Structure (binary format for named pipe)                    |
//+------------------------------------------------------------------+
struct SignalData
{
    datetime   timestamp;       // Signal generation time
    char       symbol[16];      // Trading symbol (e.g., "XAUUSD")
    char       action[8];       // "BUY", "SELL", "HOLD"
    double     confidence;      // Model confidence 0.0 - 1.0
    double     sl_pips;         // Stop loss in pips
    double     tp_pips;         // Take profit in pips
    double     lot_size;        // Calculated lot size
    char       model_name[32];  // Model that generated signal
    char       regime[16];      // Market regime
    int        entry_type;      // ENUM_ENTRY_TYPE value
    double     limit_price;     // Limit price (0 = market)
    int        checksum;        // Simple validation checksum
};

//+------------------------------------------------------------------+
//| Confirmation Structure (binary format for named pipe)              |
//+------------------------------------------------------------------+
struct ConfirmData
{
    datetime   timestamp;       // Execution time
    ulong      ticket;          // Position ticket
    char       symbol[16];      // Symbol
    char       action[8];       // "BUY" or "SELL"
    double     lot_size;        // Executed lot size
    double     open_price;      // Fill price
    double     sl;              // Stop loss price
    double     tp;              // Take profit price
    char       status[16];      // "FILLED", "FAILED", "CLOSED", "LIMIT_PLACED"
    double     profit;          // P&L (for closed trades)
    double     slippage;        // Slippage in price units
    int        checksum;        // Simple validation checksum
};

//+------------------------------------------------------------------+
//| Exit Signal Structure                                              |
//+------------------------------------------------------------------+
struct ExitSignalData
{
    datetime   timestamp;
    ulong      ticket;          // Position ticket to manage
    char       action[16];      // "CLOSE_FULL", "CLOSE_PARTIAL", "MODIFY_SL"
    double     lot_pct;         // Percentage to close (0.0 - 1.0)
    double     new_sl;          // New SL price (for MODIFY_SL)
    char       reason[64];      // Human-readable reason
    int        checksum;
};

//+------------------------------------------------------------------+
//| Brain Settings Structure                                           |
//+------------------------------------------------------------------+
struct BrainSettings
{
    double     sl_dollars;      // Brain-computed SL (0 = use input)
    double     min_confidence;  // Brain min confidence threshold
    double     lot_multiplier;  // Brain lot size multiplier
    double     be_profit;       // Brain breakeven profit threshold
    double     trail_start;     // Brain trail start threshold
    int        session_active;  // 1 = active, 0 = paused
    int        checksum;
};

//+------------------------------------------------------------------+
//| Position Tracking Structure                                        |
//+------------------------------------------------------------------+
struct TrackedPosition
{
    ulong      ticket;          // Position ticket
    datetime   entry_time;      // When position was opened
    double     entry_price;     // Entry price
    double     volume;          // Position volume
    bool       active;          // Is this slot in use?
};

//+------------------------------------------------------------------+
//| Daily Performance Statistics                                        |
//+------------------------------------------------------------------+
struct DailyStats
{
    datetime   date;            // Current trading day
    double     starting_equity; // Equity at start of day
    double     realized_pnl;   // Total realized P&L today
    int        trades_total;    // Total trades today
    int        trades_won;      // Winning trades today
    int        trades_lost;     // Losing trades today
    double     largest_win;     // Biggest single win
    double     largest_loss;    // Biggest single loss
    double     gross_profit;    // Sum of all wins
    double     gross_loss;      // Sum of all losses (positive value)
    int        consecutive_wins;  // Current win streak
    int        consecutive_losses; // Current loss streak
    int        max_consecutive_wins;  // Best streak today
    int        max_consecutive_losses; // Worst streak today
};

//+------------------------------------------------------------------+
//| Global State Container                                             |
//+------------------------------------------------------------------+
// Trade objects
CTrade         g_trade;
CPositionInfo  g_position;
CAccountInfo   g_account;

// Last signal data
string         g_lastAction     = "HOLD";
double         g_lastConfidence = 0.0;
double         g_lastSLPips     = 0.0;
double         g_lastTPPips     = 0.0;
double         g_lastLotSize    = 0.0;
string         g_lastModel      = "";
string         g_lastRegime     = "";
ENUM_ENTRY_TYPE g_lastEntryType = ENTRY_MARKET;
double         g_lastLimitPrice = 0.0;
datetime       g_lastSignalTime = 0;
int            g_signalsRead    = 0;
int            g_tradesExecuted = 0;
string         g_status         = "Initializing...";

// Python bridge status
ENUM_STATUS_TYPE g_statusType   = STATUS_OK;
string         g_newsWarning    = "";

// Intelligence state (from Python intelligence file)
string         g_intelRegime       = "";
double         g_intelATR          = 0.0;
bool           g_intelATRPass      = false;
double         g_intelTickPct      = 0.0;
string         g_intelTickDir      = "";
int            g_intelPersistence  = 0;
string         g_intelPersistDir   = "";
string         g_intelStrategy     = "";
string         g_intelDecision     = "";
string         g_intelReason       = "";
string         g_intelEmaTrend     = "";

// Duplicate signal execution guard
datetime       g_lastExecutedSignalTime = 0;

// Emergency close cooldown
datetime       g_lastEmergencyClose = 0;

// Brain settings (overrides input parameters dynamically)
double         g_brain_sl           = 0;
double         g_brain_min_conf     = 0;
double         g_brain_lot_mult     = 1.0;
double         g_brain_be_profit    = 0;
double         g_brain_trail_start  = 0;
int            g_brain_session_active = 1;
datetime       g_brain_last_read    = 0;

// Python heartbeat age (cached by OnTimer)
int            g_pyHeartbeatAge     = -1;

// Position tracking arrays
TrackedPosition g_tracked[MAX_TRACKED_POSITIONS];
int            g_trackedCount = 0;

// Momentum tracking
double         g_momentumPrice = 0.0;
datetime       g_momentumTime  = 0;

// Trailing status for dashboard
string         g_trailStatus   = "No positions";

// Slippage tracking
double         g_lastRequestedPrice = 0.0;

// Daily performance stats
DailyStats     g_dailyStats;

// Named pipe connection state
bool           g_pipeConnected = false;
datetime       g_pipeLastAttempt = 0;

// Current ADX value (updated from WriteMT5Heartbeat)
double         g_currentADX = 0.0;

//+------------------------------------------------------------------+
//| Utility: Compute simple checksum for struct validation             |
//+------------------------------------------------------------------+
int ComputeChecksum(const uchar &data[], int length)
{
    int sum = 0;
    for(int i = 0; i < length; i++)
        sum += data[i] * (i + 1);
    return sum & 0x7FFFFFFF;
}

//+------------------------------------------------------------------+
//| Utility: Convert string to ENUM_ENTRY_TYPE                         |
//+------------------------------------------------------------------+
ENUM_ENTRY_TYPE StringToEntryType(string entryStr)
{
    if(entryStr == "LIMIT")          return ENTRY_LIMIT;
    if(entryStr == "PARTIAL_ENTRY")  return ENTRY_PARTIAL;
    return ENTRY_MARKET;
}

//+------------------------------------------------------------------+
//| Utility: Convert ENUM_ENTRY_TYPE to string                         |
//+------------------------------------------------------------------+
string EntryTypeToString(ENUM_ENTRY_TYPE type)
{
    switch(type)
    {
        case ENTRY_LIMIT:   return "LIMIT";
        case ENTRY_PARTIAL: return "PARTIAL_ENTRY";
        default:            return "MARKET";
    }
}

#endif // NEUROX_TYPES_MQH
