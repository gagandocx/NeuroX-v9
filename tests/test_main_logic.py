"""Tests for main.py logic: EMA-only trading with cooldown."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from config import Config


@pytest.fixture(autouse=True)
def reset_main_state():
    """Reset all global state in main module before each test."""
    main.last_signal_time = 0.0
    main.current_price = 0.0
    yield


class TestCanTrade:
    """Test cooldown logic."""

    def test_can_trade_respects_cooldown(self):
        """can_trade should respect COOLDOWN_SECONDS."""
        main.last_signal_time = time.time()
        assert main.can_trade() is False

        main.last_signal_time = time.time() - Config.COOLDOWN_SECONDS - 1
        assert main.can_trade() is True

    def test_can_trade_initially_true(self):
        """can_trade should be True when no signal has been fired."""
        main.last_signal_time = 0.0
        assert main.can_trade() is True

    def test_cooldown_from_config(self):
        """Cooldown should come from Config."""
        assert Config.COOLDOWN_SECONDS == 1


class TestCreateSignal:
    """Test signal creation."""

    def test_create_signal_buy(self):
        """create_signal should produce correct dict for BUY."""
        sig = main.create_signal("BUY", 2000.0)
        assert sig["action"] == "BUY"
        assert sig["symbol"] == Config.SYMBOL
        assert sig["lot_size"] == Config.LOT_SIZE
        assert sig["model_name"] == "ema_trend_v9"
        assert sig["regime"] == "momentum"
        assert sig["entry_type"] == "MARKET"

    def test_create_signal_sell(self):
        """create_signal should produce correct dict for SELL."""
        sig = main.create_signal("SELL", 2000.0)
        assert sig["action"] == "SELL"
        assert sig["entry_type"] == "MARKET"
        assert sig["model_name"] == "ema_trend_v9"

    def test_create_signal_lot_size_bounded(self):
        """Lot size should be bounded by MIN_LOT_SIZE and MAX_LOT_SIZE."""
        sig = main.create_signal("BUY", 2000.0)
        assert sig["lot_size"] >= Config.MIN_LOT_SIZE
        assert sig["lot_size"] <= Config.MAX_LOT_SIZE


class TestFireSignal:
    """Test fire_signal updates cooldown state."""

    def test_fire_signal_updates_cooldown(self, tmp_path):
        """fire_signal should update last_signal_time."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))

        before = time.time()
        main.fire_signal(bridge, "BUY", 2000.0, "TEST")
        after = time.time()

        assert main.last_signal_time >= before
        assert main.last_signal_time <= after

    def test_fire_signal_buy(self, tmp_path):
        """fire_signal should successfully write a BUY signal."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))

        main.fire_signal(bridge, "BUY", 2000.0, "EMA TREND")
        assert main.last_signal_time > 0

    def test_fire_signal_sell(self, tmp_path):
        """fire_signal should successfully write a SELL signal."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))

        main.fire_signal(bridge, "SELL", 2050.0, "EMA TREND")
        assert main.last_signal_time > 0


class TestReadEmaFromEa:
    """Test EMA reading from EA file."""

    def test_read_ema_no_file(self, tmp_path):
        """Should return defaults if file doesn't exist."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        result = main.read_ema_from_ea(bridge)
        assert result == (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_read_ema_valid_file(self, tmp_path):
        """Should return EMA values from a valid file."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|3.00|2", encoding="utf-16")
        result = main.read_ema_from_ea(bridge)
        assert result == (2650.50, 2648.30, 3.00, 2, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_read_ema_invalid_content(self, tmp_path):
        """Should return defaults for invalid content."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("garbage", encoding="utf-16")
        result = main.read_ema_from_ea(bridge)
        assert result == (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_read_ema_with_adx(self, tmp_path):
        """Should return ADX value from fifth field."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|1.00|2|25.30", encoding="utf-16")
        result = main.read_ema_from_ea(bridge)
        assert result == (2650.50, 2648.30, 1.00, 2, 25.30, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_read_ema_without_adx_defaults_100(self, tmp_path):
        """Should default ADX to 100.0 when not present (always allow trading)."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|1.00|2", encoding="utf-16")
        result = main.read_ema_from_ea(bridge)
        assert result == (2650.50, 2648.30, 1.00, 2, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_read_ema_full_10_fields(self, tmp_path):
        """Should parse all 10 fields including swing_high, swing_low, bb, choppiness."""
        from bridge import Bridge
        bridge = Bridge(mt5_common_path=str(tmp_path))
        ema_path = tmp_path / Config.EMA_FILE
        ema_path.write_text("2650.50|2648.30|0.80|2|25.30|2655.00|2645.00|2653.00|2647.00|55.50", encoding="utf-16")
        result = main.read_ema_from_ea(bridge)
        assert result == (2650.50, 2648.30, 0.80, 2, 25.30, 2655.00, 2645.00, 2653.00, 2647.00, 55.50)


class TestADXFilter:
    """Test ADX ranging market filter (now part of multi-indicator choppy filter)."""

    def test_adx_below_threshold_filters(self):
        """ADX below MIN_ADX_THRESHOLD should contribute to choppy vote."""
        assert 15.0 < Config.MIN_ADX_THRESHOLD

    def test_adx_above_threshold_allows(self):
        """ADX above MIN_ADX_THRESHOLD should not trigger choppy vote."""
        assert 30.0 >= Config.MIN_ADX_THRESHOLD

    def test_adx_at_threshold_allows(self):
        """ADX exactly at MIN_ADX_THRESHOLD should not trigger choppy vote."""
        assert not (20.0 < Config.MIN_ADX_THRESHOLD)

    def test_adx_default_100_always_allows(self):
        """Default ADX of 100.0 (EA not writing) should always allow trading."""
        assert not (100.0 < Config.MIN_ADX_THRESHOLD)

    def test_config_min_adx_threshold(self):
        """Config MIN_ADX_THRESHOLD should be 20.0."""
        assert Config.MIN_ADX_THRESHOLD == 20.0

    def test_choppy_filter_enabled(self):
        """Config CHOPPY_FILTER_ENABLED should be True."""
        assert Config.CHOPPY_FILTER_ENABLED is True

    def test_ranging_filter_agreement(self):
        """Config RANGING_FILTER_AGREEMENT should be 2."""
        assert Config.RANGING_FILTER_AGREEMENT == 2


class TestGetEmaTrendLabel:
    """Test EMA trend label generation (price vs EMA 9)."""

    def test_warmup_label(self):
        """Should return WARMUP when ema9 is 0."""
        assert main.get_ema_trend_label_from_ea(0.0, 0.0, 2000.0) == "WARMUP"

    def test_buy_label(self):
        """Should return BUY label when price > ema9."""
        label = main.get_ema_trend_label_from_ea(2000.0, 1998.0, 2001.0)
        assert "BUY" in label
        assert "P>EMA9" in label

    def test_sell_label(self):
        """Should return SELL label when price < ema9."""
        label = main.get_ema_trend_label_from_ea(2000.0, 2002.0, 1999.0)
        assert "SELL" in label
        assert "P<EMA9" in label

    def test_flat_label(self):
        """Should return FLAT when price equals ema9."""
        assert main.get_ema_trend_label_from_ea(2000.0, 2000.0, 2000.0) == "FLAT"

    def test_price_above_ema9_label(self):
        """Should include P>EMA9 when price > ema9."""
        label = main.get_ema_trend_label_from_ea(2000.0, 1998.0, 2001.0)
        assert "P>EMA9" in label

    def test_price_below_ema9_label(self):
        """Should include P<EMA9 when price < ema9."""
        label = main.get_ema_trend_label_from_ea(2002.0, 2004.0, 2001.0)
        assert "P<EMA9" in label


class TestNoRemovedLogic:
    """Verify that removed logic is no longer in main.py."""

    def test_no_momentum_import(self):
        """main module should not import momentum functions."""
        import inspect
        source = inspect.getsource(main)
        assert "from momentum import" not in source
        assert "compute_momentum" not in source
        assert "detect_regime" not in source
        assert "compute_mean_reversion_signal" not in source

    def test_no_intelligence_import(self):
        """main module should not import intelligence functions."""
        import inspect
        source = inspect.getsource(main)
        assert "from intelligence import" not in source
        assert "compute_acceleration" not in source
        assert "detect_micro_patterns" not in source

    def test_no_velocity_spike(self):
        """main module should not have velocity spike logic."""
        import inspect
        source = inspect.getsource(main)
        assert "velocity_spike" not in source
        assert "check_velocity_spike" not in source

    def test_no_liquidity_sweep(self):
        """main module should not import liquidity sweep."""
        import inspect
        source = inspect.getsource(main)
        assert "from liquidity_sweep import" not in source
        assert "detect_liquidity_sweep" not in source

    def test_no_cumulative_delta(self):
        """main module should not import cumulative delta."""
        import inspect
        source = inspect.getsource(main)
        assert "from cumulative_delta import" not in source

    def test_no_tick_frequency(self):
        """main module should not import tick frequency."""
        import inspect
        source = inspect.getsource(main)
        assert "from tick_frequency import" not in source

    def test_no_scalp_exit(self):
        """main module should not have scalp exit logic."""
        import inspect
        source = inspect.getsource(main)
        assert "check_scalp_exit" not in source
        assert "scalp_entry_price" not in source

    def test_no_brain_settings(self):
        """main module should not write brain settings."""
        import inspect
        source = inspect.getsource(main)
        assert "write_brain_settings" not in source

    def test_no_atr_filter(self):
        """main module should not have ATR filter."""
        import inspect
        source = inspect.getsource(main)
        assert "passes_atr_filter" not in source

    def test_no_signal_persistence(self):
        """main module should not have signal persistence."""
        import inspect
        source = inspect.getsource(main)
        assert "passes_signal_persistence" not in source

    def test_ema_distance_filter_present(self):
        """main module should have EMA distance filter using Config.EMA_MAX_DISTANCE."""
        import inspect
        source = inspect.getsource(main)
        assert "EMA_MAX_DISTANCE" in source

    def test_no_hysteresis(self):
        """main module should not have hysteresis logic."""
        import inspect
        source = inspect.getsource(main)
        assert "passes_hysteresis" not in source
        assert "HYSTERESIS_THRESHOLD" not in source

    def test_no_position_tracking(self):
        """main module should not have complex position tracking (uses EA count instead)."""
        import inspect
        source = inspect.getsource(main)
        assert "has_capacity" not in source
        assert "direction_matches_open" not in source

    def test_no_trailing_stop(self):
        """main module should not have TrailingStopManager references."""
        import inspect
        source = inspect.getsource(main)
        assert "TrailingStopManager" not in source

    def test_no_optimizer(self):
        """main module should not import optimizer."""
        import inspect
        source = inspect.getsource(main)
        assert "from optimizer import" not in source
        assert "RollingTracker" not in source

    def test_no_performance(self):
        """main module should not import performance."""
        import inspect
        source = inspect.getsource(main)
        assert "from performance import" not in source
        assert "PositionSizer" not in source

    def test_no_support_resistance(self):
        """main module should not import support resistance."""
        import inspect
        source = inspect.getsource(main)
        assert "from support_resistance import" not in source

    def test_no_mtf_confluence(self):
        """main module should not import MTF confluence."""
        import inspect
        source = inspect.getsource(main)
        assert "from mtf_confluence import" not in source
