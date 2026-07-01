#!/usr/bin/env python3
"""
NeuroX v9 Backtester - Simulates full trading logic against M1 OHLC data.

Supports two modes:
  v9.1 - Momentum only (no choppy market filters)
  v9.2 - Full filters (ATR filter, tick consistency, signal persistence,
          dual-mode regime detection + mean reversion)

Usage:
    python backtest.py <csv_file>
    python backtest.py data/XAUUSD_M1.csv
"""

import sys
import os
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

# Add project root to path so we can import momentum
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from momentum import compute_momentum, compute_atr, detect_regime, compute_mean_reversion_signal
from config import Config


# ---------------------------------------------------------------------------
# Constants (from EA trailing stop tiers)
# ---------------------------------------------------------------------------
LOT_SIZE = Config.LOT_SIZE  # 0.01
FIXED_SL = 2.00  # $2.00 fixed stop loss
DEFAULT_SPREAD_POINTS = 16  # 16 points = $0.16 for XAUUSD

# EA Trailing Stop Tiers (from NeuroX_Position.mqh / NeuroX_EA_v9.mq5)
# These values reflect the actual EA implementation and intentionally differ from
# Config.TRAIL_TIERS in config.py, which is stale/unused and has not been updated
# to match the EA's current tier structure.
# (profit_threshold, trail_distance_from_price)
# BE tier is special: SL = entry + spread + buffer
BE_PROFIT_THRESHOLD = 0.30
BE_BUFFER = 0.05
T2_PROFIT_THRESHOLD = 0.60
T2_TRAIL_DISTANCE = 0.40
T3_PROFIT_THRESHOLD = 1.20
T3_TRAIL_DISTANCE = 0.25
T4_PROFIT_THRESHOLD = 2.00
T4_TRAIL_DISTANCE = 0.15


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Position:
    """Represents an open trading position."""
    direction: str  # "BUY" or "SELL"
    entry_price: float
    entry_bar: int
    spread: float  # spread at entry in price terms
    stop_loss: float  # current SL price
    trailing_tier: int  # -1=none, 0=BE, 1=T2, 2=T3, 3=T4
    regime: str  # "trending" or "ranging"


@dataclass
class Trade:
    """Represents a completed trade."""
    direction: str
    entry_price: float
    exit_price: float
    entry_bar: int
    exit_bar: int
    profit: float
    exit_reason: str
    regime: str


@dataclass
class BacktestResult:
    """Holds the results of a backtest run."""
    mode: str
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.profit > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.profit <= 0)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.wins / self.total_trades * 100

    @property
    def total_profit(self) -> float:
        return sum(t.profit for t in self.trades)

    @property
    def gross_profit(self) -> float:
        return sum(t.profit for t in self.trades if t.profit > 0)

    @property
    def gross_loss(self) -> float:
        return sum(t.profit for t in self.trades if t.profit <= 0)

    @property
    def profit_factor(self) -> float:
        if self.gross_loss == 0:
            return float('inf') if self.gross_profit > 0 else 0.0
        return self.gross_profit / abs(self.gross_loss)

    @property
    def max_drawdown(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = 0.0
        max_dd = 0.0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def avg_trade_profit(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.total_profit / self.total_trades

    @property
    def best_trade(self) -> float:
        if not self.trades:
            return 0.0
        return max(t.profit for t in self.trades)

    @property
    def worst_trade(self) -> float:
        if not self.trades:
            return 0.0
        return min(t.profit for t in self.trades)

    @property
    def trending_trades(self) -> int:
        return sum(1 for t in self.trades if t.regime == "trending")

    @property
    def ranging_trades(self) -> int:
        return sum(1 for t in self.trades if t.regime == "ranging")


# ---------------------------------------------------------------------------
# CSV Parser
# ---------------------------------------------------------------------------
def load_csv(filepath: str) -> pd.DataFrame:
    """
    Load M1 OHLC data from a CSV file exported from MT5.

    Auto-detects format: comma or tab separated, various date formats,
    with or without Spread column.

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume, Spread
        Index is sequential integers (bar number).
    """
    # Try comma first, then tab
    for sep in [',', '\t']:
        try:
            df = pd.read_csv(filepath, sep=sep, engine='python')
            if len(df.columns) >= 4:
                break
        except Exception:
            continue
    else:
        raise ValueError(f"Could not parse CSV file: {filepath}")

    # Normalize column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    # Build a normalized lookup: key = lowercase no spaces/underscores, value = original col name
    col_lower = {c.lower().replace(' ', '').replace('_', '').replace('<', '').replace('>', ''): c for c in df.columns}

    # Find source columns for each target. Priority order matters for Volume
    # (prefer 'Tick Volume'/'TickVolume' over raw 'Volume' which is often 0 in MT5)
    def find_col(aliases):
        for alias in aliases:
            if alias in col_lower:
                return col_lower[alias]
        return None

    src_open = find_col(['open'])
    src_high = find_col(['high'])
    src_low = find_col(['low'])
    src_close = find_col(['close'])
    src_volume = find_col(['tickvolume', 'tickvol', 'vol', 'volume'])
    src_spread = find_col(['spread'])

    # Verify required columns
    for name, src in [('Open', src_open), ('High', src_high),
                      ('Low', src_low), ('Close', src_close)]:
        if src is None:
            raise ValueError(
                f"Missing required column '{name}'. "
                f"Available columns: {list(df.columns)}"
            )

    # Build output DataFrame with standard column names
    out = pd.DataFrame()
    out['Open'] = pd.to_numeric(df[src_open], errors='coerce')
    out['High'] = pd.to_numeric(df[src_high], errors='coerce')
    out['Low'] = pd.to_numeric(df[src_low], errors='coerce')
    out['Close'] = pd.to_numeric(df[src_close], errors='coerce')

    if src_volume is not None:
        out['Volume'] = pd.to_numeric(df[src_volume], errors='coerce').fillna(0)
    else:
        out['Volume'] = 0

    if src_spread is not None:
        # Spread in points; convert to price: points * 0.01 for XAUUSD
        out['Spread'] = pd.to_numeric(
            df[src_spread], errors='coerce'
        ).fillna(DEFAULT_SPREAD_POINTS) * 0.01
    else:
        out['Spread'] = DEFAULT_SPREAD_POINTS * 0.01  # $0.16

    # Drop rows with NaN in OHLC
    out = out.dropna(subset=['Open', 'High', 'Low', 'Close']).reset_index(drop=True)

    return out


# ---------------------------------------------------------------------------
# Trailing Stop Logic (simulates EA 4-tier system)
# ---------------------------------------------------------------------------
def compute_trailing_sl(position: Position, current_price: float) -> float:
    """
    Compute the updated trailing stop loss for a position based on EA tiers.

    Only tightens SL, never widens. Returns the new SL price.
    """
    if position.direction == "BUY":
        profit = current_price - position.entry_price
    else:
        profit = position.entry_price - current_price

    new_sl = position.stop_loss
    new_tier = position.trailing_tier

    # T4: profit >= $2.00, trail distance $0.15 from current price
    if profit >= T4_PROFIT_THRESHOLD:
        if position.direction == "BUY":
            candidate_sl = current_price - T4_TRAIL_DISTANCE
        else:
            candidate_sl = current_price + T4_TRAIL_DISTANCE
        new_tier = 3

    # T3: profit >= $1.20, trail distance $0.25 from current price
    elif profit >= T3_PROFIT_THRESHOLD:
        if position.direction == "BUY":
            candidate_sl = current_price - T3_TRAIL_DISTANCE
        else:
            candidate_sl = current_price + T3_TRAIL_DISTANCE
        new_tier = 2

    # T2: profit >= $0.60, trail distance $0.40 from current price
    elif profit >= T2_PROFIT_THRESHOLD:
        if position.direction == "BUY":
            candidate_sl = current_price - T2_TRAIL_DISTANCE
        else:
            candidate_sl = current_price + T2_TRAIL_DISTANCE
        new_tier = 1

    # BE: profit >= $0.30, SL = entry + spread + buffer (BUY) or entry - spread - buffer (SELL)
    elif profit >= BE_PROFIT_THRESHOLD:
        if position.direction == "BUY":
            candidate_sl = position.entry_price + position.spread + BE_BUFFER
        else:
            candidate_sl = position.entry_price - position.spread - BE_BUFFER
        new_tier = 0
    else:
        return new_sl  # No tier reached, keep current SL

    # Only tighten: for BUY, SL can only go up; for SELL, SL can only go down
    if position.direction == "BUY":
        if candidate_sl > new_sl:
            new_sl = candidate_sl
    else:
        if candidate_sl < new_sl:
            new_sl = candidate_sl

    position.trailing_tier = new_tier
    return new_sl


def check_sl_hit(position: Position, bar_high: float, bar_low: float) -> bool:
    """Check if the stop loss was hit during this bar."""
    if position.direction == "BUY":
        return bar_low <= position.stop_loss
    else:  # SELL
        return bar_high >= position.stop_loss


# ---------------------------------------------------------------------------
# Tick Consistency Simulation (from bar data)
# ---------------------------------------------------------------------------
def compute_tick_consistency(closes: np.ndarray, lookback: int) -> float:
    """
    Simulate tick consistency from bar close data.

    Since we only have M1 bars (not ticks), we approximate by looking at
    the directional consistency of recent close-to-close moves.

    Returns:
        Fraction of moves in the dominant direction (0.0 to 1.0).
    """
    if len(closes) < lookback + 1:
        return 0.0

    recent = closes[-(lookback + 1):]
    diffs = np.diff(recent)

    if len(diffs) == 0:
        return 0.0

    ups = np.sum(diffs > 0)
    downs = np.sum(diffs < 0)

    # Return the consistency of the dominant direction
    return max(ups, downs) / len(diffs)


# ---------------------------------------------------------------------------
# Backtester Engine
# ---------------------------------------------------------------------------
class Backtester:
    """
    NeuroX v9 Backtester Engine.

    Simulates the full trading logic bar-by-bar on M1 data.
    """

    def __init__(self, df: pd.DataFrame, mode: str = "v9.2"):
        """
        Args:
            df: DataFrame with Open, High, Low, Close, Volume, Spread columns.
            mode: "v9.1" (momentum only) or "v9.2" (full filters).
        """
        self.df = df
        self.mode = mode
        self.positions: List[Position] = []
        self.trades: List[Trade] = []
        self.equity = 0.0
        self.equity_curve: List[float] = []

        # State tracking
        self.last_trade_bar = -999  # For cooldown
        self.last_signal_direction: Optional[str] = None
        self.last_signal_price: float = 0.0
        self.signal_persistence_count = 0
        self.last_persistent_direction: Optional[str] = None

    def run(self) -> BacktestResult:
        """Run the backtest and return results."""
        n_bars = len(self.df)

        # Need minimum bars for indicators
        min_bars = max(
            Config.MOMENTUM_LOOKBACK + 2,
            Config.MEAN_REVERSION_LOOKBACK,
            Config.REGIME_VARIANCE_RATIO_LOOKBACK + 1,
            Config.TICK_CONSISTENCY_LOOKBACK + 1,
            15 + 1,  # ATR period (14) + 1
        )

        for i in range(min_bars, n_bars):
            bar = self.df.iloc[i]
            bar_high = bar['High']
            bar_low = bar['Low']
            bar_close = bar['Close']
            bar_spread = bar['Spread']

            # Update existing positions (check SL, trailing stops, max hold)
            self._update_positions(i, bar_high, bar_low, bar_close)

            # Generate signal and potentially open new position
            self._process_bar(i, bar_close, bar_spread)

            # Record equity
            self.equity_curve.append(self.equity)

        # Force close any remaining positions at the last bar close
        if len(self.df) > 0:
            last_close = self.df.iloc[-1]['Close']
            last_spread = self.df.iloc[-1]['Spread']
            for pos in list(self.positions):
                self._close_position(pos, last_close, len(self.df) - 1,
                                     last_spread, "end_of_data")
        self.positions.clear()

        result = BacktestResult(mode=self.mode, trades=self.trades,
                                equity_curve=self.equity_curve)
        return result

    def _update_positions(self, bar_idx: int, bar_high: float,
                          bar_low: float, bar_close: float):
        """Update all open positions: check SL hits, trailing stops, max hold."""
        closed = []
        for pos in self.positions:
            # Check max hold (2 bars)
            bars_held = bar_idx - pos.entry_bar
            if bars_held >= 2:  # MAX_HOLD_SECONDS=120 / 60s per bar = 2 bars
                closed.append((pos, bar_close, "max_hold"))
                continue

            # Update trailing stop based on current bar close
            new_sl = compute_trailing_sl(pos, bar_close)
            if pos.direction == "BUY":
                if new_sl > pos.stop_loss:
                    pos.stop_loss = new_sl
            else:
                if new_sl < pos.stop_loss:
                    pos.stop_loss = new_sl

            # Check if SL was hit during this bar
            if check_sl_hit(pos, bar_high, bar_low):
                # Exit at SL price
                closed.append((pos, pos.stop_loss, "stop_loss"))
                continue

        # Process closures
        for pos, exit_price, reason in closed:
            spread = self.df.iloc[bar_idx]['Spread']
            self._close_position(pos, exit_price, bar_idx, spread, reason)
            if pos in self.positions:
                self.positions.remove(pos)

    def _close_position(self, pos: Position, exit_price: float,
                        bar_idx: int, spread: float, reason: str):
        """Close a position and record the trade."""
        half_spread = spread / 2.0

        if pos.direction == "BUY":
            # Entry cost already applied; exit costs half spread
            effective_exit = exit_price - half_spread
            profit = effective_exit - pos.entry_price
        else:
            effective_exit = exit_price + half_spread
            profit = pos.entry_price - effective_exit

        trade = Trade(
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=effective_exit,
            entry_bar=pos.entry_bar,
            exit_bar=bar_idx,
            profit=profit,
            exit_reason=reason,
            regime=pos.regime,
        )
        self.trades.append(trade)
        self.equity += profit

    def _process_bar(self, bar_idx: int, bar_close: float, bar_spread: float):
        """Process a bar for potential trade entry."""
        # Cooldown check: allow max 1 trade per bar
        if bar_idx <= self.last_trade_bar:
            return

        # Get price history up to current bar
        prices_df = self.df.iloc[:bar_idx + 1].copy()
        closes = prices_df['Close'].values

        # For momentum computation, drop Volume column to avoid volume-weighted
        # mode which is designed for live tick data, not M1 bar backtesting.
        # MT5 bar Volume (tick count per bar) has different statistical properties
        # than real-time tick arrival rates, so volume-weighted signals would be
        # misleading in this context.
        momentum_df = prices_df.drop(columns=['Volume', 'Spread'], errors='ignore')

        # Compute ATR
        current_atr, avg_atr = compute_atr(momentum_df, period=14)

        # Detect regime
        regime = detect_regime(momentum_df, current_atr, avg_atr)

        # --- v9.2 filters ---
        if self.mode == "v9.2":
            # ATR filter: skip if ATR < MIN_ATR_THRESHOLD
            if current_atr < Config.MIN_ATR_THRESHOLD:
                return

            # Tick consistency simulation
            consistency = compute_tick_consistency(
                closes, Config.TICK_CONSISTENCY_LOOKBACK
            )

            # Regime-based signal generation
            if regime == "ranging":
                # Mean reversion in ranging markets
                signal = compute_mean_reversion_signal(momentum_df)
                # Skip tick consistency for mean reversion entries
            else:
                # Trending: use momentum
                signal = compute_momentum(momentum_df, current_atr, avg_atr)

                # Tick consistency filter (trending mode only)
                if consistency < Config.TICK_CONSISTENCY_MIN_PCT:
                    return

            # Signal persistence: require N consecutive same-direction signals
            if signal == "FLAT":
                self.signal_persistence_count = 0
                self.last_persistent_direction = None
                return

            if signal == self.last_persistent_direction:
                self.signal_persistence_count += 1
            else:
                self.signal_persistence_count = 1
                self.last_persistent_direction = signal

            if self.signal_persistence_count < Config.SIGNAL_PERSISTENCE_COUNT:
                return

        else:
            # v9.1: momentum only, no regime detection for signal
            signal = compute_momentum(momentum_df, current_atr, avg_atr)
            regime = "trending"  # v9.1 treats everything as trending/momentum

        if signal == "FLAT":
            return

        # Hysteresis check
        if not self._passes_hysteresis(signal, bar_close):
            return

        # Position capacity check
        if not self._can_open_position(prices_df, current_atr, avg_atr):
            return

        # Open position
        self._open_position(signal, bar_close, bar_idx, bar_spread, regime)

    def _passes_hysteresis(self, signal: str, current_price: float) -> bool:
        """
        Check hysteresis: require $0.50 move to flip direction.
        Same-direction signals pass immediately.
        """
        if self.last_signal_direction is None:
            return True

        # Same direction always passes
        if signal == self.last_signal_direction:
            return True

        # Different direction: need sufficient price move
        price_move = abs(current_price - self.last_signal_price)
        return price_move >= Config.HYSTERESIS_THRESHOLD

    def _can_open_position(self, prices_df: pd.DataFrame,
                           current_atr: float, avg_atr: float) -> bool:
        """
        Check position capacity. Max 5 positions.
        Additional positions (beyond first) require strong momentum.
        """
        if len(self.positions) >= Config.MAX_POSITIONS:
            return False

        if len(self.positions) == 0:
            return True

        # Additional positions require strong momentum
        # Compute momentum strength
        closes = prices_df['Close'].values
        if len(closes) < Config.MOMENTUM_LOOKBACK + 2:
            return False

        current_close = closes[-1]
        reference_close = closes[-(Config.MOMENTUM_LOOKBACK + 1)]
        move = abs(current_close - reference_close)

        # Strong momentum gate: move must exceed threshold * STRONG_MOMENTUM_MULT
        strong_threshold = Config.TICK_MOMENTUM_THRESHOLD * Config.STRONG_MOMENTUM_MULT
        return move >= strong_threshold

    def _open_position(self, direction: str, price: float,
                       bar_idx: int, spread: float, regime: str):
        """Open a new position."""
        half_spread = spread / 2.0

        # Apply half-spread as entry cost
        if direction == "BUY":
            entry_price = price + half_spread
            # Fixed SL below entry
            stop_loss = entry_price - FIXED_SL
        else:
            entry_price = price - half_spread
            # Fixed SL above entry
            stop_loss = entry_price + FIXED_SL

        pos = Position(
            direction=direction,
            entry_price=entry_price,
            entry_bar=bar_idx,
            spread=spread,
            stop_loss=stop_loss,
            trailing_tier=-1,
            regime=regime,
        )
        self.positions.append(pos)

        # Update state
        self.last_trade_bar = bar_idx
        self.last_signal_direction = direction
        self.last_signal_price = price


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------
def print_report(result_v91: BacktestResult, result_v92: BacktestResult):
    """Print a side-by-side comparison report."""
    print("\n" + "=" * 70)
    print("  NeuroX v9 Backtester - Comparison Report")
    print("=" * 70)

    header = f"{'Metric':<25} {'v9.1 (Momentum)':<20} {'v9.2 (Full Filters)':<20}"
    print(f"\n{header}")
    print("-" * 65)

    rows = [
        ("Total Trades", result_v91.total_trades, result_v92.total_trades),
        ("Wins", result_v91.wins, result_v92.wins),
        ("Losses", result_v91.losses, result_v92.losses),
        ("Win Rate", f"{result_v91.win_rate:.1f}%", f"{result_v92.win_rate:.1f}%"),
        ("Total Profit", f"${result_v91.total_profit:.2f}",
         f"${result_v92.total_profit:.2f}"),
        ("Gross Profit", f"${result_v91.gross_profit:.2f}",
         f"${result_v92.gross_profit:.2f}"),
        ("Gross Loss", f"${result_v91.gross_loss:.2f}",
         f"${result_v92.gross_loss:.2f}"),
        ("Profit Factor", f"{result_v91.profit_factor:.2f}",
         f"{result_v92.profit_factor:.2f}"),
        ("Max Drawdown", f"${result_v91.max_drawdown:.2f}",
         f"${result_v92.max_drawdown:.2f}"),
        ("Avg Trade Profit", f"${result_v91.avg_trade_profit:.4f}",
         f"${result_v92.avg_trade_profit:.4f}"),
        ("Best Trade", f"${result_v91.best_trade:.2f}",
         f"${result_v92.best_trade:.2f}"),
        ("Worst Trade", f"${result_v91.worst_trade:.2f}",
         f"${result_v92.worst_trade:.2f}"),
    ]

    for label, v1, v2 in rows:
        print(f"  {label:<23} {str(v1):<20} {str(v2):<20}")

    print(f"\n{'Regime Breakdown':<25}")
    print("-" * 65)
    print(f"  {'Trending Trades':<23} {result_v91.trending_trades:<20} "
          f"{result_v92.trending_trades:<20}")
    print(f"  {'Ranging Trades':<23} {result_v91.ranging_trades:<20} "
          f"{result_v92.ranging_trades:<20}")

    print("\n" + "=" * 70)
    print(f"  v9.1 trades are all classified as 'trending' (momentum-only mode)")
    print(f"  v9.2 uses dual-mode: momentum in trending, mean reversion in ranging")
    print("=" * 70)
    print()
    print("  NOTE: Tick consistency is approximated from M1 bar closes (40-bar")
    print("  lookback) and may behave differently than live tick-level filtering,")
    print("  where 40 consecutive ticks arrive in sub-second bursts. Backtester")
    print("  results should not be treated as equivalent to live performance.")
    print()


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main():
    """Main entry point for the backtester."""
    if len(sys.argv) < 2:
        print("NeuroX v9 Backtester")
        print("=" * 40)
        print()
        print("Usage: python backtest.py <csv_file>")
        print()
        print("Arguments:")
        print("  csv_file    Path to MT5-exported M1 OHLC CSV file")
        print()
        print("Example:")
        print("  python backtest.py data/XAUUSD_M1.csv")
        print()
        print("The backtester runs both v9.1 (momentum only) and v9.2")
        print("(full filters) modes and prints a comparison report.")
        print()
        print("See data/README.md for CSV format details.")
        sys.exit(0)

    filepath = sys.argv[1]

    if not os.path.isfile(filepath):
        print(f"Error: File not found: {filepath}")
        print(f"Please check the path and try again.")
        sys.exit(1)

    print(f"Loading data from: {filepath}")
    try:
        df = load_csv(filepath)
    except Exception as e:
        print(f"Error loading CSV: {e}")
        sys.exit(1)

    print(f"Loaded {len(df)} bars")
    print(f"Price range: ${df['Close'].min():.2f} - ${df['Close'].max():.2f}")
    print()

    # Run v9.1
    print("Running v9.1 (Momentum Only)...")
    bt_v91 = Backtester(df.copy(), mode="v9.1")
    result_v91 = bt_v91.run()
    print(f"  Completed: {result_v91.total_trades} trades")

    # Run v9.2
    print("Running v9.2 (Full Filters)...")
    bt_v92 = Backtester(df.copy(), mode="v9.2")
    result_v92 = bt_v92.run()
    print(f"  Completed: {result_v92.total_trades} trades")

    # Print comparison
    print_report(result_v91, result_v92)


if __name__ == "__main__":
    main()
