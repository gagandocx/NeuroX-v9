"""
NeuroX v9.0 - Tick Collector

Reads tick prices from the EA's tick price file and aggregates them
into 1-minute OHLC bars for momentum computation.
Zero network dependency - reads local file only.
"""

import os
import time
import logging
from collections import deque
from datetime import datetime

import pandas as pd

from config import Config

logger = logging.getLogger("TickCollector")


class TickCollector:
    """
    Collects tick prices from a file written by the MT5 EA and aggregates
    them into 1-minute OHLC bars.

    The EA writes the current tick price to a file every tick. This class
    reads that file, builds M1 candles locally, and maintains a rolling
    window of completed bars for momentum computation.
    """

    def __init__(self, tick_file_path: str, bar_count: int = 20):
        """
        Args:
            tick_file_path: Full path to the tick price file.
            bar_count: Number of completed M1 bars to keep in memory.
        """
        self.tick_file_path = tick_file_path
        self.bar_count = bar_count

        # Current bar state
        self._bar_open = 0.0
        self._bar_high = 0.0
        self._bar_low = 0.0
        self._bar_close = 0.0
        self._bar_start_minute = None  # datetime rounded to minute

        # Completed bars (deque with max length)
        self._completed_bars = deque(maxlen=bar_count)

        # Raw tick prices for tick-based momentum (instant trading)
        self._tick_prices = deque(maxlen=50)

        # Timestamps corresponding to each tick for velocity detection
        self._tick_timestamps = deque(maxlen=50)

        # Last successfully read price
        self.last_price = 0.0

        logger.info(f"TickCollector: file={tick_file_path}, bars={bar_count}")

    def read_tick(self) -> float:
        """
        Read the current tick price from the EA's tick price file.

        Returns:
            The price as a float, or 0.0 if the file is missing/stale/unreadable.
        """
        try:
            if not os.path.exists(self.tick_file_path):
                return 0.0

            with open(self.tick_file_path, "r", encoding="utf-16") as f:
                content = f.read().strip()

            if not content:
                return 0.0

            price = float(content)
            return price

        except (ValueError, OSError, IOError) as e:
            logger.debug(f"Tick read error: {e}")
            return 0.0

    def update(self) -> pd.DataFrame:
        """
        Read the current tick, aggregate into M1 bars, and return a DataFrame
        of completed bars for momentum computation.

        Returns:
            DataFrame with columns [Open, High, Low, Close] for the last N
            complete bars. Returns empty DataFrame until at least
            MIN_BARS_FOR_MOMENTUM bars are collected.
        """
        price = self.read_tick()
        if price <= 0.0:
            # No valid tick - return whatever bars we have (if enough)
            return self._build_dataframe()

        self.last_price = price
        self._tick_prices.append(price)
        self._tick_timestamps.append(time.time())
        now = datetime.now()
        current_minute = now.replace(second=0, microsecond=0)

        if self._bar_start_minute is None:
            # First tick ever - start a new bar
            self._start_new_bar(price, current_minute)
        elif current_minute > self._bar_start_minute:
            # Minute changed - close the current bar and start a new one
            self._close_current_bar()
            self._start_new_bar(price, current_minute)
        else:
            # Same minute - update current bar
            self._update_current_bar(price)

        return self._build_dataframe()

    def _start_new_bar(self, price: float, minute: datetime):
        """Start a new M1 bar."""
        self._bar_start_minute = minute
        self._bar_open = price
        self._bar_high = price
        self._bar_low = price
        self._bar_close = price

    def _update_current_bar(self, price: float):
        """Update the current bar with a new tick."""
        if price > self._bar_high:
            self._bar_high = price
        if price < self._bar_low:
            self._bar_low = price
        self._bar_close = price

    def _close_current_bar(self):
        """Close the current bar and add it to completed bars."""
        if self._bar_start_minute is not None and self._bar_open > 0.0:
            bar = {
                "Open": self._bar_open,
                "High": self._bar_high,
                "Low": self._bar_low,
                "Close": self._bar_close,
            }
            self._completed_bars.append(bar)

    def get_tick_momentum(self, lookback: int = None) -> str:
        """
        Compute momentum direction from raw tick prices (no bar aggregation).

        This enables instant trading within seconds of startup, before
        enough M1 bars have formed for bar-based momentum.

        Args:
            lookback: Number of ticks to look back. Defaults to
                      Config.TICK_MOMENTUM_LOOKBACK.

        Returns:
            "BUY" if price moved up beyond threshold,
            "SELL" if price moved down beyond threshold,
            "FLAT" otherwise or if not enough ticks collected.
        """
        if lookback is None:
            lookback = Config.TICK_MOMENTUM_LOOKBACK

        if len(self._tick_prices) < lookback:
            return "FLAT"

        current = self._tick_prices[-1]
        past = self._tick_prices[-lookback]
        diff = current - past
        threshold = Config.TICK_MOMENTUM_THRESHOLD

        if diff > threshold:
            return "BUY"
        elif diff < -threshold:
            return "SELL"
        else:
            return "FLAT"

    def get_tick_momentum_strength(self, lookback: int = None) -> float:
        """
        Compute the absolute magnitude of tick-based momentum.

        Used to determine whether momentum is strong enough to allow
        additional concurrent positions (multi-position scaling).

        Args:
            lookback: Number of ticks to look back. Defaults to
                      Config.TICK_MOMENTUM_LOOKBACK.

        Returns:
            Absolute price difference over the lookback period,
            or 0.0 if not enough ticks are collected.
        """
        if lookback is None:
            lookback = Config.TICK_MOMENTUM_LOOKBACK

        if len(self._tick_prices) < lookback:
            return 0.0

        current = self._tick_prices[-1]
        past = self._tick_prices[-lookback]
        return abs(current - past)

    def get_tick_consistency(self, lookback: int = None) -> tuple:
        """
        Analyze recent tick-to-tick moves for directional consistency.

        Counts how many consecutive tick-to-tick moves are in the same
        direction (up vs down) over the last N ticks. Used to detect
        choppy/noisy markets where ticks flip direction frequently.

        Args:
            lookback: Number of recent ticks to analyze. Defaults to
                      Config.TICK_CONSISTENCY_LOOKBACK.

        Returns:
            Tuple of (dominant_direction, consistency_pct):
            - dominant_direction: 'BUY' if mostly up moves, 'SELL' if mostly
              down moves, 'FLAT' if insufficient data or tied.
            - consistency_pct: Float 0.0-1.0 representing the fraction of
              moves in the dominant direction.
        """
        if lookback is None:
            lookback = Config.TICK_CONSISTENCY_LOOKBACK

        # Need at least 2 ticks to compute any moves
        if len(self._tick_prices) < 2:
            return ("FLAT", 0.0)

        # Use the last 'lookback' ticks (or all available if fewer)
        available = min(lookback, len(self._tick_prices))
        recent_ticks = list(self._tick_prices)[-available:]

        up_moves = 0
        down_moves = 0

        for i in range(1, len(recent_ticks)):
            diff = recent_ticks[i] - recent_ticks[i - 1]
            if diff > 0:
                up_moves += 1
            elif diff < 0:
                down_moves += 1
            # diff == 0: no move, not counted either way

        total_moves = up_moves + down_moves
        if total_moves == 0:
            return ("FLAT", 0.0)

        if up_moves > down_moves:
            dominant = "BUY"
            consistency_pct = up_moves / total_moves
        elif down_moves > up_moves:
            dominant = "SELL"
            consistency_pct = down_moves / total_moves
        else:
            # Exactly tied
            dominant = "FLAT"
            consistency_pct = 0.5

        return (dominant, consistency_pct)

    def detect_velocity_spike(self) -> tuple:
        """
        Detect if price moved >= TICK_VELOCITY_THRESHOLD within
        TICK_VELOCITY_WINDOW seconds by scanning recent ticks.

        Returns:
            Tuple of (direction, magnitude):
            - direction: 'BUY' if spike is upward, 'SELL' if downward, None if no spike.
            - magnitude: Absolute price move that triggered the spike (0.0 if no spike).
        """
        if len(self._tick_prices) < 2:
            return (None, 0.0)

        now = self._tick_timestamps[-1]
        current_price = self._tick_prices[-1]
        window = Config.TICK_VELOCITY_WINDOW
        threshold = Config.TICK_VELOCITY_THRESHOLD

        # Scan backwards through ticks within the time window
        for i in range(len(self._tick_timestamps) - 2, -1, -1):
            elapsed = now - self._tick_timestamps[i]
            if elapsed > window:
                break
            diff = current_price - self._tick_prices[i]
            magnitude = abs(diff)
            if magnitude >= threshold:
                direction = "BUY" if diff > 0 else "SELL"
                return (direction, magnitude)

        return (None, 0.0)

    def detect_exhaustion(self) -> bool:
        """
        Detect momentum exhaustion by checking if the last EXHAUSTION_BAR_COUNT
        completed bars have shrinking ranges (each bar's range < previous bar's range).

        Returns:
            True if exhaustion pattern is detected, False otherwise.
        """
        count = Config.EXHAUSTION_BAR_COUNT
        if len(self._completed_bars) < count + 1:
            return False

        # Check the last 'count' bars have shrinking ranges compared to previous
        bars = list(self._completed_bars)
        # We need count+1 bars: the reference bar + count shrinking bars
        # Check that bars[-count] through bars[-1] each have smaller range than predecessor
        for i in range(len(bars) - count, len(bars)):
            current_range = bars[i]["High"] - bars[i]["Low"]
            prev_range = bars[i - 1]["High"] - bars[i - 1]["Low"]
            if current_range >= prev_range:
                return False

        return True

    def _build_dataframe(self) -> pd.DataFrame:
        """
        Build a DataFrame from completed bars.

        Returns empty DataFrame if fewer than MIN_BARS_FOR_MOMENTUM bars
        are available.
        """
        if len(self._completed_bars) < Config.MIN_BARS_FOR_MOMENTUM:
            return pd.DataFrame()

        return pd.DataFrame(list(self._completed_bars))
