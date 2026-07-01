"""Tests for momentum.py"""

import numpy as np
import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from momentum import compute_momentum, compute_atr, detect_regime, compute_mean_reversion_signal
from config import Config


class TestComputeMomentum:
    """Test momentum direction detection."""

    def test_buy_signal_simple_array(self):
        """Rising prices should return BUY."""
        # Create a clear uptrend exceeding threshold ($0.60)
        prices = np.array([2000.0, 2000.2, 2000.4, 2000.6, 2000.8,
                           2001.0, 2001.2, 2001.4, 2001.6, 2001.8])
        result = compute_momentum(prices)
        assert result == "BUY"

    def test_sell_signal_simple_array(self):
        """Falling prices should return SELL."""
        prices = np.array([2001.8, 2001.6, 2001.4, 2001.2, 2001.0,
                           2000.8, 2000.6, 2000.4, 2000.2, 2000.0])
        result = compute_momentum(prices)
        assert result == "SELL"

    def test_flat_signal(self):
        """Sideways prices should return FLAT."""
        prices = np.array([2000.0, 2000.1, 2000.0, 2000.1, 2000.0,
                           2000.1, 2000.0, 2000.1, 2000.0, 2000.1])
        result = compute_momentum(prices)
        assert result == "FLAT"

    def test_buy_signal_dataframe(self):
        """DataFrame with Close column should work."""
        df = pd.DataFrame({
            "Close": [2000.0, 2000.2, 2000.4, 2000.6, 2000.8,
                      2001.0, 2001.2, 2001.4, 2001.6, 2001.8]
        })
        result = compute_momentum(df)
        assert result == "BUY"

    def test_sell_signal_dataframe(self):
        """DataFrame with falling Close should return SELL."""
        df = pd.DataFrame({
            "Close": [2001.8, 2001.6, 2001.4, 2001.2, 2001.0,
                      2000.8, 2000.6, 2000.4, 2000.2, 2000.0]
        })
        result = compute_momentum(df)
        assert result == "SELL"

    def test_insufficient_data_returns_flat(self):
        """Too few data points should return FLAT."""
        prices = np.array([2000.0, 2001.0])
        result = compute_momentum(prices)
        assert result == "FLAT"

    def test_empty_dataframe_returns_flat(self):
        """Empty DataFrame should return FLAT."""
        df = pd.DataFrame()
        result = compute_momentum(df)
        assert result == "FLAT"

    def test_invalid_input_returns_flat(self):
        """Non-array/non-DataFrame input should return FLAT."""
        result = compute_momentum("invalid")
        assert result == "FLAT"
        result = compute_momentum(None)
        assert result == "FLAT"

    def test_adaptive_lookback_high_atr(self):
        """High ATR should use shorter lookback (3 bars)."""
        # With 3-bar lookback, need big move in last 3 bars
        prices = np.array([2000.0, 2000.0, 2000.0, 2000.0, 2000.0,
                           2000.0, 2000.0, 2001.0, 2002.0, 2003.0])
        # high ATR = 3.0, avg ATR = 1.0 -> ratio > 1.5 -> use 3-bar lookback
        result = compute_momentum(prices, adaptive_atr=3.0, avg_atr=1.0)
        assert result == "BUY"

    def test_adaptive_lookback_low_atr(self):
        """Low ATR should use longer lookback (7 bars)."""
        # With 7-bar lookback, need move over 7 bars
        # Here the last 7 bars show a clear move up
        prices = np.array([2000.0, 2000.0, 2000.1, 2000.2, 2000.3,
                           2000.4, 2000.5, 2000.6, 2000.8, 2001.0])
        # normal ATR = 1.0, avg ATR = 1.0 -> ratio = 1.0 < 1.5 -> 7-bar lookback
        result = compute_momentum(prices, adaptive_atr=1.0, avg_atr=1.0)
        assert result == "BUY"

    def test_volume_weighted_mode(self):
        """Volume-weighted momentum should give more weight to high-volume bars."""
        # Large volume on the final up-bar makes vw_momentum exceed $0.60
        df = pd.DataFrame({
            "Close": [2000.0, 2000.0, 2000.0, 2000.0, 2000.0,
                      2000.0, 2000.0, 2000.0, 2000.0, 2002.0],
            "Volume": [100, 100, 100, 100, 100,
                       100, 100, 100, 100, 10000],
        })
        result = compute_momentum(df)
        assert result == "BUY"

    def test_volume_weighted_sell(self):
        """Volume-weighted sell signal."""
        df = pd.DataFrame({
            "Close": [2002.0, 2002.0, 2002.0, 2002.0, 2002.0,
                      2002.0, 2002.0, 2002.0, 2002.0, 2000.0],
            "Volume": [100, 100, 100, 100, 100,
                       100, 100, 100, 100, 10000],
        })
        result = compute_momentum(df)
        assert result == "SELL"


class TestComputeATR:
    """Test ATR computation."""

    def test_basic_atr(self):
        """ATR should be computed from OHLC data."""
        np.random.seed(42)
        n = 30
        base = 2000.0 + np.cumsum(np.random.randn(n) * 0.5)
        df = pd.DataFrame({
            "High": base + np.random.rand(n) * 2,
            "Low": base - np.random.rand(n) * 2,
            "Close": base,
        })
        atr, avg_atr = compute_atr(df, period=14)
        assert atr > 0
        assert avg_atr > 0

    def test_insufficient_data(self):
        """Not enough data should return (0, 0)."""
        df = pd.DataFrame({
            "High": [2001.0, 2002.0],
            "Low": [1999.0, 2000.0],
            "Close": [2000.0, 2001.0],
        })
        atr, avg_atr = compute_atr(df, period=14)
        assert atr == 0.0
        assert avg_atr == 0.0

    def test_missing_columns(self):
        """Missing OHLC columns should return (0, 0)."""
        df = pd.DataFrame({"Close": [2000.0] * 20})
        atr, avg_atr = compute_atr(df)
        assert atr == 0.0
        assert avg_atr == 0.0

    def test_non_dataframe(self):
        """Non-DataFrame input should return (0, 0)."""
        atr, avg_atr = compute_atr(np.array([1, 2, 3]))
        assert atr == 0.0
        assert avg_atr == 0.0


class TestDetectRegime:
    """Test regime detection: trending vs ranging."""

    def test_trending_high_atr_ratio(self):
        """High ATR ratio (above threshold) should return trending."""
        # ATR ratio = 1.2 > 0.8 -> trending (ATR criterion fails)
        n = 25
        close = np.linspace(2000, 2010, n)
        df = pd.DataFrame({"Close": close})
        result = detect_regime(df, current_atr=1.2, avg_atr=1.0)
        assert result == "trending"

    def test_trending_normal_variance_ratio(self):
        """Normal variance ratio (trending walk) should return trending."""
        # ATR ratio < 0.8 (ranging criterion met) but variance ratio > 0.5 (trending)
        # Create a steady trending series (variance ratio should be high)
        n = 25
        close = np.linspace(2000, 2005, n)
        df = pd.DataFrame({"Close": close})
        result = detect_regime(df, current_atr=0.5, avg_atr=1.0)
        # ATR ratio = 0.5 < 0.8 (ranging), but variance ratio of linear trend is high
        assert result == "trending"

    def test_ranging_low_atr_and_low_variance(self):
        """Both low ATR ratio and low variance ratio should return ranging."""
        # Create a mean-reverting (oscillating) series
        n = 25
        # Oscillate around 2000 - the walk goes nowhere (low variance ratio)
        close = [2000.0 + 0.5 * ((-1) ** i) for i in range(n)]
        df = pd.DataFrame({"Close": close})
        # ATR ratio = 0.5 < 0.8 (ranging criterion met)
        result = detect_regime(df, current_atr=0.5, avg_atr=1.0)
        assert result == "ranging"

    def test_insufficient_data_defaults_trending(self):
        """Insufficient data should default to trending."""
        df = pd.DataFrame({"Close": [2000.0, 2001.0, 2002.0]})
        result = detect_regime(df, current_atr=0.5, avg_atr=1.0)
        assert result == "trending"

    def test_zero_avg_atr_defaults_trending(self):
        """Zero avg_atr should default to trending."""
        n = 25
        close = [2000.0] * n
        df = pd.DataFrame({"Close": close})
        result = detect_regime(df, current_atr=0.5, avg_atr=0.0)
        assert result == "trending"

    def test_non_dataframe_defaults_trending(self):
        """Non-DataFrame input should default to trending."""
        result = detect_regime(np.array([1, 2, 3]), current_atr=0.5, avg_atr=1.0)
        assert result == "trending"

    def test_missing_close_column_defaults_trending(self):
        """DataFrame without Close column should default to trending."""
        df = pd.DataFrame({"Open": [2000.0] * 25})
        result = detect_regime(df, current_atr=0.5, avg_atr=1.0)
        assert result == "trending"

    def test_mixed_case_atr_ranging_variance_not(self):
        """ATR suggests ranging but variance ratio does not -> trending."""
        # Create a trending series that has low ATR ratio
        n = 25
        close = np.linspace(2000, 2020, n)  # Strong trend
        df = pd.DataFrame({"Close": close})
        # ATR ratio < 0.8 (ranging) but variance ratio of trend is high
        result = detect_regime(df, current_atr=0.7, avg_atr=1.0)
        assert result == "trending"


class TestMeanReversionSignal:
    """Test mean reversion signal computation."""

    def test_buy_near_range_low(self):
        """Price near the bottom of the range should return BUY."""
        # Create 10 bars with range from 2000 to 2010
        # Current price near bottom (within 20% = 2000 to 2002)
        close_vals = [2005.0, 2008.0, 2010.0, 2007.0, 2006.0,
                      2004.0, 2003.0, 2002.0, 2001.0, 2000.5]
        df = pd.DataFrame({
            "Close": close_vals,
            "High": [c + 0.5 for c in close_vals],
            "Low": [c - 0.5 for c in close_vals],
        })
        # Range: high=2010.5, low=1999.5, range=11.0
        # Position: (2000.5 - 1999.5) / 11.0 = 0.09 < 0.20
        result = compute_mean_reversion_signal(df)
        assert result == "BUY"

    def test_sell_near_range_high(self):
        """Price near the top of the range should return SELL."""
        close_vals = [2005.0, 2002.0, 2000.0, 2003.0, 2004.0,
                      2006.0, 2007.0, 2008.0, 2009.0, 2009.5]
        df = pd.DataFrame({
            "Close": close_vals,
            "High": [c + 0.5 for c in close_vals],
            "Low": [c - 0.5 for c in close_vals],
        })
        # Range: high=2010.0, low=1999.5, range=10.5
        # Position: (2009.5 - 1999.5) / 10.5 = 0.95 > 0.80
        result = compute_mean_reversion_signal(df)
        assert result == "SELL"

    def test_flat_in_middle(self):
        """Price in the middle of the range should return FLAT."""
        close_vals = [2000.0, 2002.0, 2004.0, 2006.0, 2008.0,
                      2010.0, 2008.0, 2006.0, 2004.0, 2005.0]
        df = pd.DataFrame({
            "Close": close_vals,
            "High": [c + 0.5 for c in close_vals],
            "Low": [c - 0.5 for c in close_vals],
        })
        # Price at 2005.0, range ~1999.5 to 2010.5 = 11.0
        # Position: (2005.0 - 1999.5) / 11.0 = 0.5 -> FLAT
        result = compute_mean_reversion_signal(df)
        assert result == "FLAT"

    def test_flat_when_range_too_small(self):
        """Range below MEAN_REVERSION_MIN_RANGE should return FLAT."""
        # All prices within $0.50 range (< $1.00 min range)
        close_vals = [2000.0 + i * 0.05 for i in range(10)]
        df = pd.DataFrame({"Close": close_vals})
        result = compute_mean_reversion_signal(df)
        assert result == "FLAT"

    def test_insufficient_data_returns_flat(self):
        """Not enough bars should return FLAT."""
        df = pd.DataFrame({"Close": [2000.0, 2001.0, 2002.0]})
        result = compute_mean_reversion_signal(df)
        assert result == "FLAT"

    def test_non_dataframe_returns_flat(self):
        """Non-DataFrame input should return FLAT."""
        result = compute_mean_reversion_signal(np.array([1, 2, 3]))
        assert result == "FLAT"

    def test_close_only_mode(self):
        """Should work with Close column only (no High/Low)."""
        # Range from Close only: 2000 to 2005, current at 2000.5
        close_vals = [2003.0, 2005.0, 2004.0, 2003.0, 2002.0,
                      2001.0, 2000.0, 2001.5, 2001.0, 2000.5]
        df = pd.DataFrame({"Close": close_vals})
        # Range: 2000 to 2005 = 5.0
        # Position: (2000.5 - 2000) / 5.0 = 0.1 < 0.2 -> BUY
        result = compute_mean_reversion_signal(df)
        assert result == "BUY"
