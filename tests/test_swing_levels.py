"""Tests for swing_levels.py - swing high/low detection for SL placement."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swing_levels import compute_swing_sl, _find_last_swing_high, _find_last_swing_low
from config import Config


class TestComputeSwingSL:
    """Test the main compute_swing_sl function."""

    def _make_bars(self, highs, lows):
        """Helper to create bar dicts from high/low lists."""
        bars = []
        for h, l in zip(highs, lows):
            bars.append({
                "Open": (h + l) / 2,
                "High": h,
                "Low": l,
                "Close": (h + l) / 2,
            })
        return bars

    def test_buy_sl_at_swing_low(self):
        """BUY SL should be at the last swing low."""
        # Create bars with a clear swing low at index 4
        # Swing low: bar 4's Low (1998.0) is lower than bars 2,3 and 5,6
        bars = self._make_bars(
            highs=[2002, 2003, 2002, 2001, 2000, 2001, 2002, 2003, 2004, 2005],
            lows= [2000, 2001, 2000, 1999, 1998, 1999, 2000, 2001, 2002, 2003],
        )

        sl = compute_swing_sl(bars, "BUY", entry_price=2005.0)
        assert sl == 1998.0

    def test_sell_sl_at_swing_high(self):
        """SELL SL should be at the last swing high."""
        # Create bars with a clear swing high at index 4
        # Swing high: bar 4's High (2010.0) is higher than bars 2,3 and 5,6
        bars = self._make_bars(
            highs=[2004, 2006, 2007, 2008, 2010, 2008, 2007, 2006, 2005, 2004],
            lows= [2002, 2004, 2005, 2006, 2008, 2006, 2005, 2004, 2003, 2002],
        )

        sl = compute_swing_sl(bars, "SELL", entry_price=2003.0)
        assert sl == 2010.0

    def test_fallback_when_no_swing_found(self):
        """Should use min_distance fallback when no swing detected."""
        # Flat bars - no swing points
        bars = self._make_bars(
            highs=[2000, 2000, 2000, 2000, 2000],
            lows= [1999, 1999, 1999, 1999, 1999],
        )

        sl = compute_swing_sl(bars, "BUY", entry_price=2000.0)
        assert sl == 2000.0 - Config.SWING_SL_MIN_DISTANCE

    def test_fallback_when_not_enough_bars(self):
        """Should use fallback when insufficient bars."""
        bars = [{"Open": 2000, "High": 2001, "Low": 1999, "Close": 2000}]
        sl = compute_swing_sl(bars, "BUY", entry_price=2000.0)
        assert sl == 2000.0 - Config.SWING_SL_MIN_DISTANCE

    def test_fallback_when_empty_bars(self):
        """Should use fallback when bars list is empty."""
        sl = compute_swing_sl([], "BUY", entry_price=2000.0)
        assert sl == 2000.0 - Config.SWING_SL_MIN_DISTANCE

    def test_fallback_sell_when_no_swing(self):
        """SELL fallback should be entry + min_distance."""
        bars = self._make_bars(
            highs=[2000, 2000, 2000, 2000, 2000],
            lows= [1999, 1999, 1999, 1999, 1999],
        )
        sl = compute_swing_sl(bars, "SELL", entry_price=2000.0)
        assert sl == 2000.0 + Config.SWING_SL_MIN_DISTANCE

    def test_minimum_distance_enforced_buy(self):
        """BUY SL should enforce minimum distance even if swing is close."""
        # Swing low very close to entry
        bars = self._make_bars(
            highs=[2001, 2002, 2001, 2000.3, 2000.1, 2000.3, 2001, 2002, 2003, 2004],
            lows= [1999.9, 2000.5, 1999.9, 1999.8, 1999.8, 1999.8, 1999.9, 2000.5, 2001, 2002],
        )
        # The swing low at 1999.8 is only 0.2 from entry 2000.0 (< 0.50 min)
        sl = compute_swing_sl(bars, "BUY", entry_price=2000.0)
        # Should enforce minimum distance
        assert sl == 2000.0 - Config.SWING_SL_MIN_DISTANCE

    def test_custom_lookback(self):
        """Should respect custom lookback parameter."""
        # Only the last 5 bars have a swing - with lookback=5, it should find it
        bars = self._make_bars(
            highs=[2002, 2003, 2002, 2001, 2000, 2001, 2002, 2003, 2002, 2001,
                   2003, 2004, 2003, 2002, 2001, 2002, 2003, 2004, 2005, 2006],
            lows= [2000, 2001, 2000, 1999, 1998, 1999, 2000, 2001, 2000, 1999,
                   2001, 2002, 2001, 2000, 1997, 2000, 2001, 2002, 2003, 2004],
        )
        # With lookback=5, only considers last 5 bars (indices 15-19 of the array)
        # Those bars have lows: 2000, 2001, 2002, 2003, 2004 - no swing low
        sl = compute_swing_sl(bars, "BUY", entry_price=2006.0, lookback=5)
        # Falls back to min distance since no swing in last 5 bars
        assert sl == 2006.0 - Config.SWING_SL_MIN_DISTANCE


class TestFindLastSwingHigh:
    """Test swing high detection."""

    def _make_bars(self, highs, lows):
        bars = []
        for h, l in zip(highs, lows):
            bars.append({"Open": (h + l) / 2, "High": h, "Low": l, "Close": (h + l) / 2})
        return bars

    def test_finds_swing_high(self):
        """Should find a clear swing high."""
        bars = self._make_bars(
            highs=[100, 102, 104, 103, 101, 100, 99, 100],
            lows= [98, 100, 102, 101, 99, 98, 97, 98],
        )
        # Swing high at index 2 (High=104): bars 0,1 have lower highs AND bars 3,4 have lower highs
        result = _find_last_swing_high(bars, width=2)
        assert result == 104

    def test_finds_last_swing_high(self):
        """Should find the LAST (most recent) swing high, not the first."""
        bars = self._make_bars(
            highs=[100, 102, 105, 103, 101, 103, 107, 104, 102, 100],
            lows= [98, 100, 103, 101, 99, 101, 105, 102, 100, 98],
        )
        # Two swing highs: index 2 (105) and index 6 (107)
        # Should return the last one (107)
        result = _find_last_swing_high(bars, width=2)
        assert result == 107

    def test_returns_none_when_no_swing(self):
        """Should return None when no swing high exists."""
        # Monotonically increasing - no swing high
        bars = self._make_bars(
            highs=[100, 101, 102, 103, 104, 105, 106, 107],
            lows= [98, 99, 100, 101, 102, 103, 104, 105],
        )
        result = _find_last_swing_high(bars, width=2)
        assert result is None

    def test_returns_none_when_too_few_bars(self):
        """Should return None when not enough bars."""
        bars = self._make_bars(highs=[100, 102], lows=[98, 100])
        result = _find_last_swing_high(bars, width=2)
        assert result is None


class TestFindLastSwingLow:
    """Test swing low detection."""

    def _make_bars(self, highs, lows):
        bars = []
        for h, l in zip(highs, lows):
            bars.append({"Open": (h + l) / 2, "High": h, "Low": l, "Close": (h + l) / 2})
        return bars

    def test_finds_swing_low(self):
        """Should find a clear swing low."""
        bars = self._make_bars(
            highs=[105, 103, 101, 102, 104, 105, 106, 107],
            lows= [103, 101, 99, 100, 102, 103, 104, 105],
        )
        # Swing low at index 2 (Low=99): bars 0,1 have higher lows AND bars 3,4 have higher lows
        result = _find_last_swing_low(bars, width=2)
        assert result == 99

    def test_finds_last_swing_low(self):
        """Should find the LAST (most recent) swing low, not the first."""
        bars = self._make_bars(
            highs=[105, 103, 101, 103, 105, 103, 100, 102, 104, 106],
            lows= [103, 101, 98, 101, 103, 101, 97, 100, 102, 104],
        )
        # Two swing lows: index 2 (98) and index 6 (97)
        # Should return the last one (97)
        result = _find_last_swing_low(bars, width=2)
        assert result == 97

    def test_returns_none_when_no_swing(self):
        """Should return None when no swing low exists."""
        # Monotonically decreasing - no swing low
        bars = self._make_bars(
            highs=[107, 106, 105, 104, 103, 102, 101, 100],
            lows= [105, 104, 103, 102, 101, 100, 99, 98],
        )
        result = _find_last_swing_low(bars, width=2)
        assert result is None

    def test_returns_none_when_too_few_bars(self):
        """Should return None when not enough bars."""
        bars = self._make_bars(highs=[102, 100], lows=[100, 98])
        result = _find_last_swing_low(bars, width=2)
        assert result is None

    def test_swing_width_1(self):
        """Should work with width=1 (only 1 bar on each side)."""
        bars = self._make_bars(
            highs=[102, 101, 100, 101, 102],
            lows= [100, 99, 97, 99, 100],
        )
        # Swing low at index 2 (Low=97): bar 1 has higher low (99), bar 3 has higher low (99)
        result = _find_last_swing_low(bars, width=1)
        assert result == 97
