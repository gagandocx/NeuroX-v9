# NeuroX v9.0 - Pure Momentum HF Scalper

Stripped-down high-frequency momentum scalper for XAUUSD. No models, no ensemble, no ML - just pure momentum direction detection from M1 candles with immediate signal execution and 4-tier trailing stop management.

## Architecture

- **Python side**: Fetch M1 data -> compute momentum direction -> fire signal -> manage trailing stop
- **EA side**: Optimized execution engine from v8 (OnTick + 100ms timer, 5pt slippage, progressive trailing)
- **Bridge**: Flag-based shared memory files in MT5 Common Files directory

## Files

| File | Purpose |
|------|---------|
| `main.py` | Main loop (~100 lines): fetch, compute, fire, trail |
| `momentum.py` | Adaptive momentum computation (ATR-based lookback) |
| `trailing_stop.py` | 4-tier trailing stop daemon (100ms checks) |
| `bridge.py` | Signal/exit writing to MT5 Common Files |
| `config.py` | All configuration in one place |
| `NeuroX_EA_v9.mq5` | MT5 Expert Advisor |
| `Include/*.mqh` | EA include modules |
| `Start.bat` | One-click compile + launch |
| `tests/` | pytest tests for momentum and bridge |

## Quick Start

```bash
# 1. Clone (into path with spaces is supported)
git clone https://github.com/gagandocx/NeuroX-v9.git "F:\Automation\EA Testing\NeuroX\NeuroX v9.0"

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run (Windows - compiles EA + launches Python)
Start.bat

# 4. Attach EA to XAUUSD M1 chart in MT5
#    Magic number: 20250629
#    All defaults are correct
```

## Configuration

All settings in `config.py`:
- **Symbol**: XAUUSD (GC=F on yfinance)
- **Lot size**: 0.01 (fixed for data collection)
- **Cooldown**: 5 seconds between signals
- **Momentum threshold**: $0.60
- **Adaptive lookback**: 3 bars (high ATR) / 7 bars (low ATR)
- **Trail tiers**: $0.50->BE, $1.00->$0.50, $2.00->$1.50, $3.00->$2.50
- **Max hold**: 120 seconds

## Running Alongside v8

This can run simultaneously with v8 on the same MT5 terminal:
- Different magic numbers (v9: 20250629, v8: 20250628)
- Different signal file prefixes (v9: `neurox_v9_*`, v8: `neurox_v8_*`)
- No interference between the two systems

## Terminal Assignments

- EA runs on: `930119AA53207C8778B41171FBFFB46F`
- Includes copied to: `D0E8209F77C8CF37AD8BF550E51FF075` (MetaEditor)

## What This Is NOT

No torch, no transformers, no scikit-learn, no lightgbm, no ensemble, no regime detection, no HTF bias, no cross-pair correlation, no sentiment, no Kelly sizing, no confidence calibration, no online learning. Just momentum + trailing stop + speed.
