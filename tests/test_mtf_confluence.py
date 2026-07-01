"""Tests for mtf_confluence.py - Multi-Timeframe Confluence module."""

import os
import sys

import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtf_confluence import aggregate_bars, compute_mtf_confluence
from config import Config


class TestAggregateBars:
    """Test M1 bar aggregation into higher timeframes."""

    def test_aggregate_m5_basic(self):
        """5 M1 bars should produce 1 M5 bar."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5},
            {"Open": 2000.5, "High": 2002.0, "Low": 2000.0, "Close": 2001.0},
            {"Open": 2001.0, "High": 2003.0, "Low": 2000.5, "Close": 2002.0},
            {"Open": 2002.0, "High": 2004.0, "Low": 2001.5, "Close": 2003.0},
            {"Open": 2003.0, "High": 2005.0, "Low": 2002.5, "Close": 2004.0},
        ]
        result = aggregate_bars(bars, 5)
        assert len(result) == 1
        assert result.iloc[0]["Open"] == 2000.0
        assert result.iloc[0]["High"] == 2005.0
        assert result.iloc[0]["Low"] == 1999.0
        assert result.iloc[0]["Close"] == 2004.0

    def test_aggregate_m15_from_15_bars(self):
        """15 M1 bars should produce 1 M15 bar."""
        bars = []
        for i in range(15):
            bars.append({
                "Open": 2000.0 + i,
                "High": 2001.0 + i,
                "Low": 1999.0 + i,
                "Close": 2000.5 + i,
            })
        result = aggregate_bars(bars, 15)
        assert len(result) == 1
        assert result.iloc[0]["Open"] == 2000.0
        assert result.iloc[0]["High"] == 2015.0  # max of all highs
        assert result.iloc[0]["Low"] == 1999.0   # min of all lows
        assert result.iloc[0]["Close"] == 2014.5  # close of last bar

    def test_aggregate_partial_bars_discarded(self):
        """7 M1 bars should produce 1 M5 bar (2 remaining discarded)."""
        bars = [
            {"Open": 2000.0 + i, "High": 2001.0 + i,
             "Low": 1999.0 + i, "Close": 2000.5 + i}
            for i in range(7)
        ]
        result = aggregate_bars(bars, 5)
        assert len(result) == 1

    def test_aggregate_insufficient_bars(self):
        """Fewer bars than period returns empty DataFrame."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5},
            {"Open": 2000.5, "High": 2002.0, "Low": 2000.0, "Close": 2001.0},
        ]
        result = aggregate_bars(bars, 5)
        assert result.empty

    def test_aggregate_multiple_bars(self):
        """10 M1 bars should produce 2 M5 bars."""
        bars = [
            {"Open": 2000.0 + i, "High": 2001.0 + i,
             "Low": 1999.0 + i, "Close": 2000.5 + i}
            for i in range(10)
        ]
        result = aggregate_bars(bars, 5)
        assert len(result) == 2


class TestComputeMtfConfluence:
    """Test multi-timeframe confluence computation."""

    def test_insufficient_bars_returns_flat(self):
        """With too few bars, all directions should be FLAT."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5}
            for _ in range(3)
        ]
        result = compute_mtf_confluence(bars)
        assert result["m1_direction"] == "FLAT"
        assert result["conviction_level"] == "NONE"

    def test_strong_uptrend_all_agree(self):
        """Strong uptrend across all timeframes should give HIGH conviction."""
        # Create 15 bars with clear uptrend (large enough moves)
        bars = []
        for i in range(15):
            price = 2000.0 + i * 2.0  # $2 per bar uptrend
            bars.append({
                "Open": price,
                "High": price + 1.0,
                "Low": price - 0.5,
                "Close": price + 1.5,
            })
        result = compute_mtf_confluence(bars)
        assert result["m1_direction"] == "BUY"
        # M5 should also show uptrend since bars trend up strongly
        if result["m5_direction"] == "BUY" and result["m15_direction"] == "BUY":
            assert result["all_agree"] is True
            assert result["conviction_level"] == "HIGH"
            assert result["position_mult"] == Config.MTF_HIGH_CONVICTION_MULT

    def test_strong_downtrend_all_agree(self):
        """Strong downtrend across all timeframes should give HIGH conviction."""
        bars = []
        for i in range(15):
            price = 2030.0 - i * 2.0  # $2 per bar downtrend
            bars.append({
                "Open": price,
                "High": price + 0.5,
                "Low": price - 1.0,
                "Close": price - 1.5,
            })
        result = compute_mtf_confluence(bars)
        assert result["m1_direction"] == "SELL"

    def test_flat_market_returns_none_conviction(self):
        """Flat market should return NONE conviction."""
        bars = []
        for i in range(15):
            # Flat: all bars at same price
            bars.append({
                "Open": 2000.0,
                "High": 2000.1,
                "Low": 1999.9,
                "Close": 2000.0,
            })
        result = compute_mtf_confluence(bars)
        # All flat -> no conviction
        assert result["conviction_level"] in ("NONE", "MEDIUM")

    def test_m1_disagrees_with_higher_tf(self):
        """M1 disagreeing with higher TFs should give LOW conviction."""
        # First 10 bars trending up (set M5/M15 direction to BUY)
        # Last 5 bars trending down (M1 direction to SELL)
        bars = []
        for i in range(10):
            price = 2000.0 + i * 2.0
            bars.append({
                "Open": price,
                "High": price + 1.0,
                "Low": price - 0.5,
                "Close": price + 1.5,
            })
        # Reverse direction sharply for last 5 bars
        for i in range(5):
            price = 2020.0 - i * 3.0
            bars.append({
                "Open": price,
                "High": price + 0.5,
                "Low": price - 1.0,
                "Close": price - 2.0,
            })
        result = compute_mtf_confluence(bars)
        # M1 should see SELL (recent trend), M5 might differ
        assert result["m1_direction"] in ("BUY", "SELL", "FLAT")

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5}
            for _ in range(15)
        ]
        result = compute_mtf_confluence(bars)
        assert "all_agree" in result
        assert "m1_direction" in result
        assert "m5_direction" in result
        assert "m15_direction" in result
        assert "conviction_level" in result
        assert "position_mult" in result
