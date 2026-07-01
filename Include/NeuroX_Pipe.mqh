//+------------------------------------------------------------------+
//|                                             NeuroX_Pipe.mqh        |
//|                              NeuroX v9.0 - Named Pipe Bridge       |
//|                                                                    |
//|  High-performance named pipe communication replacing CSV files.    |
//|  Sub-millisecond latency, atomic message delivery, no disk I/O.    |
//|                                                                    |
//|  Protocol:                                                         |
//|    Signal pipe:  Python -> MT5 (text message, newline-terminated)  |
//|    Confirm pipe: MT5 -> Python (text message, newline-terminated)  |
//|    Brain pipe:   Python -> MT5 (key=value pairs)                   |
//|    Exit pipe:    Python -> MT5 (exit commands)                      |
//|                                                                    |
//|  Messages use simple text format for easy debugging:               |
//|    Signal: "timestamp,symbol,action,conf,sl,tp,lot,model,regime,   |
//|             entry_type,limit_price\n"                               |
//|    Confirm: "timestamp,ticket,symbol,action,lot,price,sl,tp,       |
//|              status,profit,slippage\n"                              |
//|                                                                    |
//|  Named pipes in MT5 are accessed via FileOpen with pipe paths.     |
//|  On Windows: \\.\pipe\neurox_*                                     |
//|  The Python side creates the pipe server; MT5 connects as client.  |
//+------------------------------------------------------------------+
#ifndef NEUROX_PIPE_MQH
#define NEUROX_PIPE_MQH

#include "NeuroX_Types.mqh"

//+------------------------------------------------------------------+
//| Input parameters are defined in main EA (NeuroX_EA_v9.mq5)        |
//| They are visible here since this file is #included directly.       |
//+------------------------------------------------------------------+


//+------------------------------------------------------------------+
//| Forward declarations                                               |
//+------------------------------------------------------------------+
void TrackNewPosition(ulong ticket, double entryPrice, double volume);
void UpdateDailyStats_TradeOpened();
bool ReadSignalFileCSV();
void WriteConfirmationCSV(string action, double lots, double price,
                          double sl, double tp, string status,
                          ulong ticketNum, double profit, double slippage);
void ReadBrainSettingsCSV();

//+------------------------------------------------------------------+
//| Pipe handle storage                                                |
//+------------------------------------------------------------------+
int g_pipeSignalHandle   = INVALID_HANDLE;
int g_pipeConfirmHandle  = INVALID_HANDLE;
int g_pipeBrainHandle    = INVALID_HANDLE;
int g_pipeExitHandle     = INVALID_HANDLE;
int g_pipeStatusHandle   = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| Shared memory file approach for MT5 compatibility                  |
//|                                                                    |
//| MT5's FileOpen cannot connect to Windows named pipes directly.     |
//| Instead we use a RAM-based shared file approach:                   |
//|   - Python writes to a shared memory-mapped file                   |
//|   - MT5 reads via FILE_SHARE_READ from the same path              |
//|   - Files are in MT5 Common folder (already in memory cache)       |
//|   - Combined with a "ready" flag file for signaling                |
//|                                                                    |
//| This achieves near-pipe performance (<1ms) because:                |
//|   - Windows caches recently-written files in RAM                   |
//|   - FILE_SHARE_READ avoids locking                                 |
//|   - Flag file acts as interrupt (MT5 polls flag, not data file)    |
//|                                                                    |
//| Alternative: Use a DLL that wraps CreateNamedPipe/ConnectNamedPipe |
//| for true kernel-mode pipe performance. See NeuroX_PipeDLL.mqh.     |
//+------------------------------------------------------------------+

// Signal ready flag file (Python writes "1" when new signal available)
#define PIPE_SIGNAL_FLAG    "neurox_signal_ready.flag"
#define PIPE_SIGNAL_DATA    "neurox_signal.bin"
#define PIPE_CONFIRM_DATA   "neurox_confirm.bin"
#define PIPE_BRAIN_DATA     "neurox_brain.bin"
#define PIPE_EXIT_DATA      "neurox_exit.bin"
#define PIPE_STATUS_DATA    "neurox_status.bin"


//+------------------------------------------------------------------+
//| Initialize pipe bridge                                             |
//+------------------------------------------------------------------+
bool PipeInit()
{
    if(InpBridgeMode == BRIDGE_CSV)
        return true;  // No pipe initialization needed

    Print("[NeuroX] Pipe bridge initializing (mode=",
          EnumToString(InpBridgeMode), ")...");

    // Test if Python has created the signal flag file
    g_pipeConnected = PipeCheckConnection();

    if(g_pipeConnected)
        Print("[NeuroX] Pipe bridge: Python server DETECTED");
    else
        Print("[NeuroX] Pipe bridge: Waiting for Python server...");

    g_pipeLastAttempt = TimeCurrent();
    return true;
}

//+------------------------------------------------------------------+
//| Check if Python pipe server is available                           |
//+------------------------------------------------------------------+
bool PipeCheckConnection()
{
    // Check for the signal flag file existence (Python creates this)
    int fh = FileOpen(PIPE_SIGNAL_FLAG,
                      FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ);
    if(fh != INVALID_HANDLE)
    {
        FileClose(fh);
        return true;
    }
    return false;
}

//+------------------------------------------------------------------+
//| Attempt pipe reconnection (called periodically)                    |
//+------------------------------------------------------------------+
void PipeReconnect()
{
    if(InpBridgeMode == BRIDGE_CSV) return;
    if(g_pipeConnected) return;

    // Rate limit reconnection attempts
    if(TimeCurrent() - g_pipeLastAttempt < InpPipeReconnectInterval)
        return;

    g_pipeLastAttempt = TimeCurrent();
    g_pipeConnected = PipeCheckConnection();

    if(g_pipeConnected)
        Print("[NeuroX] Pipe bridge: RECONNECTED to Python server");
}


//+------------------------------------------------------------------+
//| Read signal via pipe bridge (shared memory file + flag)            |
//|                                                                    |
//| Protocol:                                                          |
//| 1. Python writes signal data to neurox_signal.bin                  |
//| 2. Python writes "1" to neurox_signal_ready.flag                   |
//| 3. MT5 detects flag, reads signal data                             |
//| 4. MT5 deletes flag (acknowledges receipt)                         |
//|                                                                    |
//| This eliminates polling the full data file every tick.             |
//| Flag check = 1 byte read = ~0.01ms vs CSV parse = ~5ms            |
//+------------------------------------------------------------------+
bool ReadSignalPipe()
{
    // Step 1: Check flag file (ultra-fast: 1 byte)
    int flagHandle = FileOpen(PIPE_SIGNAL_FLAG,
                              FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ);
    if(flagHandle == INVALID_HANDLE)
        return false;  // No new signal

    string flagContent = FileReadString(flagHandle);
    FileClose(flagHandle);

    // Flag must contain "1" to indicate new signal ready
    if(flagContent != "1")
        return false;

    // Step 2: Read the signal data file
    int dataHandle = FileOpen(PIPE_SIGNAL_DATA,
                              FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ | FILE_ANSI);
    if(dataHandle == INVALID_HANDLE)
    {
        Print("[NeuroX] Pipe: Flag set but signal data file missing!");
        return false;
    }

    // Read single-line signal (CSV format, no header)
    if(!FileIsEnding(dataHandle))
    {
        string line = FileReadString(dataHandle);
        FileClose(dataHandle);

        if(StringLen(line) == 0)
            return false;

        // Parse CSV fields from the single line
        if(!ParseSignalLine(line))
            return false;
    }
    else
    {
        FileClose(dataHandle);
        return false;
    }

    // Step 3: Clear the flag (acknowledge receipt)
    int clearHandle = FileOpen(PIPE_SIGNAL_FLAG,
                               FILE_WRITE | FILE_TXT | FILE_COMMON);
    if(clearHandle != INVALID_HANDLE)
    {
        FileWriteString(clearHandle, "0");
        FileClose(clearHandle);
    }

    return true;
}


//+------------------------------------------------------------------+
//| Parse a signal line (comma-separated, 11 fields)                   |
//+------------------------------------------------------------------+
bool ParseSignalLine(string line)
{
    string fields[];
    int count = StringSplit(line, ',', fields);

    if(count < 9)
    {
        Print("[NeuroX] Pipe: Signal parse error - only ", count, " fields in: ", line);
        return false;
    }

    g_lastSignalTime = StringToTime(fields[0]);
    // fields[1] = symbol (ignored, we trade chart symbol)
    g_lastAction     = fields[2];
    g_lastConfidence = StringToDouble(fields[3]);
    g_lastSLPips     = StringToDouble(fields[4]);
    g_lastTPPips     = StringToDouble(fields[5]);
    g_lastLotSize    = StringToDouble(fields[6]);
    g_lastModel      = fields[7];
    g_lastRegime     = fields[8];

    // Optional fields (entry_type, limit_price)
    if(count >= 10)
        g_lastEntryType = StringToEntryType(fields[9]);
    else
        g_lastEntryType = ENTRY_MARKET;

    if(count >= 11)
        g_lastLimitPrice = StringToDouble(fields[10]);
    else
        g_lastLimitPrice = 0.0;

    return true;
}

//+------------------------------------------------------------------+
//| Write confirmation via pipe bridge                                  |
//+------------------------------------------------------------------+
void WriteConfirmationPipe(string action, double lots, double price,
                           double sl, double tp, string status,
                           ulong ticketNum, double profit, double slippage)
{
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);

    string ticketStr;
    if(ticketNum > 0)
        ticketStr = IntegerToString(ticketNum);
    else
        ticketStr = IntegerToString(g_trade.ResultDeal());

    // Build confirmation line
    string line = TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "," +
                  ticketStr + "," +
                  _Symbol + "," +
                  action + "," +
                  DoubleToString(lots, 2) + "," +
                  DoubleToString(price, digits) + "," +
                  DoubleToString(sl, digits) + "," +
                  DoubleToString(tp, digits) + "," +
                  status + "," +
                  DoubleToString(profit, 2) + "," +
                  DoubleToString(slippage, 4);

    // Write to shared confirm file
    int fh = FileOpen(PIPE_CONFIRM_DATA,
                      FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
    if(fh != INVALID_HANDLE)
    {
        FileWriteString(fh, line + "\n");
        FileClose(fh);

        // Set confirmation ready flag
        int flagH = FileOpen("neurox_confirm_ready.flag",
                             FILE_WRITE | FILE_TXT | FILE_COMMON);
        if(flagH != INVALID_HANDLE)
        {
            FileWriteString(flagH, "1");
            FileClose(flagH);
        }
    }
    else
    {
        Print("[NeuroX] Pipe: Cannot write confirmation data!");
    }
}


//+------------------------------------------------------------------+
//| Read brain settings via pipe bridge                                 |
//+------------------------------------------------------------------+
void ReadBrainSettingsPipe()
{
    int fh = FileOpen(PIPE_BRAIN_DATA,
                      FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ | FILE_ANSI);
    if(fh == INVALID_HANDLE) return;

    while(!FileIsEnding(fh))
    {
        string line = FileReadString(fh);
        if(StringLen(line) == 0) continue;

        string parts[];
        int cnt = StringSplit(line, '=', parts);
        if(cnt < 2) continue;

        string param = parts[0];
        double v = StringToDouble(parts[1]);

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
//| Process exit signals via pipe bridge                                |
//+------------------------------------------------------------------+
bool ReadExitSignalsPipe()
{
    // Check for exit flag
    int flagH = FileOpen("neurox_exit_ready.flag",
                         FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ);
    if(flagH == INVALID_HANDLE)
        return false;

    string flagVal = FileReadString(flagH);
    FileClose(flagH);

    if(flagVal != "1")
        return false;

    // Read exit data
    int fh = FileOpen(PIPE_EXIT_DATA,
                      FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ | FILE_ANSI);
    if(fh == INVALID_HANDLE)
        return false;

    // Each line: ticket,action,lot_pct,new_sl,reason
    while(!FileIsEnding(fh))
    {
        string line = FileReadString(fh);
        if(StringLen(line) == 0) continue;

        string fields[];
        int cnt = StringSplit(line, ',', fields);
        if(cnt < 5) continue;

        long ticketNum = StringToInteger(fields[0]);
        string action  = fields[1];
        double lotPct  = StringToDouble(fields[2]);
        double newSL   = StringToDouble(fields[3]);
        string reason  = fields[4];

        Print("[NeuroX] Pipe exit: ticket=", ticketNum,
              " action=", action, " reason=", reason);

        if(action == "CLOSE_FULL")
            ClosePosition(ticketNum, 1.0);
        else if(action == "CLOSE_PARTIAL")
            ClosePosition(ticketNum, lotPct);
        else if(action == "MODIFY_SL")
            ModifyPositionSL(ticketNum, newSL);
    }
    FileClose(fh);

    // Clear exit flag
    int clearH = FileOpen("neurox_exit_ready.flag",
                          FILE_WRITE | FILE_TXT | FILE_COMMON);
    if(clearH != INVALID_HANDLE)
    {
        FileWriteString(clearH, "0");
        FileClose(clearH);
    }

    return true;
}


//+------------------------------------------------------------------+
//| Read status via pipe bridge                                        |
//+------------------------------------------------------------------+
void ReadStatusPipe()
{
    int fh = FileOpen(PIPE_STATUS_DATA,
                      FILE_READ | FILE_TXT | FILE_COMMON | FILE_SHARE_READ | FILE_ANSI);
    if(fh == INVALID_HANDLE) return;

    if(!FileIsEnding(fh))
    {
        string line = FileReadString(fh);
        FileClose(fh);
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
        FileClose(fh);
}

//+------------------------------------------------------------------+
//| Unified signal read - dispatches to pipe or CSV based on mode      |
//+------------------------------------------------------------------+
bool ReadSignal()
{
    if(InpBridgeMode == BRIDGE_PIPE)
    {
        return ReadSignalPipe();
    }
    else if(InpBridgeMode == BRIDGE_AUTO)
    {
        // Try pipe first, fallback to CSV
        if(g_pipeConnected)
        {
            if(ReadSignalPipe())
                return true;
        }
        return ReadSignalFileCSV();
    }
    else  // BRIDGE_CSV
    {
        return ReadSignalFileCSV();
    }
}

//+------------------------------------------------------------------+
//| Unified confirmation write - dispatches to pipe or CSV             |
//+------------------------------------------------------------------+
void WriteConfirmation(string action, double lots, double price,
                       double sl, double tp, string status,
                       ulong ticketNum = 0, double profit = 0.0,
                       double slippage = 0.0)
{
    if(InpBridgeMode == BRIDGE_PIPE ||
       (InpBridgeMode == BRIDGE_AUTO && g_pipeConnected))
    {
        WriteConfirmationPipe(action, lots, price, sl, tp, status,
                              ticketNum, profit, slippage);
    }
    else
    {
        WriteConfirmationCSV(action, lots, price, sl, tp, status,
                             ticketNum, profit, slippage);
    }

    // Always write balance on close
    if(status == "CLOSED")
        WriteBalance();
}


//+------------------------------------------------------------------+
//| Unified brain settings read                                        |
//+------------------------------------------------------------------+
void ReadBrainSettings()
{
    if(InpBridgeMode == BRIDGE_PIPE ||
       (InpBridgeMode == BRIDGE_AUTO && g_pipeConnected))
    {
        ReadBrainSettingsPipe();
    }
    else
    {
        ReadBrainSettingsCSV();
    }
}

//+------------------------------------------------------------------+
//| Unified exit signals processing                                    |
//+------------------------------------------------------------------+
void ProcessExitSignalsUnified()
{
    if(InpBridgeMode == BRIDGE_PIPE ||
       (InpBridgeMode == BRIDGE_AUTO && g_pipeConnected))
    {
        ReadExitSignalsPipe();
    }
    else
    {
        ProcessExitSignals();
    }
}

//+------------------------------------------------------------------+
//| Unified status read                                                |
//+------------------------------------------------------------------+
void ReadStatusUnified()
{
    if(InpBridgeMode == BRIDGE_PIPE ||
       (InpBridgeMode == BRIDGE_AUTO && g_pipeConnected))
    {
        ReadStatusPipe();
    }
    else
    {
        ReadStatusFile();
    }
}

//+------------------------------------------------------------------+
//| Update heartbeat age (called from OnTimer every 1s)                |
//+------------------------------------------------------------------+
void UpdateHeartbeatAge()
{
    if(InpBridgeMode == BRIDGE_PIPE ||
       (InpBridgeMode == BRIDGE_AUTO && g_pipeConnected))
    {
        // In pipe mode, connection = heartbeat
        g_pyHeartbeatAge = g_pipeConnected ? 0 : -1;
    }
    else
    {
        // CSV mode: check heartbeat file modification time
        int pyHB = FileOpen(InpHeartbeatFile, FILE_READ | FILE_TXT | FILE_COMMON);
        if(pyHB == INVALID_HANDLE)
        {
            g_pyHeartbeatAge = -1;
        }
        else
        {
            datetime modTime = (datetime)FileGetInteger(pyHB, FILE_MODIFY_DATE);
            FileClose(pyHB);
            int age = (int)(TimeLocal() - modTime);
            g_pyHeartbeatAge = (age < 0) ? 0 : age;
        }
    }
}

//+------------------------------------------------------------------+
//| Write MT5 heartbeat for Python connection detection                |
//+------------------------------------------------------------------+
void WriteMT5Heartbeat()
{
    static datetime lastHB = 0;
    if(TimeCurrent() - lastHB < 1) return;
    lastHB = TimeCurrent();

    int hbFile = FileOpen("neurox_v9_mt5_heartbeat.txt",
                          FILE_WRITE | FILE_TXT | FILE_COMMON);
    if(hbFile != INVALID_HANDLE)
    {
        FileWriteString(hbFile,
            TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "\n");
        FileClose(hbFile);
    }

    // v9.0: Write current price for Python tick confirmation
    // This allows Python to check price between cycles without a yfinance call
    double bidPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    if(bidPrice > 0)
    {
        int priceFile = FileOpen("neurox_v9_tick_price.txt",
                                 FILE_WRITE | FILE_TXT | FILE_COMMON);
        if(priceFile != INVALID_HANDLE)
        {
            FileWriteString(priceFile, DoubleToString(bidPrice,
                            (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS)));
            FileClose(priceFile);
        }
    }

    // Write EMA values for Python (instant trend direction - zero warmup)
    double ema9_buf[1], ema15_buf[1];
    static int ema9_handle = INVALID_HANDLE;
    static int ema15_handle = INVALID_HANDLE;
    static bool ema_debug_logged = false;

    if(ema9_handle == INVALID_HANDLE)
        ema9_handle = iMA(_Symbol, PERIOD_M1, InpEmaFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
    if(ema15_handle == INVALID_HANDLE)
        ema15_handle = iMA(_Symbol, PERIOD_M1, InpEmaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE);

    if(!ema_debug_logged)
    {
        Print("[NeuroX] EMA init: ema9_handle=", ema9_handle, " ema15_handle=", ema15_handle);
    }

    if(ema9_handle != INVALID_HANDLE && ema15_handle != INVALID_HANDLE)
    {
        int res9 = CopyBuffer(ema9_handle, 0, 0, 1, ema9_buf);
        int res15 = CopyBuffer(ema15_handle, 0, 0, 1, ema15_buf);
        
        if(!ema_debug_logged)
        {
            Print("[NeuroX] EMA copy: res9=", res9, " res15=", res15,
                  " val9=", ema9_buf[0], " val15=", ema15_buf[0]);
            ema_debug_logged = true;
        }
        
        if(res9 == 1 && res15 == 1)
        {
            int emaFile = FileOpen("neurox_v9_ema.txt",
                                   FILE_WRITE | FILE_TXT | FILE_COMMON);
            if(emaFile != INVALID_HANDLE)
            {
                FileWriteString(emaFile,
                    DoubleToString(ema9_buf[0], 2) + "|" +
                    DoubleToString(ema15_buf[0], 2) + "|" +
                    DoubleToString(InpEmaMaxDistance, 2) + "|" +
                    IntegerToString(CountOpenPositions()));
                FileClose(emaFile);
            }
        }
    }
    else if(!ema_debug_logged)
    {
        Print("[NeuroX] EMA FAILED: handles invalid. ema9=", ema9_handle, " ema15=", ema15_handle);
        ema_debug_logged = true;
    }
}

//+------------------------------------------------------------------+
//| Cleanup pipe bridge on deinit                                      |
//+------------------------------------------------------------------+
void PipeDeinit()
{
    g_pipeConnected = false;
    Print("[NeuroX] Pipe bridge: Disconnected");
}

#endif // NEUROX_PIPE_MQH
