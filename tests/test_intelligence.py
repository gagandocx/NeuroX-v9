"""Tests for intelligence.py - Predictive Intelligence module."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from intelligence import (
    compute_acceleration,
    compute_weighted_tick_direction,
    detect_micro_patterns,
    compute_adaptive_thresholds,
)
from config import Config


class TestComputeAcceleration:
    """Test price acceleration (2nd derivative) detection."""

    def test_accelerating_upward(self):
        """Increasing positive moves should be ACCELERATING."""
        # Prices with increasing velocity: moves get bigger each tick
        prices = [100.0, 100.01, 100.03, 100.06, 100.10, 100.15, 100.21, 100.28, 100.36, 100.45]
        state, value = compute_acceleration(prices, lookback=10)
        assert state == "ACCELERATING"
        assert value > 0

    def test_decelerating_upward(self):
        """Decreasing positive moves should be DECELERATING."""
        # Prices with decreasing velocity: moves get smaller each tick
        prices = [100.0, 100.20, 100.35, 100.45, 100.52, 100.57, 100.60, 100.62, 100.63, 100.635]
        state, value = compute_acceleration(prices, lookback=10)
        assert state == "DECELERATING"
        assert value < 0

    def test_stable_constant_velocity(self):
        """Constant velocity should be STABLE."""
        # Prices with constant increments (zero acceleration)
        prices = [100.0 + i * 0.05 for i in range(10)]
        state, value = compute_acceleration(prices, lookback=10)
        assert state == "STABLE"

    def test_insufficient_data_stable(self):
        """With fewer ticks than lookback, should return STABLE."""
        prices = [100.0, 100.10, 100.20]
        state, value = compute_acceleration(prices, lookback=10)
        assert state == "STABLE"
        assert value == 0.0

    def test_empty_data(self):
        """Empty price list should return STABLE."""
        state, value = compute_acceleration([], lookback=10)
        assert state == "STABLE"
        assert value == 0.0

    def test_accelerating_downward(self):
        """Increasing negative moves (accelerating downtrend)."""
        # Prices dropping faster and faster
        prices = [100.0, 99.99, 99.97, 99.94, 99.90, 99.85, 99.79, 99.72, 99.64, 99.55]
        state, value = compute_acceleration(prices, lookback=10)
        # This is decelerating (price is moving down faster -> negative acceleration of momentum)
        # Actually, the velocity is increasingly negative, so acceleration is negative
        assert state == "DECELERATING"
        assert value < 0

    def test_uses_config_lookback_default(self):
        """Should use Config.ACCELERATION_LOOKBACK when no lookback specified."""
        assert Config.ACCELERATION_LOOKBACK == 10
        prices = [100.0 + i * 0.05 for i in range(15)]
        state, _ = compute_acceleration(prices)
        assert state == "STABLE"

    def test_lookback_parameter_override(self):
        """Custom lookback should override Config default."""
        # With lookback=5, use only last 5 ticks
        prices = [100.0, 100.1, 100.2, 100.3, 100.4,   # constant vel
                  100.4, 100.45, 100.55, 100.70, 100.90]  # accelerating
        state, value = compute_acceleration(prices, lookback=5)
        assert state == "ACCELERATING"


class TestComputeWeightedTickDirection:
    """Test volume-weighted tick direction analysis."""

    def test_strong_buy_bias(self):
        """Large upward moves should produce BUY with positive score."""
        # Mix of large up moves and small down moves
        prices = [100.0]
        for i in range(19):
            if i % 3 == 0:
                prices.append(prices[-1] - 0.01)  # tiny down
            else:
                prices.append(prices[-1] + 0.20)  # large up
        direction, score = compute_weighted_tick_direction(prices, lookback=20)
        assert direction == "BUY"
        assert score > 0

    def test_strong_sell_bias(self):
        """Large downward moves should produce SELL with negative score."""
        prices = [100.0]
        for i in range(19):
            if i % 3 == 0:
                prices.append(prices[-1] + 0.01)  # tiny up
            else:
                prices.append(prices[-1] - 0.20)  # large down
        direction, score = compute_weighted_tick_direction(prices, lookback=20)
        assert direction == "SELL"
        assert score < 0

    def test_balanced_moves_flat(self):
        """Equal up/down moves should produce FLAT."""
        prices = [100.0]
        for i in range(19):
            if i % 2 == 0:
                prices.append(prices[-1] + 0.05)
            else:
                prices.append(prices[-1] - 0.05)
        direction, score = compute_weighted_tick_direction(prices, lookback=20)
        assert direction == "FLAT"

    def test_insufficient_data(self):
        """Not enough ticks should return FLAT."""
        prices = [100.0, 100.10]
        direction, score = compute_weighted_tick_direction(prices, lookback=20)
        assert direction == "FLAT"
        assert score == 0.0

    def test_weight_by_magnitude(self):
        """A single large move should outweigh many small moves in opposite direction."""
        # 15 small down moves of $0.01 each, then 4 large up moves of $0.20 each
        prices = [100.0]
        for _ in range(15):
            prices.append(prices[-1] - 0.01)
        for _ in range(4):
            prices.append(prices[-1] + 0.20)
        direction, score = compute_weighted_tick_direction(prices, lookback=20)
        # The large up moves should dominate
        assert direction == "BUY"
        assert score > 0

    def test_uses_config_lookback_default(self):
        """Should use Config.WEIGHTED_TICK_LOOKBACK when no lookback specified."""
        assert Config.WEIGHTED_TICK_LOOKBACK == 20


class TestDetectMicroPatterns:
    """Test micro-pattern recognition from tick data."""

    def test_v_reversal_bullish(self):
        """Sharp drop followed by sharp recovery should detect bullish V-reversal."""
        # Start high, drop sharply, then recover
        prices = []
        start = 100.0
        # First half: drop
        for i in range(15):
            prices.append(start - i * 0.02)  # drop $0.30 total
        # Second half: recover
        low = prices[-1]
        for i in range(15):
            prices.append(low + i * 0.02)  # recover $0.28

        patterns = detect_micro_patterns(prices, lookback=30)
        pattern_types = [(p["pattern"], p["direction"]) for p in patterns]
        assert ("v_reversal", "BUY") in pattern_types

    def test_v_reversal_bearish(self):
        """Sharp rise followed by sharp drop should detect bearish V-reversal."""
        prices = []
        start = 100.0
        # First half: rise
        for i in range(15):
            prices.append(start + i * 0.02)  # rise $0.28
        # Second half: drop
        high = prices[-1]
        for i in range(15):
            prices.append(high - i * 0.02)  # drop $0.28

        patterns = detect_micro_patterns(prices, lookback=30)
        pattern_types = [(p["pattern"], p["direction"]) for p in patterns]
        assert ("v_reversal", "SELL") in pattern_types

    def test_double_top_bearish(self):
        """Two peaks at similar levels should detect double-top (SELL)."""
        prices = []
        # First peak: rise to 100.30 then drop
        for i in range(5):
            prices.append(100.0 + i * 0.075)  # rise to 100.30
        for i in range(1, 6):
            prices.append(100.30 - i * 0.04)  # dip to 100.10
        # Valley
        for i in range(5):
            prices.append(100.10 + i * 0.01)  # slight up
        # Second peak: rise to ~100.30 then drop
        for i in range(5):
            prices.append(100.15 + i * 0.035)  # rise to ~100.325
        for i in range(1, 11):
            prices.append(100.325 - i * 0.02)  # drop

        patterns = detect_micro_patterns(prices, lookback=30)
        pattern_types = [(p["pattern"], p["direction"]) for p in patterns]
        assert ("double_top", "SELL") in pattern_types

    def test_rejection_wick_bearish(self):
        """Quick spike up then retrace should detect rejection wick (SELL)."""
        # Start flat, then spike up, then retrace most of the spike
        prices = [100.0] * 20
        # Spike up $0.20
        for i in range(5):
            prices.append(100.0 + i * 0.05)
        # Retrace back down
        for i in range(5):
            prices.append(100.20 - i * 0.04)

        patterns = detect_micro_patterns(prices, lookback=30)
        pattern_types = [(p["pattern"], p["direction"]) for p in patterns]
        assert ("rejection_wick", "SELL") in pattern_types

    def test_rejection_wick_bullish(self):
        """Quick spike down then retrace up should detect rejection wick (BUY)."""
        # Start flat, spike down, retrace back up
        prices = [100.0] * 20
        # Spike down $0.20
        for i in range(5):
            prices.append(100.0 - i * 0.05)
        # Retrace back up
        for i in range(5):
            prices.append(99.80 + i * 0.04)

        patterns = detect_micro_patterns(prices, lookback=30)
        pattern_types = [(p["pattern"], p["direction"]) for p in patterns]
        assert ("rejection_wick", "BUY") in pattern_types

    def test_no_patterns_flat_market(self):
        """Flat/minimal movement should detect no patterns."""
        prices = [100.0 + i * 0.001 for i in range(30)]
        patterns = detect_micro_patterns(prices, lookback=30)
        assert patterns == []

    def test_insufficient_data(self):
        """Not enough data should return empty list."""
        prices = [100.0, 100.1]
        patterns = detect_micro_patterns(prices, lookback=30)
        assert patterns == []

    def test_pattern_returns_correct_keys(self):
        """Each pattern dict should have 'pattern' and 'direction' keys."""
        prices = []
        start = 100.0
        for i in range(15):
            prices.append(start - i * 0.02)
        low = prices[-1]
        for i in range(15):
            prices.append(low + i * 0.02)

        patterns = detect_micro_patterns(prices, lookback=30)
        for pat in patterns:
            assert "pattern" in pat
            assert "direction" in pat
            assert pat["direction"] in ("BUY", "SELL")

    def test_uses_config_lookback_default(self):
        """Should use Config.PATTERN_LOOKBACK when no lookback specified."""
        assert Config.PATTERN_LOOKBACK == 30


class TestComputeAdaptiveThresholds:
    """Test adaptive threshold scaling based on volatility."""

    def test_normal_volatility(self):
        """When current ATR equals average, thresholds should be at base values."""
        result = compute_adaptive_thresholds(1.0, 1.0)
        assert abs(result["velocity_threshold"] - 0.30) < 0.001
        assert abs(result["scalp_threshold"] - 0.50) < 0.001
        assert abs(result["momentum_threshold"] - 0.60) < 0.001

    def test_high_volatility_widens(self):
        """High ATR should widen thresholds (multiply by ratio > 1)."""
        result = compute_adaptive_thresholds(2.0, 1.0)
        assert result["velocity_threshold"] > 0.30
        assert result["scalp_threshold"] > 0.50
        assert result["momentum_threshold"] > 0.60

    def test_low_volatility_tightens(self):
        """Low ATR should tighten thresholds (multiply by ratio < 1)."""
        result = compute_adaptive_thresholds(0.5, 1.0)
        assert result["velocity_threshold"] < 0.30
        assert result["scalp_threshold"] < 0.50
        assert result["momentum_threshold"] < 0.60

    def test_zero_avg_atr_returns_defaults(self):
        """Zero average ATR should return default thresholds."""
        result = compute_adaptive_thresholds(1.0, 0.0)
        assert result["velocity_threshold"] == 0.30
        assert result["scalp_threshold"] == 0.50
        assert result["momentum_threshold"] == 0.60

    def test_very_high_volatility_clamped(self):
        """Extremely high volatility should be clamped to 2x max."""
        result = compute_adaptive_thresholds(10.0, 1.0)
        # Clamped at 2.0x
        assert abs(result["velocity_threshold"] - 0.60) < 0.001
        assert abs(result["scalp_threshold"] - 1.00) < 0.001
        assert abs(result["momentum_threshold"] - 1.20) < 0.001

    def test_very_low_volatility_clamped(self):
        """Extremely low volatility should be clamped to 0.5x min."""
        result = compute_adaptive_thresholds(0.1, 1.0)
        # Clamped at 0.5x
        assert abs(result["velocity_threshold"] - 0.15) < 0.001
        assert abs(result["scalp_threshold"] - 0.25) < 0.001
        assert abs(result["momentum_threshold"] - 0.30) < 0.001

    def test_proportional_scaling(self):
        """Thresholds should scale proportionally to volatility ratio."""
        result = compute_adaptive_thresholds(1.5, 1.0)  # 1.5x ratio
        assert abs(result["velocity_threshold"] - 0.45) < 0.001
        assert abs(result["scalp_threshold"] - 0.75) < 0.001
        assert abs(result["momentum_threshold"] - 0.90) < 0.001

    def test_returns_all_keys(self):
        """Result dict should contain all three threshold keys."""
        result = compute_adaptive_thresholds(1.0, 1.0)
        assert "velocity_threshold" in result
        assert "scalp_threshold" in result
        assert "momentum_threshold" in result


class TestConfigPhase2:
    """Test that Phase 2 config parameters exist with correct values."""

    def test_acceleration_lookback(self):
        assert Config.ACCELERATION_LOOKBACK == 10

    def test_weighted_tick_lookback(self):
        assert Config.WEIGHTED_TICK_LOOKBACK == 20

    def test_pattern_lookback(self):
        assert Config.PATTERN_LOOKBACK == 30

    def test_adaptive_threshold_enabled(self):
        assert Config.ADAPTIVE_THRESHOLD_ENABLED is True

    def test_v_reversal_min_drop(self):
        assert Config.V_REVERSAL_MIN_DROP == 0.20

    def test_v_reversal_min_recovery_pct(self):
        assert Config.V_REVERSAL_MIN_RECOVERY_PCT == 0.70

    def test_double_top_tolerance(self):
        assert Config.DOUBLE_TOP_TOLERANCE == 0.10

    def test_rejection_wick_min(self):
        assert Config.REJECTION_WICK_MIN == 0.15

    def test_rejection_retrace_pct(self):
        assert Config.REJECTION_RETRACE_PCT == 0.60
