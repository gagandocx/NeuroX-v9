//+------------------------------------------------------------------+
//|                                         NeuroX_Dashboard.mqh       |
//|                              NeuroX v9.0 - Minimal HF Dashboard    |
//|                                                                    |
//|  Compact on-chart dashboard: momentum, P&L, connection only.       |
//|  Designed for v9 pure momentum scalper - no model/brain/regime.    |
//+------------------------------------------------------------------+
#ifndef NEUROX_DASHBOARD_MQH
#define NEUROX_DASHBOARD_MQH

#include "NeuroX_Types.mqh"

//+------------------------------------------------------------------+
//| Forward declarations from other modules                            |
//+------------------------------------------------------------------+
double CalculateFloatingPL();
int    CountOpenPositions();
double GetDailyWinRate();

//+------------------------------------------------------------------+
//| Dashboard Layout Constants                                         |
//| These are BASE values - multiplied by scale factor at runtime      |
//+------------------------------------------------------------------+
#define DASH_BASE_X          10
#define DASH_BASE_Y          30
#define DASH_BASE_WIDTH      310
#define DASH_BASE_LINE_H     18
#define DASH_BASE_MARGIN_L   20
#define DASH_BASE_VALUE_COL  150
#define DASH_BASE_FONT_SIZE  9
#define DASH_FONT            "Consolas"

//+------------------------------------------------------------------+
//| Scaled layout variables (computed once per UpdateDashboard call)    |
//+------------------------------------------------------------------+
int    DASH_X;
int    DASH_Y;
int    DASH_WIDTH;
int    DASH_LINE_H;
int    DASH_MARGIN_L;
int    DASH_VALUE_COL;
int    DASH_FONT_SIZE;

//+------------------------------------------------------------------+
//| Compute scaled layout values from InpDashboardScale                |
//+------------------------------------------------------------------+
void DashComputeScale()
{
    // Clamp scale to 50-200%
    double scale = MathMax(50, MathMin(200, (double)InpDashboardScale)) / 100.0;

    DASH_X         = (int)(DASH_BASE_X * scale);
    DASH_Y         = (int)(DASH_BASE_Y * scale);
    DASH_WIDTH     = (int)(DASH_BASE_WIDTH * scale);
    DASH_LINE_H    = (int)(DASH_BASE_LINE_H * scale);
    DASH_MARGIN_L  = (int)(DASH_BASE_MARGIN_L * scale);
    DASH_VALUE_COL = (int)(DASH_BASE_VALUE_COL * scale);
    DASH_FONT_SIZE = (int)(DASH_BASE_FONT_SIZE * scale);

    // Ensure minimums
    if(DASH_LINE_H < 10) DASH_LINE_H = 10;
    if(DASH_FONT_SIZE < 6) DASH_FONT_SIZE = 6;
    if(DASH_WIDTH < 200) DASH_WIDTH = 200;
}

//+------------------------------------------------------------------+
//| Color Scheme                                                       |
//+------------------------------------------------------------------+
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
//| Create or update a label object                                    |
//+------------------------------------------------------------------+
void DashLabel(string name, int x, int y, string text, color clr,
               int fontSize = -1, string font = DASH_FONT)
{
    // Use scaled font size if not explicitly provided
    if(fontSize < 0) fontSize = DASH_FONT_SIZE;

    string objName = "NX_" + name;
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
    ObjectSetString(0, objName, OBJPROP_FONT, font);
}

//+------------------------------------------------------------------+
//| Create or update background panel                                  |
//+------------------------------------------------------------------+
void DashBackground(string name, int x, int y, int width, int height, color bgColor)
{
    string objName = "NX_" + name;
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
//| Draw section separator line                                        |
//+------------------------------------------------------------------+
void DashSeparator(int &y, string label, color clr = CLR_HEADER)
{
    y += 4;
    DashLabel("sep_" + label, DASH_X + DASH_MARGIN_L, y,
              "--- " + label + " ---", clr, DASH_FONT_SIZE - 1);
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
//| Main dashboard update - called every tick/timer                    |
//+------------------------------------------------------------------+
void UpdateDashboard()
{
    if(!InpShowDashboard) return;

    // Compute scaled layout from InpDashboardScale input
    DashComputeScale();

    int y = DASH_Y + 10;

    // Background panel (sized dynamically at end)
    DashBackground("bg", DASH_X, DASH_Y, DASH_WIDTH, 400, CLR_BG_PANEL);

    // ═══════════════════════════════════════════
    // --- HEADER ---
    // ═══════════════════════════════════════════
    // Bitmap logo
    string logoName = "NX_logo_bmp";
    if(ObjectFind(0, logoName) < 0)
    {
        ObjectCreate(0, logoName, OBJ_BITMAP_LABEL, 0, 0, 0);
        ObjectSetString(0, logoName, OBJPROP_BMPFILE, "\\Images\\neurox_logo.bmp");
        ObjectSetInteger(0, logoName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
        ObjectSetInteger(0, logoName, OBJPROP_SELECTABLE, false);
        ObjectSetInteger(0, logoName, OBJPROP_HIDDEN, true);
        ObjectSetInteger(0, logoName, OBJPROP_BACK, false);
    }
    ObjectSetInteger(0, logoName, OBJPROP_XDISTANCE, DASH_X + DASH_MARGIN_L);
    ObjectSetInteger(0, logoName, OBJPROP_YDISTANCE, y);
    y += 62;

    DashLabel("subtitle", DASH_X + DASH_MARGIN_L, y,
              "Pure Momentum HF Scalper v" + NEUROX_VERSION, CLR_TITLE, DASH_FONT_SIZE);
    y += DASH_LINE_H + 4;

    // ═══════════════════════════════════════════
    // --- CONNECTION ---
    // ═══════════════════════════════════════════
    DashSeparator(y, "CONNECTION");

    // Python Bridge status
    string pyConnStr;
    color  pyConnClr;
    if(g_pyHeartbeatAge >= 0 && g_pyHeartbeatAge <= 3)
        { pyConnStr = "LIVE";      pyConnClr = CLR_POSITIVE; }
    else
        { pyConnStr = "OFFLINE";   pyConnClr = CLR_NEGATIVE; }
    DashRow(y, "conn_py", "Python Bridge:", pyConnStr, pyConnClr);

    // Named Pipe status
    if(InpBridgeMode != BRIDGE_CSV)
    {
        string pipeStr = g_pipeConnected ? "CONNECTED" : "WAITING";
        color pipeClr = g_pipeConnected ? CLR_POSITIVE : clrYellow;
        DashRow(y, "conn_pipe", "Named Pipe:", pipeStr, pipeClr);
    }
    y += 4;

    // ═══════════════════════════════════════════
    // --- PRICE ---
    // ═══════════════════════════════════════════
    DashSeparator(y, "PRICE");

    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    DashRow(y, "price_bid", "Bid:", DoubleToString(bid, digits));

    double spread = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
    string spreadStatus = "";
    color  spreadClr = CLR_NEUTRAL;
    if(spread < 10)
    {
        spreadStatus = "TIGHT";
        spreadClr = CLR_POSITIVE;
    }
    else if(spread <= 20)
    {
        spreadStatus = "OK";
        spreadClr = CLR_NEUTRAL;
    }
    else
    {
        spreadStatus = "WIDE";
        spreadClr = CLR_NEGATIVE;
    }
    DashRow(y, "price_sprd", "Spread:", DoubleToString(spread, 0) + " pts " + spreadStatus, spreadClr);
    y += 4;

    // ═══════════════════════════════════════════
    // --- EMA TREND ---
    // ═══════════════════════════════════════════
    DashSeparator(y, "EMA TREND");

    // EMA Trend label (primary indicator)
    string emaStr = g_intelEmaTrend;
    color emaClr = CLR_NEUTRAL;
    if(StringFind(emaStr, "BUY") >= 0)       emaClr = CLR_POSITIVE;
    else if(StringFind(emaStr, "SELL") >= 0) emaClr = CLR_NEGATIVE;
    else if(emaStr == "WARMUP")              emaClr = clrYellow;
    if(StringLen(emaStr) == 0) emaStr = "---";
    DashRow(y, "int_ema", "EMA Signal:", emaStr, emaClr);

    // Decision (override with STALE if Python offline)
    color decClr = CLR_NEUTRAL;
    string decStr = g_intelDecision;
    if(g_pyHeartbeatAge > 3)
    {
        decStr = "STALE";
        decClr = clrGray;
    }
    else if(g_intelDecision == "TRADING")       decClr = CLR_POSITIVE;
    else if(g_intelDecision == "COOLDOWN") decClr = clrYellow;
    else if(g_intelDecision == "WAITING")  decClr = CLR_NEUTRAL;
    if(StringLen(decStr) == 0) decStr = "---";
    DashRow(y, "int_dec", "Decision:", decStr, decClr);

    // ADX Filter status
    string adxStr;
    color adxClr;
    if(g_currentADX >= InpMinADX)
    {
        adxStr = "TRENDING (" + DoubleToString(g_currentADX, 1) + ")";
        adxClr = CLR_POSITIVE;  // green = trading allowed
    }
    else
    {
        adxStr = "RANGING (" + DoubleToString(g_currentADX, 1) + ")";
        adxClr = CLR_NEGATIVE;  // red = trading blocked
    }
    DashRow(y, "int_adx", "ADX Filter:", adxStr, adxClr);

    y += 4;

    // ═══════════════════════════════════════════
    // --- POSITION ---
    // ═══════════════════════════════════════════
    DashSeparator(y, "POSITION");

    int openPos = CountOpenPositions();
    DashRow(y, "pos_cnt", "Open:", IntegerToString(openPos));

    double floatingPL = CalculateFloatingPL();
    color plColor = (floatingPL >= 0) ? CLR_POSITIVE : CLR_NEGATIVE;
    string plSign = (floatingPL >= 0) ? "+" : "";
    DashRow(y, "pos_pl", "Floating P/L:",
            plSign + "$" + DoubleToString(floatingPL, 2), plColor);

    DashRow(y, "pos_trail", "Trail Tier:", g_trailStatus, CLR_ACCENT);
    y += 4;

    // ═══════════════════════════════════════════
    // --- DAILY P&L ---
    // ═══════════════════════════════════════════
    DashSeparator(y, "DAILY P&L");

    // Realized P&L
    color dailyPLClr = (g_dailyStats.realized_pnl >= 0) ? CLR_POSITIVE : CLR_NEGATIVE;
    string dailyPLSign = (g_dailyStats.realized_pnl >= 0) ? "+" : "";
    DashRow(y, "day_pnl", "Realized:",
            dailyPLSign + "$" + DoubleToString(g_dailyStats.realized_pnl, 2), dailyPLClr);

    // Win / Loss count
    DashRow(y, "day_wl", "W / L:",
            IntegerToString(g_dailyStats.trades_won) + " / " +
            IntegerToString(g_dailyStats.trades_lost), CLR_VALUE);

    // Win rate
    double winRate = GetDailyWinRate();
    color wrClr = (winRate >= 60) ? CLR_POSITIVE : (winRate >= 45) ? CLR_VALUE : CLR_NEGATIVE;
    DashRow(y, "day_wr", "Win Rate:", DoubleToString(winRate, 1) + "%", wrClr);
    y += 4;

    // ═══════════════════════════════════════════
    // --- STATUS ---
    // ═══════════════════════════════════════════
    DashSeparator(y, "STATUS");

    // Last signal time
    string sigTimeStr = (g_lastSignalTime > 0)
        ? TimeToString(g_lastSignalTime, TIME_MINUTES | TIME_SECONDS) : "---";
    DashRow(y, "st_sig", "Last Signal:", sigTimeStr);

    // Trades executed today
    DashRow(y, "st_trd", "Trades Today:", IntegerToString(g_tradesExecuted));
    y += DASH_LINE_H;

    // --- Resize background panel to fit content ---
    int finalHeight = y - DASH_Y;
    ObjectSetInteger(0, "NX_bg", OBJPROP_YSIZE, finalHeight);

    ChartRedraw(0);
}

//+------------------------------------------------------------------+
//| Remove all dashboard objects from chart                            |
//+------------------------------------------------------------------+
void RemoveDashboard()
{
    ObjectsDeleteAll(0, "NX_");
    Comment("");
    ChartRedraw(0);
}

#endif // NEUROX_DASHBOARD_MQH
