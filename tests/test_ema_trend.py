"""Tests for EMA computation and EA-based EMA trend label."""

import numpy as np
import pandas as pd
import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from momentum import compute_ema
from config import Config


class TestComputeEma:
    """Test EMA computation."""

    def test_insufficient_data_returns_zero(self):
        """EMA should return 0.0 if fewer than period data points."""
        prices = np.array([2000.0, 2001.0, 2002.0])
        result = compute_ema(prices, period=9)
        assert result == 0.0

    def test_exact_period_returns_sma(self):
        """With exactly period data points, EMA equals SMA (no extra iterations)."""
        prices = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0])
        result = compute_ema(prices, period=9)
        # With exactly 9 values and period=9, the EMA seed is the SMA of all 9
        # and there are no remaining values to iterate over
        expected_sma = np.mean(prices)
        assert abs(result - expected_sma) < 1e-10

    def test_ema_responds_to_rising_prices(self):
        """EMA should be between the SMA and the latest price in an uptrend."""
        prices = np.array([2000.0, 2001.0, 2002.0, 2003.0, 2004.0,
                           2005.0, 2006.0, 2007.0, 2008.0, 2009.0,
                           2010.0, 2011.0, 2012.0])
        result = compute_ema(prices, period=9)
        # EMA should lag but be close to the latest prices
        assert result > 2006.0  # Should be above midpoint
        assert result < 2012.0  # Should be below latest price

    def test_ema_responds_to_falling_prices(self):
        """EMA should be above latest price in a downtrend."""
        prices = np.array([2012.0, 2011.0, 2010.0, 2009.0, 2008.0,
                           2007.0, 2006.0, 2005.0, 2004.0, 2003.0,
                           2002.0, 2001.0, 2000.0])
        result = compute_ema(prices, period=9)
        # EMA should be above the latest price in downtrend (lagging)
        assert result > 2000.0
        assert result < 2012.0

    def test_ema_with_pandas_series(self):
        """EMA should work with pandas Series input."""
        series = pd.Series([2000.0, 2001.0, 2002.0, 2003.0, 2004.0,
                            2005.0, 2006.0, 2007.0, 2008.0, 2009.0])
        result = compute_ema(series, period=9)
        assert result > 0.0

    def test_ema_with_list_input(self):
        """EMA should work with list input."""
        prices = [2000.0, 2001.0, 2002.0, 2003.0, 2004.0,
                  2005.0, 2006.0, 2007.0, 2008.0, 2009.0]
        result = compute_ema(prices, period=9)
        assert result > 0.0

    def test_ema_default_period_uses_config(self):
        """EMA with no period argument should use Config.EMA_MASTER_PERIOD."""
        prices = np.array([2000.0, 2001.0, 2002.0, 2003.0, 2004.0,
                           2005.0, 2006.0, 2007.0, 2008.0, 2009.0])
        result = compute_ema(prices)  # No period arg
        assert result > 0.0

    def test_ema_constant_price_equals_price(self):
        """EMA of constant prices should equal that price."""
        prices = np.array([2000.0] * 30)
        result = compute_ema(prices, period=9)
        assert abs(result - 2000.0) < 1e-10

    def test_ema_empty_array_returns_zero(self):
        """EMA of empty array returns 0.0."""
        result = compute_ema(np.array([]), period=9)
        assert result == 0.0

    def test_ema_21_period(self):
        """EMA 21 should work with enough data points."""
        prices = np.array([2000.0 + i * 0.5 for i in range(30)])
        result = compute_ema(prices, period=21)
        assert result > 0.0
        # EMA 21 should lag more than EMA 9 in an uptrend
        ema9 = compute_ema(prices, period=9)
        assert ema9 > result  # Fast EMA closer to current price in uptrend


class TestGetEmaTrendLabelFromEa:
    """Test EMA trend label using EA-provided values (price vs EMA 9)."""

    def test_warmup_label_when_ema9_zero(self):
        """Should return WARMUP when ema9 is 0."""
        from main import get_ema_trend_label_from_ea
        assert get_ema_trend_label_from_ea(0.0, 0.0, 2000.0) == "WARMUP"

    def test_buy_label_when_price_above_ema9(self):
        """Should return BUY label when price > ema9."""
        from main import get_ema_trend_label_from_ea
        label = get_ema_trend_label_from_ea(2000.0, 1998.0, 2001.0)
        assert "BUY" in label
        assert "P>EMA9" in label

    def test_sell_label_when_price_below_ema9(self):
        """Should return SELL label when price < ema9."""
        from main import get_ema_trend_label_from_ea
        label = get_ema_trend_label_from_ea(2000.0, 2002.0, 1999.0)
        assert "SELL" in label
        assert "P<EMA9" in label

    def test_flat_label_when_price_equals_ema9(self):
        """Should return FLAT when price equals ema9."""
        from main import get_ema_trend_label_from_ea
        assert get_ema_trend_label_from_ea(2000.0, 2000.0, 2000.0) == "FLAT"

    def test_price_above_ema9_label(self):
        """Should include P>EMA9 when price > ema9."""
        from main import get_ema_trend_label_from_ea
        label = get_ema_trend_label_from_ea(2000.0, 1998.0, 2001.0)
        assert "P>EMA9" in label

    def test_price_below_ema9_label(self):
        """Should include P<EMA9 when price < ema9."""
        from main import get_ema_trend_label_from_ea
        label = get_ema_trend_label_from_ea(2000.0, 2002.0, 1999.0)
        assert "P<EMA9" in label

    def test_no_crossover_when_ema15_zero(self):
        """Should still work when ema15 is 0 (only ema9 matters)."""
        from main import get_ema_trend_label_from_ea
        # With ema9 > 0 and price > ema9, should still return BUY
        label = get_ema_trend_label_from_ea(2000.0, 0.0, 2001.0)
        assert "BUY" in label
        assert "P>EMA9" in label

    def test_distance_shown_in_label(self):
        """Label should include the distance from EMA 9."""
        from main import get_ema_trend_label_from_ea
        label = get_ema_trend_label_from_ea(2000.0, 1998.0, 2001.50)
        assert "$1.50" in label


class TestReadEmaFromEa:
    """Test reading EMA values from EA file."""

    def test_no_file_returns_zeros(self, tmp_path):
        """Should return defaults when file doesn't exist."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        assert read_ema_from_ea(bridge) == (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_valid_file_returns_values(self, tmp_path):
        """Should parse EMA values from valid file."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|3.00|1", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (2650.50, 2648.30, 3.00, 1, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_invalid_content_returns_zeros(self, tmp_path):
        """Should return defaults for invalid content."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("no_pipe_here", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_empty_file_returns_zeros(self, tmp_path):
        """Should return defaults for empty file."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_three_field_format_with_max_distance(self, tmp_path):
        """Should parse max_distance from third field, default open_positions to 0."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|5.00", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (2650.50, 2648.30, 5.00, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_two_field_format_uses_config_default(self, tmp_path):
        """Should fall back to Config.EMA_MAX_DISTANCE when third field missing."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (2650.50, 2648.30, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_five_field_format_with_adx(self, tmp_path):
        """Should parse ADX value from fifth field."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|1.00|2|35.50", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (2650.50, 2648.30, 1.00, 2, 35.50, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_full_10_field_format(self, tmp_path):
        """Should parse all 10 fields including new indicators."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|0.80|2|35.50|2660.00|2640.00|2655.00|2645.00|48.50", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (2650.50, 2648.30, 0.80, 2, 35.50, 2660.00, 2640.00, 2655.00, 2645.00, 48.50, 0.0, 0.0)

    def test_full_12_field_format_with_ema50_and_ema_sl(self, tmp_path):
        """Should parse all 12 fields including ema50 and ema_sl."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|0.80|2|35.50|2660.00|2640.00|2655.00|2645.00|48.50|2645.00|2643.50", encoding="utf-16")
        assert read_ema_from_ea(bridge) == (2650.50, 2648.30, 0.80, 2, 35.50, 2660.00, 2640.00, 2655.00, 2645.00, 48.50, 2645.00, 2643.50)
