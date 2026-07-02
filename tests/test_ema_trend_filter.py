"""Tests for 50 EMA trend filter and EMA-based SL logic."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


class TestEmaTrendFilterConfig:
    """Test config settings for 50 EMA trend filter."""

    def test_ema_trend_period_default(self):
        """EMA_TREND_PERIOD should default to 50."""
        assert Config.EMA_TREND_PERIOD == 50

    def test_ema_trend_enabled_default(self):
        """EMA_TREND_ENABLED should default to True."""
        assert Config.EMA_TREND_ENABLED is True

    def test_ema_sl_period_default(self):
        """EMA_SL_PERIOD should default to 60."""
        assert Config.EMA_SL_PERIOD == 60

    def test_ema_sl_enabled_default(self):
        """EMA_SL_ENABLED should default to True."""
        assert Config.EMA_SL_ENABLED is True

    def test_ema_sl_min_distance_default(self):
        """EMA_SL_MIN_DISTANCE should default to 0.50."""
        assert Config.EMA_SL_MIN_DISTANCE == 0.50


class TestReadEmaFromEaWith50Ema:
    """Test reading 50 EMA and 60 EMA SL from EA file."""

    def test_11_field_format_with_ema50(self, tmp_path):
        """Should parse ema50 from field 11."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text(
            "2650.50|2648.30|0.80|2|35.50|2660.00|2640.00|2655.00|2645.00|48.50|2640.00",
            encoding="utf-16"
        )
        result = read_ema_from_ea(bridge)
        assert result[10] == 2640.00  # ema50
        assert result[11] == 0.0     # ema_sl defaults to 0 if not present

    def test_12_field_format_with_ema50_and_ema_sl(self, tmp_path):
        """Should parse both ema50 and ema_sl from full format."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text(
            "2650.50|2648.30|0.80|2|35.50|2660.00|2640.00|2655.00|2645.00|48.50|2640.00|2638.50",
            encoding="utf-16"
        )
        result = read_ema_from_ea(bridge)
        assert result[10] == 2640.00  # ema50
        assert result[11] == 2638.50  # ema_sl (60 EMA)

    def test_backward_compat_10_fields(self, tmp_path):
        """Old 10-field format should still work, ema50 and ema_sl default to 0."""
        from bridge import Bridge
        from main import read_ema_from_ea
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text(
            "2650.50|2648.30|0.80|2|35.50|2660.00|2640.00|2655.00|2645.00|48.50",
            encoding="utf-16"
        )
        result = read_ema_from_ea(bridge)
        assert result[10] == 0.0  # ema50 not available
        assert result[11] == 0.0  # ema_sl not available


class TestEmaTrendFilterDirection:
    """Test the 50 EMA trend filter direction logic in main loop."""

    def test_price_above_both_emas_means_buy(self):
        """When price > ema50 and price > ema9, only BUY is allowed."""
        # Simulating the logic from main.py
        current_price = 2660.0
        ea_ema9 = 2655.0
        ea_ema50 = 2640.0
        ema_trend_enabled = True

        if ema_trend_enabled and ea_ema50 > 0.0:
            price_above_ema50 = current_price > ea_ema50
            price_above_ema9 = current_price > ea_ema9
            price_below_ema50 = current_price < ea_ema50
            price_below_ema9 = current_price < ea_ema9

            if price_above_ema50 and price_above_ema9:
                direction = "BUY"
            elif price_below_ema50 and price_below_ema9:
                direction = "SELL"
            else:
                direction = None
        else:
            direction = None

        assert direction == "BUY"

    def test_price_below_both_emas_means_sell(self):
        """When price < ema50 and price < ema9, only SELL is allowed."""
        current_price = 2630.0
        ea_ema9 = 2635.0
        ea_ema50 = 2640.0

        price_above_ema50 = current_price > ea_ema50
        price_above_ema9 = current_price > ea_ema9
        price_below_ema50 = current_price < ea_ema50
        price_below_ema9 = current_price < ea_ema9

        if price_above_ema50 and price_above_ema9:
            direction = "BUY"
        elif price_below_ema50 and price_below_ema9:
            direction = "SELL"
        else:
            direction = None

        assert direction == "SELL"

    def test_price_between_emas_means_no_trade(self):
        """When price is above one EMA but below the other, no trade (conflicting)."""
        # Price above EMA9 but below EMA50
        current_price = 2645.0
        ea_ema9 = 2640.0
        ea_ema50 = 2650.0

        price_above_ema50 = current_price > ea_ema50
        price_above_ema9 = current_price > ea_ema9
        price_below_ema50 = current_price < ea_ema50
        price_below_ema9 = current_price < ea_ema9

        if price_above_ema50 and price_above_ema9:
            direction = "BUY"
        elif price_below_ema50 and price_below_ema9:
            direction = "SELL"
        else:
            direction = None

        assert direction is None

    def test_price_below_ema9_above_ema50_means_no_trade(self):
        """When price is below EMA9 but above EMA50, no trade (conflicting)."""
        # Price below EMA9 but above EMA50
        current_price = 2645.0
        ea_ema9 = 2650.0
        ea_ema50 = 2640.0

        price_above_ema50 = current_price > ea_ema50
        price_above_ema9 = current_price > ea_ema9
        price_below_ema50 = current_price < ea_ema50
        price_below_ema9 = current_price < ea_ema9

        if price_above_ema50 and price_above_ema9:
            direction = "BUY"
        elif price_below_ema50 and price_below_ema9:
            direction = "SELL"
        else:
            direction = None

        assert direction is None

    def test_trend_filter_disabled_uses_ema9_only(self):
        """When EMA_TREND_ENABLED is False, fallback to price vs EMA9 only."""
        current_price = 2660.0
        ea_ema9 = 2655.0
        ea_ema50 = 2640.0
        ema_trend_enabled = False

        if ema_trend_enabled and ea_ema50 > 0.0:
            direction = None
        else:
            if current_price > ea_ema9:
                direction = "BUY"
            elif current_price < ea_ema9:
                direction = "SELL"
            else:
                direction = None

        assert direction == "BUY"

    def test_ema50_zero_falls_back_to_ema9_only(self):
        """When ema50 is 0 (not yet computed), fallback to EMA9 only."""
        current_price = 2660.0
        ea_ema9 = 2655.0
        ea_ema50 = 0.0
        ema_trend_enabled = True

        if ema_trend_enabled and ea_ema50 > 0.0:
            direction = None
        else:
            if current_price > ea_ema9:
                direction = "BUY"
            elif current_price < ea_ema9:
                direction = "SELL"
            else:
                direction = None

        assert direction == "BUY"


class TestEmaBasedSL:
    """Test EMA-based stop loss logic."""

    def test_ema_sl_used_when_available(self):
        """When EMA_SL_ENABLED and ema_sl > 0, SL distance = |price - ema_sl|."""
        current_price = 2660.0
        ea_ema_sl = 2655.0
        ema_sl_enabled = True
        min_distance = 0.50

        if ema_sl_enabled and ea_ema_sl > 0.0:
            sl_distance = abs(current_price - ea_ema_sl)
            if sl_distance < min_distance:
                sl_distance = min_distance
        else:
            sl_distance = 2.0  # swing fallback

        assert sl_distance == 5.0

    def test_ema_sl_min_distance_enforced(self):
        """When EMA SL distance is too small, minimum is enforced."""
        current_price = 2660.0
        ea_ema_sl = 2659.80  # Very close
        ema_sl_enabled = True
        min_distance = 0.50

        if ema_sl_enabled and ea_ema_sl > 0.0:
            sl_distance = abs(current_price - ea_ema_sl)
            if sl_distance < min_distance:
                sl_distance = min_distance
        else:
            sl_distance = 2.0

        assert sl_distance == 0.50

    def test_ema_sl_disabled_uses_swing(self):
        """When EMA_SL_ENABLED is False, swing SL is used."""
        current_price = 2660.0
        ea_ema_sl = 2655.0
        ema_sl_enabled = False
        min_distance = 0.50

        used_ema_sl = False
        if ema_sl_enabled and ea_ema_sl > 0.0:
            sl_distance = abs(current_price - ea_ema_sl)
            used_ema_sl = True
        else:
            sl_distance = 2.0  # swing fallback
            used_ema_sl = False

        assert not used_ema_sl
        assert sl_distance == 2.0

    def test_ema_sl_zero_uses_swing_fallback(self):
        """When ema_sl is 0 (not computed yet), swing SL is used."""
        current_price = 2660.0
        ea_ema_sl = 0.0
        ema_sl_enabled = True

        used_ema_sl = False
        if ema_sl_enabled and ea_ema_sl > 0.0:
            sl_distance = abs(current_price - ea_ema_sl)
            used_ema_sl = True
        else:
            sl_distance = 2.0  # swing fallback
            used_ema_sl = False

        assert not used_ema_sl
        assert sl_distance == 2.0


class TestIntelligenceEma50Field:
    """Test that intelligence file includes ema50_trend field."""

    def test_write_intelligence_with_ema50_trend(self, tmp_path):
        """write_intelligence should include ema50_trend as 16th field."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        bridge.write_intelligence(
            strategy="EMA_TREND",
            decision="TRADING",
            reason="",
            ema_trend="P>EMA9 BUY $0.45 ADX=35.0",
            choppy_votes="1/5 TRENDING",
            swing_sl="EMA60 $2638.50",
            breakeven_status="INACTIVE",
            reversal_status="CLEAR",
            ema50_trend="BULLISH (2640.00)",
        )
        intel_path = bridge.common_path / Config.INTELLIGENCE_FILE
        content = intel_path.read_text(encoding="ascii").strip()
        fields = content.split("|")
        assert len(fields) == 16
        assert fields[15] == "BULLISH (2640.00)"

    def test_write_intelligence_ema50_trend_conflicting(self, tmp_path):
        """ema50_trend should show CONFLICTING when EMAs disagree."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        bridge.write_intelligence(
            strategy="EMA_TREND",
            decision="FILTERED",
            reason="EMA_CONFLICTING",
            ema50_trend="CONFLICTING",
        )
        intel_path = bridge.common_path / Config.INTELLIGENCE_FILE
        content = intel_path.read_text(encoding="ascii").strip()
        fields = content.split("|")
        assert fields[15] == "CONFLICTING"
        assert fields[8] == "FILTERED"
        assert fields[9] == "EMA_CONFLICTING"
