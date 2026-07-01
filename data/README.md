# Data Directory - MT5 OHLC Export Format

## Required CSV Format

The backtester expects M1 (1-minute) OHLC bar data for XAUUSD exported from MetaTrader 5.

### Supported Column Formats

The parser auto-detects common MT5 export formats:

**Format A (Standard MT5 Export):**
```
Date,Time,Open,High,Low,Close,Tick Volume,Volume,Spread
2024.01.02,00:00,2063.42,2063.98,2063.10,2063.75,485,0,16
2024.01.02,00:01,2063.75,2064.12,2063.55,2063.90,312,0,16
```

**Format B (Tab-separated):**
```
Date	Time	Open	High	Low	Close	Tick Volume	Volume	Spread
2024.01.02	00:00	2063.42	2063.98	2063.10	2063.75	485	0	16
```

**Format C (Combined DateTime column):**
```
DateTime,Open,High,Low,Close,TickVolume,Volume,Spread
2024.01.02 00:00,2063.42,2063.98,2063.10,2063.75,485,0,16
```

### Column Descriptions

| Column | Description |
|--------|-------------|
| Date | Bar date (YYYY.MM.DD or YYYY-MM-DD or YYYY/MM/DD) |
| Time | Bar time (HH:MM or HH:MM:SS) |
| Open | Opening price |
| High | Highest price during the bar |
| Low | Lowest price during the bar |
| Close | Closing price |
| Tick Volume | Number of ticks in the bar (optional) |
| Volume | Real volume (optional, often 0 for forex/metals) |
| Spread | Spread in points (optional, defaults to 16 if missing) |

### Notes

- Spread is in points. For XAUUSD, 16 points = $0.16.
- If the Spread column is missing, the backtester assumes 16 points (0.16).
- The backtester uses 0.01 lot size, so $1 price move = $1 profit.
- Commission is $0 for all calculations.

## How to Export from MetaTrader 5

1. Open MetaTrader 5
2. Go to **File** > **Open Data Folder**
3. Navigate to the Terminal's history directory, or use the built-in export:
   - Open the **Symbols** window (Ctrl+U or View > Symbols)
   - Select **XAUUSD**
   - Go to the **Bars** tab
   - Set timeframe to **M1**
   - Select the date range you want
   - Click **Export Bars** and save as CSV

### Alternative Method (History Center):

1. Open **Tools** > **History Center** (or press F2)
2. Navigate to **XAUUSD** > **M1**
3. Select the date range
4. Click **Export** and save as CSV

### Alternative Method (Chart Export):

1. Open an M1 chart of XAUUSD
2. Load the desired history (scroll back or use Navigator)
3. Right-click on the chart
4. Select **Save** (or use File > Save As)
5. Choose CSV format

## File Naming Convention

Recommended naming: `XAUUSD_M1.csv` or `XAUUSD_M1_YYYYMMDD_YYYYMMDD.csv`

Example: `XAUUSD_M1_20240101_20240630.csv`

Place exported CSV files in this `data/` directory, then run:

```bash
python backtest.py data/XAUUSD_M1.csv
```
