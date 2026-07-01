"""Tests for spread_signal.py - Spread-as-Signal module."""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spread_signal import compute_spread_from_ticks, compute_spread_from_bars
from config import Config


class TestComputeSpreadFromTicks:
    """Test tick-based spread computation."""

    def test_tight_spread(self):
        """Small tick differences should show TIGHT spread."""
        # Ticks with very small differences (< tight threshold)
        prices = [2000.0 + i * 0.01 for i in range(20)]
        result = compute_spread_from_ticks(prices)
        assert result["spread_value"] <= Config.SPREAD_TIGHT_THRESHOLD
        assert result["spread_state"] == "TIGHT"
        assert result["can_trade"] is True

    def test_wide_spread(self):
        """Large tick differences should show WIDE spread."""
        # Ticks with large differences
        prices = [2000.0 + i * 0.20 for i in range(20)]
        result = compute_spread_from_ticks(prices)
        assert result["spread_value"] >= Config.SPREAD_WIDE_THRESHOLD
        assert result["spread_state"] in ("WIDE", "SPIKE")
        assert result["can_trade"] is False

    def test_spike_spread(self):
        """Very large tick differences should show SPIKE spread."""
        # Ticks with very large jumps
        prices = [2000.0 + i * 0.50 for i in range(20)]
        result = compute_spread_from_ticks(prices)
        assert result["spread_value"] >= Config.SPREAD_SPIKE_THRESHOLD
        assert result["spread_state"] == "SPIKE"
        assert result["can_trade"] is False

    def test_normal_spread(self):
        """Moderate tick differences should show NORMAL spread."""
        # Ticks with moderate differences (between tight and wide)
        prices = [2000.0 + i * 0.08 for i in range(20)]
        result = compute_spread_from_ticks(prices)
        assert result["spread_state"] == "NORMAL"
        assert result["can_trade"] is True

    def test_widening_trend(self):
        """Increasing tick differences should show WIDENING trend."""
        # First half: small diffs, second half: large diffs
        prices = [2000.0]
        for i in range(9):
            prices.append(prices[-1] + 0.02)  # small diffs
        for i in range(10):
            prices.append(prices[-1] + 0.20)  # large diffs
        result = compute_spread_from_ticks(prices)
        assert result["spread_trend"] == "WIDENING"

    def test_tightening_trend(self):
        """Decreasing tick differences should show TIGHTENING trend."""
        # First half: large diffs, second half: small diffs
        prices = [2000.0]
        for i in range(9):
            prices.append(prices[-1] + 0.20)  # large diffs
        for i in range(10):
            prices.append(prices[-1] + 0.02)  # small diffs
        result = compute_spread_from_ticks(prices)
        assert result["spread_trend"] == "TIGHTENING"

    def test_empty_data(self):
        """Empty prices should return defaults."""
        result = compute_spread_from_ticks([])
        assert result["spread_state"] == "NORMAL"
        assert result["can_trade"] is True

    def test_insufficient_data(self):
        """Too few prices should return defaults."""
        result = compute_spread_from_ticks([2000.0, 2000.1])
        assert result["spread_state"] == "NORMAL"
        assert result["can_trade"] is True

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        result = compute_spread_from_ticks([2000.0] * 20)
        assert "spread_value" in result
        assert "spread_state" in result
        assert "can_trade" in result
        assert "spread_trend" in result


class TestComputeSpreadFromBars:
    """Test bar-based spread computation."""

    def test_small_bar_range_tight(self):
        """Bars with small High-Low range should be TIGHT."""
        bars = [
            {"Open": 2000.0, "High": 2000.05, "Low": 1999.95, "Close": 2000.0}
            for _ in range(5)
        ]
        result = compute_spread_from_bars(bars)
        # 0.10 range / (SPREAD_BAR_MULT * threshold)
        assert result["can_trade"] is True

    def test_large_bar_range_wide(self):
        """Bars with very large High-Low range should be WIDE."""
        bars = [
            {"Open": 2000.0, "High": 2005.0, "Low": 1995.0, "Close": 2000.0}
            for _ in range(5)
        ]
        result = compute_spread_from_bars(bars)
        # 10.0 range is much larger than wide threshold * bar_mult
        assert result["can_trade"] is False

    def test_insufficient_bars(self):
        """Too few bars should return defaults."""
        bars = [{"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.0}]
        result = compute_spread_from_bars(bars)
        assert result["bar_spread_state"] == "NORMAL"
        assert result["can_trade"] is True

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.0}
            for _ in range(5)
        ]
        result = compute_spread_from_bars(bars)
        assert "bar_spread" in result
        assert "bar_spread_state" in result
        assert "can_trade" in result
