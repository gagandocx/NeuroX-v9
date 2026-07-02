"""Tests for the CandleCloseManager (candle-close exit system)."""

import os
import sys
import time
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trailing_stop import CandleCloseManager
from config import Config


class TestCandleCloseManagerInit:
    """Test CandleCloseManager initialization and state."""

    def test_initial_state(self):
        """Manager should start with no tracking."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 0.0,
            write_exit_fn=lambda **kw: True,
        )
        assert mgr.is_tracking is False
        assert mgr.close_fired is False

    def test_start_tracking(self):
        """start_tracking should set tracking state."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "12345")
        assert mgr.is_tracking is True
        assert mgr.close_fired is False

    def test_stop_tracking(self):
        """stop_tracking should reset state."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "12345")
        mgr.stop_tracking()
        assert mgr.is_tracking is False


class TestCandleCloseDetection:
    """Test candle close detection logic."""

    def test_candle_close_fires_when_minute_changes(self):
        """Should fire CLOSE_FULL when bar minute changes."""
        current_minute = [30]
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: current_minute[0],
        )

        mgr.start_tracking("BUY", 2000.0, "T1")

        # Simulate minute change
        current_minute[0] = 31

        # Directly call the internal check
        with mgr._lock:
            result = mgr._check_candle_close()
        assert result is True

    def test_no_candle_close_when_same_minute(self):
        """Should NOT fire when minute stays the same."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        # Same minute - no close
        with mgr._lock:
            result = mgr._check_candle_close()
        assert result is False

    def test_candle_close_via_monitor_thread(self):
        """Monitor thread should fire candle close signal on minute change."""
        current_minute = [30]
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: current_minute[0],
            check_interval_ms=10,
        )

        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr.start()

        time.sleep(0.05)
        # Change minute
        current_minute[0] = 31
        time.sleep(0.1)

        mgr.stop()

        assert mgr.close_fired is True
        assert len(exit_signals) == 1
        assert exit_signals[0]["action"] == "CLOSE_FULL"
        assert exit_signals[0]["reason"] == "candle_close"
        assert exit_signals[0]["ticket"] == "T1"


class TestBreakevenLogic:
    """Test $5 profit breakeven at $1."""

    def test_be_triggers_at_5_profit_buy(self):
        """Should trigger BE move when profit >= $5 for BUY."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2005.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        # Price at entry + $5 = $2005
        result = mgr._check_breakeven(2005.0)
        assert result is True

    def test_be_triggers_at_5_profit_sell(self):
        """Should trigger BE move when profit >= $5 for SELL."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1995.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")

        # SELL: profit = entry - current = 2000 - 1995 = 5
        result = mgr._check_breakeven(1995.0)
        assert result is True

    def test_be_not_triggered_below_threshold(self):
        """Should NOT trigger BE when profit < $5."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2004.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        result = mgr._check_breakeven(2004.0)
        assert result is False

    def test_be_only_fires_once(self):
        """BE move should only fire once, not repeatedly."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2006.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        assert mgr._check_breakeven(2006.0) is True
        mgr._be_moved = True
        assert mgr._check_breakeven(2006.0) is False

    def test_be_sl_price_buy(self):
        """BE SL for BUY should be entry + $1."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2006.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        sl = mgr._get_be_sl_price()
        assert sl == 2001.0

    def test_be_sl_price_sell(self):
        """BE SL for SELL should be entry - $1."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1994.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        sl = mgr._get_be_sl_price()
        assert sl == 1999.0

    def test_be_fires_modify_sl_via_monitor(self):
        """Monitor thread should fire MODIFY_SL when BE threshold reached."""
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2006.0,
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: 30,
            check_interval_ms=10,
        )

        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr.start()

        time.sleep(0.1)
        mgr.stop()

        # Should have fired a MODIFY_SL
        sl_signals = [s for s in exit_signals if s["action"] == "MODIFY_SL"]
        assert len(sl_signals) >= 1
        assert sl_signals[0]["new_sl"] == 2001.0
        assert sl_signals[0]["reason"] == "breakeven_5_lock_1"


class TestReversalDetection:
    """Test high-momentum reversal detection."""

    def test_reversal_detected_sell_against_buy(self):
        """Should detect bearish reversal against a BUY position."""
        # Current bar: big bearish candle
        current_bar = {"Open": 2003.0, "High": 2003.5, "Low": 2001.5, "Close": 2001.6}
        # Body = |2001.6 - 2003.0| = 1.4 (>= 0.40)
        # Range = 2003.5 - 2001.5 = 2.0
        # Body ratio = 1.4 / 2.0 = 0.70 (>= 0.70)
        # Direction: close < open = SELL (against BUY)

        # Recent bars with smaller ranges for ATR comparison
        recent_bars = [
            {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},  # range 1.3
            {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},  # range 1.2
            {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},  # range 1.2
        ]
        # Avg range = (1.3 + 1.2 + 1.2) / 3 = 1.23
        # Current range 2.0 >= 1.5 * 1.23 = 1.85 -> YES

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.6,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
            get_current_bar_fn=lambda: current_bar,
            get_recent_bars_fn=lambda: recent_bars,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        result = mgr._check_reversal(2001.6)
        assert result is True

    def test_reversal_detected_buy_against_sell(self):
        """Should detect bullish reversal against a SELL position."""
        # Current bar: big bullish candle
        current_bar = {"Open": 1997.0, "High": 1998.5, "Low": 1996.5, "Close": 1998.4}
        # Body = |1998.4 - 1997.0| = 1.4 (>= 0.40)
        # Range = 1998.5 - 1996.5 = 2.0
        # Body ratio = 1.4 / 2.0 = 0.70 (>= 0.70)
        # Direction: close > open = BUY (against SELL)

        recent_bars = [
            {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},  # range 1.3
            {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},  # range 1.2
            {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},  # range 1.2
        ]

        mgr = CandleCloseManager(
            get_price_fn=lambda: 1998.4,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
            get_current_bar_fn=lambda: current_bar,
            get_recent_bars_fn=lambda: recent_bars,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")

        result = mgr._check_reversal(1998.4)
        assert result is True

    def test_no_reversal_when_candle_too_small(self):
        """Should NOT detect reversal when candle body is too small."""
        current_bar = {"Open": 2000.0, "High": 2000.5, "Low": 1999.7, "Close": 1999.8}
        # Body = |1999.8 - 2000.0| = 0.2 (< 0.40 min)

        recent_bars = [
            {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},
            {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},
            {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},
        ]

        mgr = CandleCloseManager(
            get_price_fn=lambda: 1999.8,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
            get_current_bar_fn=lambda: current_bar,
            get_recent_bars_fn=lambda: recent_bars,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        result = mgr._check_reversal(1999.8)
        assert result is False

    def test_no_reversal_when_same_direction(self):
        """Should NOT detect reversal when candle is in trade direction."""
        # Bullish candle for a BUY trade - not a reversal
        current_bar = {"Open": 2000.0, "High": 2002.5, "Low": 1999.5, "Close": 2002.4}

        recent_bars = [
            {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},
            {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},
            {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},
        ]

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2002.4,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
            get_current_bar_fn=lambda: current_bar,
            get_recent_bars_fn=lambda: recent_bars,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        result = mgr._check_reversal(2002.4)
        assert result is False

    def test_no_reversal_when_disabled(self):
        """Should NOT detect reversal when REVERSAL_DETECTION_ENABLED is False."""
        original = Config.REVERSAL_DETECTION_ENABLED
        try:
            Config.REVERSAL_DETECTION_ENABLED = False

            current_bar = {"Open": 2003.0, "High": 2003.5, "Low": 2001.5, "Close": 2001.6}
            recent_bars = [
                {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},
                {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},
                {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},
            ]

            mgr = CandleCloseManager(
                get_price_fn=lambda: 2001.6,
                write_exit_fn=lambda **kw: True,
                get_bar_minute_fn=lambda: 30,
                get_current_bar_fn=lambda: current_bar,
                get_recent_bars_fn=lambda: recent_bars,
            )
            mgr.start_tracking("BUY", 2000.0, "T1")

            result = mgr._check_reversal(2001.6)
            assert result is False
        finally:
            Config.REVERSAL_DETECTION_ENABLED = original

    def test_no_reversal_low_body_ratio(self):
        """Should NOT detect reversal when body ratio is too low (wick-heavy)."""
        # Big wick candle: body is small relative to range
        current_bar = {"Open": 2001.0, "High": 2003.0, "Low": 1999.0, "Close": 2000.8}
        # Body = |2000.8 - 2001.0| = 0.2
        # Range = 2003.0 - 1999.0 = 4.0
        # Body ratio = 0.2 / 4.0 = 0.05 (< 0.70)

        recent_bars = [
            {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},
            {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},
            {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},
        ]

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.8,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
            get_current_bar_fn=lambda: current_bar,
            get_recent_bars_fn=lambda: recent_bars,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        result = mgr._check_reversal(2000.8)
        assert result is False


class TestReversalFiresEarlyExit:
    """Test that reversal detection fires early CLOSE_FULL via monitor."""

    def test_reversal_fires_close_via_monitor(self):
        """Monitor thread should fire CLOSE_FULL on reversal detection."""
        current_bar = {"Open": 2003.0, "High": 2003.5, "Low": 2001.5, "Close": 2001.6}
        recent_bars = [
            {"Open": 2000.0, "High": 2000.8, "Low": 1999.5, "Close": 2000.5},
            {"Open": 2000.5, "High": 2001.0, "Low": 1999.8, "Close": 2000.8},
            {"Open": 2000.8, "High": 2001.2, "Low": 2000.0, "Close": 2001.0},
        ]

        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.6,
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: 30,
            get_current_bar_fn=lambda: current_bar,
            get_recent_bars_fn=lambda: recent_bars,
            check_interval_ms=10,
        )

        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr.start()

        time.sleep(0.1)
        mgr.stop()

        assert mgr.close_fired is True
        close_signals = [s for s in exit_signals if s["action"] == "CLOSE_FULL"]
        assert len(close_signals) >= 1
        assert close_signals[0]["reason"] == "reversal_detected"


class TestPnlComputation:
    """Test P&L computation."""

    def test_pnl_buy_profit(self):
        """BUY P&L should be current - entry."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2005.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        assert mgr._compute_pnl(2005.0) == 5.0

    def test_pnl_buy_loss(self):
        """BUY P&L should be negative when price drops."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1998.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        assert mgr._compute_pnl(1998.0) == -2.0

    def test_pnl_sell_profit(self):
        """SELL P&L should be entry - current."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1995.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        assert mgr._compute_pnl(1995.0) == 5.0

    def test_pnl_sell_loss(self):
        """SELL P&L should be negative when price rises."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2003.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        assert mgr._compute_pnl(2003.0) == -3.0


class TestConfigValues:
    """Test that config values are set correctly for candle-close system."""

    def test_candle_close_exit_enabled(self):
        assert Config.CANDLE_CLOSE_EXIT is True

    def test_no_tp_enabled(self):
        assert Config.NO_TP is True

    def test_swing_sl_lookback(self):
        assert Config.SWING_SL_LOOKBACK == 10

    def test_swing_sl_min_distance(self):
        assert Config.SWING_SL_MIN_DISTANCE == 0.50

    def test_breakeven_profit_threshold(self):
        assert Config.BREAKEVEN_PROFIT_THRESHOLD == 5.00

    def test_breakeven_lock_amount(self):
        assert Config.BREAKEVEN_LOCK_AMOUNT == 1.00

    def test_reversal_detection_enabled(self):
        assert Config.REVERSAL_DETECTION_ENABLED is True

    def test_reversal_candle_body_min(self):
        assert Config.REVERSAL_CANDLE_BODY_MIN == 0.40

    def test_reversal_candle_body_ratio(self):
        assert Config.REVERSAL_CANDLE_BODY_RATIO == 0.70

    def test_reversal_atr_mult(self):
        assert Config.REVERSAL_ATR_MULT == 1.5

    def test_max_positions_is_one(self):
        assert Config.MAX_POSITIONS == 1
