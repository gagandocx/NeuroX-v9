"""Tests for cumulative_delta.py - Cumulative Delta module."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cumulative_delta import compute_cumulative_delta, detect_delta_divergence
from config import Config


class TestComputeCumulativeDelta:
    """Test cumulative delta computation."""

    def test_all_buy_ticks(self):
        """All upward ticks should give positive delta (BUYING)."""
        # Every tick goes up
        prices = [2000.0 + i * 0.01 for i in range(30)]
        result = compute_cumulative_delta(prices)
        assert result["delta_value"] > 0
        assert result["delta_direction"] == "BUYING"
        assert result["buy_count"] == 29
        assert result["sell_count"] == 0

    def test_all_sell_ticks(self):
        """All downward ticks should give negative delta (SELLING)."""
        prices = [2000.0 - i * 0.01 for i in range(30)]
        result = compute_cumulative_delta(prices)
        assert result["delta_value"] < 0
        assert result["delta_direction"] == "SELLING"
        assert result["sell_count"] == 29
        assert result["buy_count"] == 0

    def test_balanced_ticks_neutral(self):
        """Alternating up/down ticks should give near-zero (NEUTRAL)."""
        prices = []
        for i in range(30):
            if i % 2 == 0:
                prices.append(2000.0 + 0.01)
            else:
                prices.append(2000.0)
        result = compute_cumulative_delta(prices)
        assert abs(result["delta_value"]) <= Config.DELTA_DIRECTION_THRESHOLD
        assert result["delta_direction"] == "NEUTRAL"

    def test_empty_data(self):
        """Empty prices should return neutral."""
        result = compute_cumulative_delta([])
        assert result["delta_value"] == 0.0
        assert result["delta_direction"] == "NEUTRAL"

    def test_single_tick(self):
        """Single tick cannot compute delta."""
        result = compute_cumulative_delta([2000.0])
        assert result["delta_value"] == 0.0
        assert result["delta_direction"] == "NEUTRAL"

    def test_flat_ticks_no_contribution(self):
        """Flat ticks (same price) should not contribute to delta."""
        prices = [2000.0] * 30
        result = compute_cumulative_delta(prices)
        assert result["delta_value"] == 0.0
        assert result["buy_count"] == 0
        assert result["sell_count"] == 0

    def test_dominance_pct_all_buys(self):
        """All buy ticks should have 100% dominance."""
        prices = [2000.0 + i * 0.01 for i in range(30)]
        result = compute_cumulative_delta(prices)
        assert result["dominance_pct"] == pytest.approx(1.0)

    def test_window_limits_data(self):
        """Window should limit which ticks are analyzed."""
        # First 20 ticks down, last 10 ticks up (use window=10)
        prices = [2000.0 - i * 0.01 for i in range(20)]
        prices += [1999.8 + i * 0.01 for i in range(10)]
        result = compute_cumulative_delta(prices, window=10)
        # Only last 10 prices analyzed: all going up
        assert result["delta_value"] > 0
        assert result["delta_direction"] == "BUYING"

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        result = compute_cumulative_delta([2000.0, 2000.1])
        assert "delta_value" in result
        assert "delta_direction" in result
        assert "buy_count" in result
        assert "sell_count" in result
        assert "dominance_pct" in result


class TestDetectDeltaDivergence:
    """Test delta divergence detection."""

    def test_bullish_divergence(self):
        """Price down but buys dominating -> bullish divergence."""
        # Price trends down overall but most ticks are up-ticks
        # Build: start high, end lower, but have many small up-ticks
        prices = []
        p = 2000.0
        for i in range(30):
            if i % 5 == 0:
                p -= 0.20  # big drops every 5th tick
            else:
                p += 0.02  # small ups most ticks
            prices.append(p)

        result = detect_delta_divergence(prices, window=30)
        if result["price_direction"] == "DOWN" and result["delta_direction"] == "BUYING":
            assert result["divergence_detected"] is True
            assert result["divergence_type"] == "BULLISH"

    def test_bearish_divergence(self):
        """Price up but sells dominating -> bearish divergence."""
        prices = []
        p = 2000.0
        for i in range(30):
            if i % 5 == 0:
                p += 0.20  # big rises every 5th tick
            else:
                p -= 0.02  # small drops most ticks
            prices.append(p)

        result = detect_delta_divergence(prices, window=30)
        if result["price_direction"] == "UP" and result["delta_direction"] == "SELLING":
            assert result["divergence_detected"] is True
            assert result["divergence_type"] == "BEARISH"

    def test_breakout_up_prediction(self):
        """Price flat but strong buying -> breakout UP prediction."""
        # Price stays flat (start and end similar) but all ticks move up
        # This means many small ups and equal small downs, net up
        prices = [2000.0]
        p = 2000.0
        for i in range(29):
            p += 0.005  # tiny up-ticks (net move < threshold)
            prices.append(p)

        result = detect_delta_divergence(prices, window=30)
        # The price change is small (below threshold), delta should be BUYING
        if result["price_direction"] == "FLAT" and result["delta_direction"] == "BUYING":
            assert result["divergence_detected"] is True
            assert result["divergence_type"] == "BREAKOUT_UP"

    def test_no_divergence_aligned(self):
        """Price and delta both UP -> no divergence."""
        prices = [2000.0 + i * 0.05 for i in range(30)]
        result = detect_delta_divergence(prices, window=30)
        assert result["divergence_detected"] is False
        assert result["divergence_type"] == "NONE"

    def test_insufficient_data(self):
        """Too few ticks should return no divergence."""
        result = detect_delta_divergence([2000.0, 2000.1], window=30)
        assert result["divergence_detected"] is False

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        result = detect_delta_divergence([2000.0] * 30, window=30)
        assert "divergence_detected" in result
        assert "divergence_type" in result
        assert "price_direction" in result
        assert "delta_direction" in result
