"""
Tests for NeuroX v9.0 Phase 3: Self-Optimizing Engine

Tests RollingTracker, TimeProfiler, and kelly_criterion.
"""

import json
import math
import pytest

from optimizer import RollingTracker, TimeProfiler, kelly_criterion
from performance import PositionSizer
from config import Config


# ============================================================
# kelly_criterion tests
# ============================================================

class TestKellyCriterion:
    """Tests for kelly_criterion function."""

    def test_basic_kelly(self):
        """60% win rate, $1 avg win, $0.50 avg loss = Kelly of 0.30, clamped to 0.25."""
        result = kelly_criterion(0.60, 1.0, 0.50)
        # Kelly = (0.60 * 1.0 - 0.40 * 0.50) / 1.0 = (0.60 - 0.20) / 1.0 = 0.40
        # Clamped to 0.25
        assert result == 0.25

    def test_kelly_moderate(self):
        """55% win rate, $0.80 avg win, $0.60 avg loss."""
        result = kelly_criterion(0.55, 0.80, 0.60)
        # Kelly = (0.55 * 0.80 - 0.45 * 0.60) / 0.80 = (0.44 - 0.27) / 0.80 = 0.2125
        assert abs(result - 0.2125) < 0.001

    def test_kelly_zero_win_rate(self):
        """0% win rate should return 0.0."""
        result = kelly_criterion(0.0, 1.0, 0.50)
        # Kelly = (0.0 * 1.0 - 1.0 * 0.50) / 1.0 = -0.50, clamped to 0.0
        assert result == 0.0

    def test_kelly_100_win_rate(self):
        """100% win rate."""
        result = kelly_criterion(1.0, 1.0, 0.50)
        # Kelly = (1.0 * 1.0 - 0.0 * 0.50) / 1.0 = 1.0, clamped to 0.25
        assert result == 0.25

    def test_kelly_zero_avg_win(self):
        """Zero avg win should return 0.0."""
        result = kelly_criterion(0.60, 0.0, 0.50)
        assert result == 0.0

    def test_kelly_negative_result_clamped(self):
        """Losing strategy should return 0.0."""
        result = kelly_criterion(0.30, 0.50, 1.0)
        # Kelly = (0.30 * 0.50 - 0.70 * 1.0) / 0.50 = (0.15 - 0.70) / 0.50 = -1.10
        # Clamped to 0.0
        assert result == 0.0

    def test_kelly_exact_breakeven(self):
        """Breakeven strategy should return 0.0."""
        result = kelly_criterion(0.50, 1.0, 1.0)
        # Kelly = (0.50 * 1.0 - 0.50 * 1.0) / 1.0 = 0.0
        assert result == 0.0

    def test_kelly_small_positive(self):
        """Slightly profitable strategy returns small fraction."""
        result = kelly_criterion(0.52, 1.0, 1.0)
        # Kelly = (0.52 * 1.0 - 0.48 * 1.0) / 1.0 = 0.04
        assert abs(result - 0.04) < 0.001

    def test_kelly_clamp_at_max(self):
        """High edge clamped at KELLY_MAX_FRACTION."""
        result = kelly_criterion(0.90, 2.0, 0.10)
        # Kelly = (0.90 * 2.0 - 0.10 * 0.10) / 2.0 = (1.80 - 0.01) / 2.0 = 0.895
        # Clamped to 0.25
        assert result == Config.KELLY_MAX_FRACTION


# ============================================================
# RollingTracker tests
# ============================================================

class TestRollingTracker:
    """Tests for RollingTracker class."""

    def test_empty_tracker(self):
        """Empty tracker returns safe defaults."""
        tracker = RollingTracker()
        assert tracker.get_win_rate() == 0.0
        assert tracker.get_avg_win() == 0.0
        assert tracker.get_avg_loss() == 0.0
        assert tracker.get_profit_factor() == 0.0
        assert tracker.get_trade_count() == 0

    def test_single_win(self):
        """Single winning trade."""
        tracker = RollingTracker()
        tracker.record_trade(profit=1.50, duration_seconds=5.0, hour=14, direction="BUY")
        assert tracker.get_win_rate() == 1.0
        assert tracker.get_avg_win() == 1.50
        assert tracker.get_avg_loss() == 0.0
        assert tracker.get_trade_count() == 1

    def test_single_loss(self):
        """Single losing trade."""
        tracker = RollingTracker()
        tracker.record_trade(profit=-0.80, duration_seconds=10.0, hour=10, direction="SELL")
        assert tracker.get_win_rate() == 0.0
        assert tracker.get_avg_win() == 0.0
        assert tracker.get_avg_loss() == 0.80
        assert tracker.get_trade_count() == 1

    def test_all_wins(self):
        """All winning trades."""
        tracker = RollingTracker(max_size=50)
        for i in range(20):
            tracker.record_trade(profit=0.50 + i * 0.01, duration_seconds=3.0,
                                 hour=12, direction="BUY")
        assert tracker.get_win_rate() == 1.0
        assert tracker.get_avg_win() > 0.0
        assert tracker.get_avg_loss() == 0.0
        assert tracker.get_profit_factor() == 999.0

    def test_all_losses(self):
        """All losing trades."""
        tracker = RollingTracker(max_size=50)
        for i in range(20):
            tracker.record_trade(profit=-0.30, duration_seconds=5.0,
                                 hour=9, direction="SELL")
        assert tracker.get_win_rate() == 0.0
        assert tracker.get_avg_win() == 0.0
        assert tracker.get_avg_loss() == 0.30
        assert tracker.get_profit_factor() == 0.0

    def test_mixed_trades(self):
        """Mixed winning and losing trades."""
        tracker = RollingTracker()
        # 6 wins, 4 losses = 60% win rate
        for _ in range(6):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=14, direction="BUY")
        for _ in range(4):
            tracker.record_trade(profit=-0.50, duration_seconds=8.0,
                                 hour=14, direction="SELL")

        assert tracker.get_win_rate() == 0.6
        assert tracker.get_avg_win() == 1.00
        assert tracker.get_avg_loss() == 0.50
        # Profit factor = 6.0 / 2.0 = 3.0
        assert tracker.get_profit_factor() == 3.0

    def test_rolling_window_eviction(self):
        """Trades beyond max_size are evicted."""
        tracker = RollingTracker(max_size=10)
        # Fill with losses
        for _ in range(10):
            tracker.record_trade(profit=-1.00, duration_seconds=5.0,
                                 hour=10, direction="SELL")
        assert tracker.get_win_rate() == 0.0

        # Now fill with wins (evicts losses)
        for _ in range(10):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=10, direction="BUY")
        assert tracker.get_win_rate() == 1.0
        assert tracker.get_trade_count() == 10

    def test_suggest_parameters_not_enough_data(self):
        """suggest_parameters returns defaults with < 10 trades."""
        tracker = RollingTracker()
        for _ in range(5):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=12, direction="BUY")
        result = tracker.suggest_parameters()
        assert result["MOMENTUM_THRESHOLD"] == Config.MOMENTUM_THRESHOLD
        assert result["TICK_MOMENTUM_THRESHOLD"] == Config.TICK_MOMENTUM_THRESHOLD
        assert result["COOLDOWN_SECONDS"] == Config.COOLDOWN_SECONDS

    def test_suggest_parameters_winning(self):
        """suggest_parameters tightens thresholds when win rate > 60%."""
        tracker = RollingTracker()
        # 8 wins, 2 losses = 80% win rate
        for _ in range(8):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=12, direction="BUY")
        for _ in range(2):
            tracker.record_trade(profit=-0.50, duration_seconds=5.0,
                                 hour=12, direction="SELL")
        result = tracker.suggest_parameters()
        # Should tighten by 10%
        assert result["MOMENTUM_THRESHOLD"] == round(Config.MOMENTUM_THRESHOLD * 0.90, 4)
        assert result["TICK_MOMENTUM_THRESHOLD"] == round(Config.TICK_MOMENTUM_THRESHOLD * 0.90, 4)

    def test_suggest_parameters_losing(self):
        """suggest_parameters widens thresholds when win rate < 40%."""
        tracker = RollingTracker()
        # 3 wins, 7 losses = 30% win rate
        for _ in range(3):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=12, direction="BUY")
        for _ in range(7):
            tracker.record_trade(profit=-0.50, duration_seconds=5.0,
                                 hour=12, direction="SELL")
        result = tracker.suggest_parameters()
        # Should widen by 20%
        assert result["MOMENTUM_THRESHOLD"] == round(Config.MOMENTUM_THRESHOLD * 1.20, 4)
        assert result["TICK_MOMENTUM_THRESHOLD"] == round(Config.TICK_MOMENTUM_THRESHOLD * 1.20, 4)

    def test_suggest_parameters_neutral(self):
        """suggest_parameters returns defaults for 40-60% win rate."""
        tracker = RollingTracker()
        # 5 wins, 5 losses = 50% win rate
        for _ in range(5):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=12, direction="BUY")
        for _ in range(5):
            tracker.record_trade(profit=-0.50, duration_seconds=5.0,
                                 hour=12, direction="SELL")
        result = tracker.suggest_parameters()
        assert result["MOMENTUM_THRESHOLD"] == Config.MOMENTUM_THRESHOLD
        assert result["TICK_MOMENTUM_THRESHOLD"] == Config.TICK_MOMENTUM_THRESHOLD
        assert result["COOLDOWN_SECONDS"] == Config.COOLDOWN_SECONDS

    def test_to_dict_serialization(self):
        """to_dict produces valid serializable data."""
        tracker = RollingTracker(max_size=10)
        tracker.record_trade(profit=1.50, duration_seconds=5.0,
                             hour=14, direction="BUY")
        tracker.record_trade(profit=-0.30, duration_seconds=8.0,
                             hour=14, direction="SELL")
        data = tracker.to_dict()
        assert "trades" in data
        assert "win_rate" in data
        assert "avg_win" in data
        assert "avg_loss" in data
        assert "profit_factor" in data
        assert "trade_count" in data
        assert data["trade_count"] == 2
        # Verify JSON serializable
        json.dumps(data)


# ============================================================
# TimeProfiler tests
# ============================================================

class TestTimeProfiler:
    """Tests for TimeProfiler class."""

    def test_empty_profiler(self):
        """Empty profiler returns neutral scores."""
        profiler = TimeProfiler()
        for hour in range(24):
            assert profiler.get_hour_score(hour) == 0.0
            assert profiler.get_aggression_mult(hour) == 1.0

    def test_profitable_hour(self):
        """Hour with profit gets positive score and higher aggression."""
        profiler = TimeProfiler()
        for _ in range(10):
            profiler.record_trade(14, 1.00)
        score = profiler.get_hour_score(14)
        assert score > 0.0
        mult = profiler.get_aggression_mult(14)
        assert mult > 1.0

    def test_losing_hour(self):
        """Hour with losses gets negative score and lower aggression."""
        profiler = TimeProfiler()
        for _ in range(10):
            profiler.record_trade(3, -0.80)
        score = profiler.get_hour_score(3)
        assert score < 0.0
        mult = profiler.get_aggression_mult(3)
        assert mult < 1.0

    def test_aggression_bounds(self):
        """Aggression multiplier stays within [0.5, 2.0]."""
        profiler = TimeProfiler()
        # Extreme profit
        for _ in range(100):
            profiler.record_trade(12, 10.0)
        mult = profiler.get_aggression_mult(12)
        assert 0.5 <= mult <= 2.0

        # Extreme loss
        for _ in range(100):
            profiler.record_trade(0, -10.0)
        mult = profiler.get_aggression_mult(0)
        assert 0.5 <= mult <= 2.0

    def test_hour_score_bounds(self):
        """Hour score stays within [-1.0, 1.0]."""
        profiler = TimeProfiler()
        for _ in range(100):
            profiler.record_trade(10, 50.0)
        score = profiler.get_hour_score(10)
        assert -1.0 <= score <= 1.0

        for _ in range(100):
            profiler.record_trade(5, -50.0)
        score = profiler.get_hour_score(5)
        assert -1.0 <= score <= 1.0

    def test_invalid_hour(self):
        """Invalid hour returns neutral values."""
        profiler = TimeProfiler()
        assert profiler.get_hour_score(-1) == 0.0
        assert profiler.get_hour_score(24) == 0.0
        assert profiler.get_aggression_mult(-1) == 1.0
        assert profiler.get_aggression_mult(24) == 1.0

    def test_multiple_hours_independent(self):
        """Different hours track independently."""
        profiler = TimeProfiler()
        profiler.record_trade(9, 2.00)   # Winning in hour 9
        profiler.record_trade(15, -1.00) # Losing in hour 15

        assert profiler.get_hour_score(9) > 0.0
        assert profiler.get_hour_score(15) < 0.0
        assert profiler.get_hour_score(12) == 0.0  # Untouched hour

    def test_breakeven_hour(self):
        """Breakeven hour returns near-zero score."""
        profiler = TimeProfiler()
        profiler.record_trade(10, 1.00)
        profiler.record_trade(10, -1.00)
        score = profiler.get_hour_score(10)
        assert abs(score) < 0.01  # Near zero

    def test_neutral_aggression_is_one(self):
        """When score is 0, aggression mult should be 1.0."""
        profiler = TimeProfiler()
        profiler.record_trade(10, 1.00)
        profiler.record_trade(10, -1.00)
        mult = profiler.get_aggression_mult(10)
        # Score is ~0, so mult should be ~1.0
        assert abs(mult - 1.0) < 0.05

    def test_to_dict(self):
        """to_dict serialization works."""
        profiler = TimeProfiler()
        profiler.record_trade(14, 1.50)
        data = profiler.to_dict()
        assert "buckets" in data
        assert len(data["buckets"]) == 24
        assert data["buckets"][14]["trade_count"] == 1
        assert data["buckets"][14]["total_profit"] == 1.50
        # JSON serializable
        json.dumps(data)

    def test_record_trade_invalid_hour_ignored(self):
        """Recording trade at invalid hour does not crash."""
        profiler = TimeProfiler()
        profiler.record_trade(-1, 1.00)  # Should not crash
        profiler.record_trade(25, 1.00)  # Should not crash
        # Verify no data was recorded
        for hour in range(24):
            assert profiler.get_hour_score(hour) == 0.0


# ============================================================
# PositionSizer Kelly Integration tests
# ============================================================

class TestPositionSizerKelly:
    """Tests for Kelly criterion integration in PositionSizer."""

    def test_kelly_lot_size_basic(self):
        """Kelly lot size with good edge."""
        sizer = PositionSizer()
        lot = sizer.get_kelly_lot_size(win_rate=0.60, avg_win=1.0, avg_loss=0.50)
        # Kelly = 0.25 (clamped), lot = 0.25 * 0.01 / 0.01 = 0.25
        # But capped at MAX_LOT_SIZE (0.05)
        assert lot == Config.MAX_LOT_SIZE

    def test_kelly_lot_size_small_edge(self):
        """Kelly lot size with small edge."""
        sizer = PositionSizer()
        lot = sizer.get_kelly_lot_size(win_rate=0.52, avg_win=1.0, avg_loss=1.0)
        # Kelly = 0.04, lot = 0.04 * 0.10 / 0.01 = 0.40
        assert lot == 0.40

    def test_kelly_lot_size_no_edge(self):
        """Kelly lot size with no edge returns min."""
        sizer = PositionSizer()
        lot = sizer.get_kelly_lot_size(win_rate=0.50, avg_win=1.0, avg_loss=1.0)
        # Kelly = 0.0, returns MIN_LOT_SIZE
        assert lot == Config.MIN_LOT_SIZE

    def test_kelly_lot_size_negative_edge(self):
        """Kelly lot size with negative edge returns min."""
        sizer = PositionSizer()
        lot = sizer.get_kelly_lot_size(win_rate=0.30, avg_win=0.50, avg_loss=1.0)
        assert lot == Config.MIN_LOT_SIZE

    def test_get_lot_size_with_kelly_enabled(self):
        """get_lot_size uses Kelly when enabled and data provided."""
        sizer = PositionSizer()
        sizer.enable_kelly(True)
        lot = sizer.get_lot_size(win_rate=0.52, avg_win=1.0, avg_loss=1.0)
        # Kelly = 0.04, lot = 0.04 * 0.10 / 0.01 = 0.40
        assert lot == 0.40

    def test_get_lot_size_without_kelly(self):
        """get_lot_size falls back to streak-based without Kelly."""
        sizer = PositionSizer()
        lot = sizer.get_lot_size()
        assert lot == Config.BASE_LOT_SIZE

    def test_get_lot_size_kelly_disabled(self):
        """get_lot_size ignores Kelly data when disabled."""
        sizer = PositionSizer()
        sizer.enable_kelly(False)
        lot = sizer.get_lot_size(win_rate=0.70, avg_win=2.0, avg_loss=0.50)
        # Should use streak-based (base lot)
        assert lot == Config.BASE_LOT_SIZE

    def test_kelly_enabled_property(self):
        """Kelly enabled flag works correctly."""
        sizer = PositionSizer()
        assert sizer.kelly_enabled is False
        sizer.enable_kelly(True)
        assert sizer.kelly_enabled is True
        sizer.enable_kelly(False)
        assert sizer.kelly_enabled is False


# ============================================================
# Integration tests
# ============================================================

class TestPhase3Integration:
    """Integration tests for Phase 3 components working together."""

    def test_tracker_feeds_kelly(self):
        """RollingTracker data feeds Kelly criterion correctly."""
        tracker = RollingTracker(max_size=50)
        # 60% win rate with specific amounts
        for _ in range(6):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=14, direction="BUY")
        for _ in range(4):
            tracker.record_trade(profit=-0.50, duration_seconds=8.0,
                                 hour=14, direction="SELL")

        kelly = kelly_criterion(
            tracker.get_win_rate(),
            tracker.get_avg_win(),
            tracker.get_avg_loss()
        )
        # Win rate = 0.6, avg_win = 1.0, avg_loss = 0.5
        # Kelly = (0.6 * 1.0 - 0.4 * 0.5) / 1.0 = 0.40, clamped to 0.25
        assert kelly == 0.25

    def test_profiler_with_tracker_data(self):
        """TimeProfiler and RollingTracker work together."""
        tracker = RollingTracker(max_size=50)
        profiler = TimeProfiler()

        # Simulate trades at different hours
        for _ in range(5):
            tracker.record_trade(profit=1.00, duration_seconds=5.0,
                                 hour=14, direction="BUY")
            profiler.record_trade(14, 1.00)

        for _ in range(5):
            tracker.record_trade(profit=-0.80, duration_seconds=5.0,
                                 hour=3, direction="SELL")
            profiler.record_trade(3, -0.80)

        # Hour 14 should be profitable, hour 3 should be losing
        assert profiler.get_aggression_mult(14) > 1.0
        assert profiler.get_aggression_mult(3) < 1.0

    def test_config_phase3_params_exist(self):
        """All Phase 3 config parameters exist."""
        assert hasattr(Config, "ROLLING_TRACKER_SIZE")
        assert hasattr(Config, "KELLY_MAX_FRACTION")
        assert hasattr(Config, "KELLY_MIN_FRACTION")
        assert hasattr(Config, "TIME_PROFILE_ENABLED")
        assert hasattr(Config, "AUTO_TUNE_ENABLED")
        assert hasattr(Config, "PERFORMANCE_FILE")
        assert Config.ROLLING_TRACKER_SIZE == 100
        assert Config.KELLY_MAX_FRACTION == 0.25
        assert Config.KELLY_MIN_FRACTION == 0.01
        assert Config.TIME_PROFILE_ENABLED is True
        assert Config.AUTO_TUNE_ENABLED is True
        assert Config.PERFORMANCE_FILE == "neurox_v9_performance.json"
