"""Tests for performance.py - Position sizing based on trade outcomes."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from performance import PositionSizer
from config import Config


class TestPositionSizerInit:
    """Test PositionSizer initialization."""

    def test_initial_lot_size(self):
        """Should start at BASE_LOT_SIZE."""
        ps = PositionSizer()
        assert ps.get_lot_size() == Config.BASE_LOT_SIZE

    def test_initial_streaks_zero(self):
        """Initial win/loss streaks should be zero."""
        ps = PositionSizer()
        assert ps.consecutive_wins == 0
        assert ps.consecutive_losses == 0

    def test_initial_total_trades(self):
        """Initial total trades should be zero."""
        ps = PositionSizer()
        assert ps.total_trades == 0


class TestPositionSizerWinStreak:
    """Test lot size increase after win streaks."""

    def test_lot_increases_after_3_wins(self):
        """After 3 consecutive wins, lot should increase by 1.5x."""
        ps = PositionSizer()
        ps.record_trade(True, 0.50)
        ps.record_trade(True, 0.30)
        ps.record_trade(True, 0.40)
        # After 3 wins: 0.01 * 1.5 = 0.015 -> rounds to 0.01 (2 decimals)
        expected = round(Config.BASE_LOT_SIZE * Config.LOT_INCREASE_MULT, 2)
        assert ps.get_lot_size() == expected

    def test_lot_does_not_increase_after_2_wins(self):
        """After only 2 wins, lot should stay at base."""
        ps = PositionSizer()
        ps.record_trade(True, 0.50)
        ps.record_trade(True, 0.30)
        assert ps.get_lot_size() == Config.BASE_LOT_SIZE

    def test_win_streak_resets_after_increase(self):
        """After a lot increase, win streak counter should reset."""
        ps = PositionSizer()
        # 3 wins -> increase
        for _ in range(3):
            ps.record_trade(True, 0.50)
        assert ps.consecutive_wins == 0  # Reset after increase

    def test_double_win_streak_compounds(self):
        """Two full win streaks should compound the lot increase."""
        ps = PositionSizer()
        # First streak: 3 wins -> 0.01 * 1.5 = 0.015
        for _ in range(3):
            ps.record_trade(True, 0.50)
        # Second streak: 3 more wins -> 0.015 * 1.5 = 0.0225 -> rounds to 0.02
        for _ in range(3):
            ps.record_trade(True, 0.50)
        expected = round(Config.BASE_LOT_SIZE * Config.LOT_INCREASE_MULT * Config.LOT_INCREASE_MULT, 2)
        assert ps.get_lot_size() == expected

    def test_lot_capped_at_max(self):
        """Lot should never exceed MAX_LOT_SIZE."""
        ps = PositionSizer()
        # Force many win streaks to push lot above max
        for _ in range(30):
            ps.record_trade(True, 1.0)
        assert ps.get_lot_size() <= Config.MAX_LOT_SIZE

    def test_config_win_streak_increase(self):
        """Config should have WIN_STREAK_INCREASE = 3."""
        assert Config.WIN_STREAK_INCREASE == 3

    def test_config_lot_increase_mult(self):
        """Config should have LOT_INCREASE_MULT = 1.5."""
        assert Config.LOT_INCREASE_MULT == 1.5


class TestPositionSizerLossStreak:
    """Test lot size decrease after loss streaks."""

    def test_lot_decreases_after_2_losses(self):
        """After 2 consecutive losses, lot should decrease by 0.5x."""
        ps = PositionSizer()
        ps.record_trade(False, -0.50)
        ps.record_trade(False, -0.30)
        # After 2 losses: 0.01 * 0.5 = 0.005 -> clamped to MIN_LOT_SIZE (0.01)
        assert ps.get_lot_size() == Config.MIN_LOT_SIZE

    def test_lot_does_not_decrease_after_1_loss(self):
        """After only 1 loss, lot should stay at current level."""
        ps = PositionSizer()
        ps.record_trade(False, -0.50)
        assert ps.get_lot_size() == Config.BASE_LOT_SIZE

    def test_loss_streak_resets_after_decrease(self):
        """After a lot decrease, loss streak counter should reset."""
        ps = PositionSizer()
        ps.record_trade(False, -0.50)
        ps.record_trade(False, -0.30)
        assert ps.consecutive_losses == 0  # Reset after decrease

    def test_lot_floored_at_min(self):
        """Lot should never go below MIN_LOT_SIZE."""
        ps = PositionSizer()
        # Many losses to push lot below floor
        for _ in range(20):
            ps.record_trade(False, -0.50)
        assert ps.get_lot_size() >= Config.MIN_LOT_SIZE

    def test_config_loss_streak_decrease(self):
        """Config should have LOSS_STREAK_DECREASE = 2."""
        assert Config.LOSS_STREAK_DECREASE == 2

    def test_config_lot_decrease_mult(self):
        """Config should have LOT_DECREASE_MULT = 0.5."""
        assert Config.LOT_DECREASE_MULT == 0.5


class TestPositionSizerMixed:
    """Test mixed win/loss scenarios."""

    def test_win_resets_loss_streak(self):
        """A win should reset the loss streak counter."""
        ps = PositionSizer()
        ps.record_trade(False, -0.50)  # 1 loss
        ps.record_trade(True, 0.30)   # win resets
        assert ps.consecutive_losses == 0
        assert ps.consecutive_wins == 1

    def test_loss_resets_win_streak(self):
        """A loss should reset the win streak counter."""
        ps = PositionSizer()
        ps.record_trade(True, 0.50)   # 1 win
        ps.record_trade(True, 0.30)   # 2 wins
        ps.record_trade(False, -0.20) # loss resets
        assert ps.consecutive_wins == 0
        assert ps.consecutive_losses == 1
        # Lot should still be at base (2 wins not enough for increase)
        assert ps.get_lot_size() == Config.BASE_LOT_SIZE

    def test_increase_then_decrease(self):
        """Win streak increase followed by loss streak decrease."""
        ps = PositionSizer()
        # 3 wins -> 0.01 * 1.5 = 0.015 -> rounds to 0.01
        for _ in range(3):
            ps.record_trade(True, 0.50)
        increased_lot = ps.get_lot_size()
        # 2 losses -> decreased by 0.5
        ps.record_trade(False, -0.30)
        ps.record_trade(False, -0.30)
        decreased_lot = ps.get_lot_size()
        # Decreased lot should be less than or equal to increased_lot
        assert decreased_lot <= increased_lot

    def test_alternating_win_loss_no_change(self):
        """Alternating win/loss should keep lot at base."""
        ps = PositionSizer()
        for _ in range(10):
            ps.record_trade(True, 0.30)
            ps.record_trade(False, -0.20)
        # Never reaches 3 consecutive wins or 2 consecutive losses
        assert ps.get_lot_size() == Config.BASE_LOT_SIZE

    def test_total_trades_count(self):
        """Total trades should count all recorded trades."""
        ps = PositionSizer()
        ps.record_trade(True, 0.50)
        ps.record_trade(False, -0.20)
        ps.record_trade(True, 0.30)
        assert ps.total_trades == 3

    def test_win_rate(self):
        """Win rate should be correctly computed."""
        ps = PositionSizer()
        ps.record_trade(True, 0.50)
        ps.record_trade(True, 0.30)
        ps.record_trade(False, -0.20)
        assert abs(ps.win_rate - 2.0/3.0) < 0.001

    def test_total_profit(self):
        """Total profit should accumulate correctly."""
        ps = PositionSizer()
        ps.record_trade(True, 0.50)
        ps.record_trade(False, -0.20)
        ps.record_trade(True, 0.30)
        assert abs(ps.total_profit - 0.60) < 0.001


class TestPositionSizerBounds:
    """Test lot size bounds enforcement."""

    def test_config_base_lot(self):
        """Config should have BASE_LOT_SIZE = 0.10."""
        assert Config.BASE_LOT_SIZE == 0.10

    def test_config_max_lot(self):
        """Config should have MAX_LOT_SIZE = 0.50."""
        assert Config.MAX_LOT_SIZE == 0.50

    def test_config_min_lot(self):
        """Config should have MIN_LOT_SIZE = 0.10."""
        assert Config.MIN_LOT_SIZE == 0.10

    def test_lot_never_negative(self):
        """Lot size should never be negative regardless of losses."""
        ps = PositionSizer()
        for _ in range(100):
            ps.record_trade(False, -1.0)
        assert ps.get_lot_size() > 0

    def test_lot_max_after_many_wins(self):
        """After many wins, lot should cap at MAX_LOT_SIZE."""
        ps = PositionSizer()
        # Enough win streaks to reach max
        for _ in range(30):
            ps.record_trade(True, 1.0)
        assert ps.get_lot_size() == Config.MAX_LOT_SIZE

    def test_large_win_streak_then_recovery(self):
        """Starting from max lot, losses should bring it down, then wins back up."""
        ps = PositionSizer()
        # Get to max
        for _ in range(30):
            ps.record_trade(True, 1.0)
        assert ps.get_lot_size() == Config.MAX_LOT_SIZE

        # Losses bring it down
        ps.record_trade(False, -1.0)
        ps.record_trade(False, -1.0)
        after_losses = ps.get_lot_size()
        assert after_losses < Config.MAX_LOT_SIZE

        # Wins bring it back up
        for _ in range(3):
            ps.record_trade(True, 1.0)
        after_wins = ps.get_lot_size()
        assert after_wins > after_losses
