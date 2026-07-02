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
        """Monitor thread should fire candle close signal on minute change when in profit."""
        current_minute = [30]
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.10,  # Small profit: PnL = 0.10 * 10 = $1 (above 0, below BE)
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

    def test_candle_close_does_not_fire_when_in_loss(self):
        """Monitor thread should NOT fire candle close when trade is in loss."""
        current_minute = [30]
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 1999.0,  # BUY at 2000, price is below -> in loss
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: current_minute[0],
            check_interval_ms=10,
        )

        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr.start()

        time.sleep(0.05)
        # Change minute - candle close detected but trade is in loss
        current_minute[0] = 31
        time.sleep(0.1)

        mgr.stop()

        # Should NOT fire close when in loss - SL protects downside
        assert mgr.close_fired is False
        assert len(exit_signals) == 0
        # Trade should still be tracking (kept running)
        assert mgr.is_tracking is True


class TestBreakevenLogic:
    """Test $5 profit breakeven at $1.

    With LOT_SIZE=0.10 and CONTRACT_SIZE=100, the multiplier is 10.
    So a $0.50 price move = $5.00 actual PnL (meets the $5 threshold).
    """

    def test_be_triggers_at_5_profit_buy(self):
        """Should trigger BE move when actual PnL >= $5 for BUY.

        Price must move $0.50 for actual PnL = 0.50 * 0.10 * 100 = $5.00.
        """
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.50,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        # Price at entry + $0.50 -> PnL = 0.50 * 10 = $5.00
        result = mgr._check_breakeven(2000.50)
        assert result is True

    def test_be_triggers_at_5_profit_sell(self):
        """Should trigger BE move when actual PnL >= $5 for SELL.

        SELL: price must drop $0.50 for actual PnL = 0.50 * 0.10 * 100 = $5.00.
        """
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1999.50,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")

        # SELL: profit = entry - current = 2000 - 1999.50 = 0.50
        # Actual PnL = 0.50 * 10 = $5.00
        result = mgr._check_breakeven(1999.50)
        assert result is True

    def test_be_not_triggered_below_threshold(self):
        """Should NOT trigger BE when actual PnL < $5.

        A $0.40 price move = 0.40 * 10 = $4.00 actual PnL (below $5 threshold).
        """
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.40,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        result = mgr._check_breakeven(2000.40)
        assert result is False

    def test_be_only_fires_once(self):
        """BE move should only fire once, not repeatedly."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")

        # $1.0 price move = $10 PnL -> triggers
        assert mgr._check_breakeven(2001.0) is True
        mgr._be_moved = True
        assert mgr._check_breakeven(2001.0) is False

    def test_be_sl_price_buy(self):
        """BE SL for BUY should be entry + $1."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
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
        """Monitor thread should fire MODIFY_SL when BE threshold reached.

        With 0.10 lots * 100 contract = 10x multiplier.
        Price at 2000.60 -> PnL = 0.60 * 10 = $6.00 (above $5 threshold).
        """
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2000.60,
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
    """Test P&L computation (actual dollar PnL = price_diff * lot_size * contract_size)."""

    def test_pnl_buy_profit(self):
        """BUY P&L should be (current - entry) * lot_size * contract_size."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2005.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        # price_diff=5.0, lot=0.10, contract=100 -> 5.0 * 10 = 50.0
        assert mgr._compute_pnl(2005.0) == 5.0 * Config.LOT_SIZE * Config.CONTRACT_SIZE

    def test_pnl_buy_loss(self):
        """BUY P&L should be negative when price drops."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1998.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        # price_diff=-2.0, lot=0.10, contract=100 -> -2.0 * 10 = -20.0
        assert mgr._compute_pnl(1998.0) == -2.0 * Config.LOT_SIZE * Config.CONTRACT_SIZE

    def test_pnl_sell_profit(self):
        """SELL P&L should be (entry - current) * lot_size * contract_size."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1995.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        # price_diff=5.0, lot=0.10, contract=100 -> 5.0 * 10 = 50.0
        assert mgr._compute_pnl(1995.0) == 5.0 * Config.LOT_SIZE * Config.CONTRACT_SIZE

    def test_pnl_sell_loss(self):
        """SELL P&L should be negative when price rises."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2003.0,
            write_exit_fn=lambda **kw: True,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        # price_diff=-3.0, lot=0.10, contract=100 -> -3.0 * 10 = -30.0
        assert mgr._compute_pnl(2003.0) == -3.0 * Config.LOT_SIZE * Config.CONTRACT_SIZE

    def test_pnl_no_direction(self):
        """P&L should be 0 when no direction is set."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2003.0,
            write_exit_fn=lambda **kw: True,
        )
        # Don't start tracking - direction is None
        assert mgr._compute_pnl(2003.0) == 0.0


class TestConfigValues:
    """Test that config values are set correctly for candle-close system."""

    def test_candle_close_exit_enabled(self):
        assert Config.CANDLE_CLOSE_EXIT is True

    def test_no_tp_enabled(self):
        assert Config.NO_TP is True

    def test_swing_sl_lookback(self):
        assert Config.SWING_SL_LOOKBACK == 10

    def test_swing_sl_min_distance(self):
        assert Config.SWING_SL_MIN_DISTANCE == 5.00

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

    def test_contract_size(self):
        assert Config.CONTRACT_SIZE == 100

    def test_lot_size(self):
        assert Config.LOT_SIZE == 0.10

    def test_trail_distance_after_be(self):
        assert Config.TRAIL_DISTANCE_AFTER_BE == 1.50


class TestTightTrailingAfterBreakeven:
    """Test tight trailing stop that activates after breakeven is applied."""

    def test_trail_not_active_before_be(self):
        """Trailing should not compute SL when BE has not been applied."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        # BE not moved yet
        assert mgr._be_moved is False
        result = mgr._compute_trail_sl(2001.0)
        assert result is None

    def test_trail_buy_moves_sl_up(self):
        """After BE on BUY, trail should move SL up as price moves up."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2002.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr._be_moved = True
        mgr._last_trail_sl = 2001.0  # BE SL level

        # Price at 2002.0 -> trail SL = 2002.0 - 1.50 = 2000.50
        # But BE SL is 2001.0 (entry + $1), trail must be above that
        # 2000.50 < 2001.0 -> no move
        result = mgr._compute_trail_sl(2002.0)
        assert result is None

    def test_trail_buy_moves_above_be_level(self):
        """Trail should return new SL when it exceeds BE SL and last trail SL."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2003.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr._be_moved = True
        mgr._last_trail_sl = 2001.0  # BE SL level (entry + $1)

        # Price at 2003.0 -> trail SL = 2003.0 - 1.50 = 2001.50
        # 2001.50 > max(BE SL=2001.0, last_trail=2001.0) = 2001.0 -> MOVE
        result = mgr._compute_trail_sl(2003.0)
        assert result == 2003.0 - Config.TRAIL_DISTANCE_AFTER_BE  # 2001.50

    def test_trail_buy_never_widens(self):
        """Trail SL on BUY should never move below current trail level."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2002.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr._be_moved = True
        mgr._last_trail_sl = 2001.80  # Previously trailed to 2001.80

        # Price drops to 2002.0 -> trail SL = 2002.0 - 1.50 = 2000.50
        # 2000.50 < last_trail_sl=2001.80 -> no move (would widen)
        result = mgr._compute_trail_sl(2002.0)
        assert result is None

    def test_trail_sell_moves_sl_down(self):
        """After BE on SELL, trail should move SL down as price moves down."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1997.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        mgr._be_moved = True
        mgr._last_trail_sl = 0.0  # Not yet trailed

        # BE SL for SELL = entry - $1 = 1999.0
        # Price at 1997.0 -> trail SL = 1997.0 + 1.50 = 1998.50
        # 1998.50 < min(BE_SL=1999.0, no last trail) = 1999.0 -> MOVE
        result = mgr._compute_trail_sl(1997.0)
        assert result == 1997.0 + Config.TRAIL_DISTANCE_AFTER_BE  # 1998.50

    def test_trail_sell_never_widens(self):
        """Trail SL on SELL should never move above current trail level."""
        mgr = CandleCloseManager(
            get_price_fn=lambda: 1998.0,
            write_exit_fn=lambda **kw: True,
            get_bar_minute_fn=lambda: 30,
        )
        mgr.start_tracking("SELL", 2000.0, "T1")
        mgr._be_moved = True
        mgr._last_trail_sl = 1998.20  # Previously trailed to 1998.20

        # Price at 1998.0 -> trail SL = 1998.0 + 1.50 = 1999.50
        # 1999.50 > last_trail_sl=1998.20 -> no move (would widen)
        result = mgr._compute_trail_sl(1998.0)
        assert result is None

    def test_trail_fires_modify_sl_via_monitor(self):
        """Monitor thread should fire MODIFY_SL for trailing after BE."""
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2003.0,  # BUY at 2000, price = 2003
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: 30,
            check_interval_ms=10,
        )

        mgr.start_tracking("BUY", 2000.0, "T1")
        # Simulate BE already applied
        mgr._be_moved = True
        mgr._last_trail_sl = 2001.0  # BE SL

        mgr.start()
        time.sleep(0.1)
        mgr.stop()

        # Should have fired a MODIFY_SL for trailing
        trail_signals = [s for s in exit_signals if s.get("reason") == "tight_trail_after_be"]
        assert len(trail_signals) >= 1
        # Trail SL = 2003.0 - 1.50 = 2001.50
        assert trail_signals[0]["new_sl"] == 2001.50
        assert trail_signals[0]["action"] == "MODIFY_SL"

    def test_trail_updates_last_trail_sl(self):
        """After trailing fires, _last_trail_sl should be updated."""
        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2003.0,
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: 30,
            check_interval_ms=10,
        )

        mgr.start_tracking("BUY", 2000.0, "T1")
        mgr._be_moved = True
        mgr._last_trail_sl = 2001.0

        mgr.start()
        time.sleep(0.1)
        mgr.stop()

        # _last_trail_sl should have been updated
        assert mgr._last_trail_sl == 2001.50


class TestCandleCloseWithSystemTime:
    """Test that candle close detection works using system time fallback."""

    def test_candle_close_works_without_bar_minute_fn(self):
        """Candle close should detect minute changes using system time even without bar_minute_fn."""
        from unittest.mock import patch
        from datetime import datetime as dt

        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,  # In profit
            write_exit_fn=write_exit,
            get_bar_minute_fn=None,  # No bar minute function
            check_interval_ms=10,
        )

        # Patch datetime.now() to simulate minute change
        fake_time_1 = dt(2025, 7, 3, 10, 30, 50)  # minute=30
        fake_time_2 = dt(2025, 7, 3, 10, 31, 0)   # minute=31

        with patch("trailing_stop.datetime") as mock_dt:
            mock_dt.now.return_value = fake_time_1
            mgr.start_tracking("BUY", 2000.0, "T1")

            # First check - same minute, no close
            with mgr._lock:
                result = mgr._check_candle_close()
            assert result is False

            # Change to new minute
            mock_dt.now.return_value = fake_time_2
            with mgr._lock:
                result = mgr._check_candle_close()
            assert result is True

    def test_candle_close_system_time_fires_even_if_bar_minute_stale(self):
        """If tick collector bar minute is stale, system time still detects candle close."""
        from unittest.mock import patch
        from datetime import datetime as dt

        exit_signals = []

        def write_exit(**kwargs):
            exit_signals.append(kwargs)
            return True

        # bar_minute_fn always returns 30 (stale - tick collector not updating)
        mgr = CandleCloseManager(
            get_price_fn=lambda: 2001.0,
            write_exit_fn=write_exit,
            get_bar_minute_fn=lambda: 30,  # Stale!
            check_interval_ms=10,
        )

        fake_time_1 = dt(2025, 7, 3, 10, 30, 50)
        fake_time_2 = dt(2025, 7, 3, 10, 31, 0)

        with patch("trailing_stop.datetime") as mock_dt:
            mock_dt.now.return_value = fake_time_1
            mgr.start_tracking("BUY", 2000.0, "T1")

            # Same minute
            with mgr._lock:
                result = mgr._check_candle_close()
            assert result is False

            # System minute changes even though bar_minute stays 30
            mock_dt.now.return_value = fake_time_2
            with mgr._lock:
                result = mgr._check_candle_close()
            assert result is True
