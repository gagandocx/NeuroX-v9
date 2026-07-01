"""Tests for liquidity_sweep.py - Liquidity Sweep Detection module."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from liquidity_sweep import detect_liquidity_sweep
from config import Config


class TestDetectLiquiditySweep:
    """Test liquidity sweep (fast spike + instant reversal) detection."""

    def test_no_sweep_flat_market(self):
        """Flat prices should not detect a sweep."""
        now = time.time()
        prices = [2000.0] * 20
        timestamps = [now - (20 - i) * 0.1 for i in range(20)]
        result = detect_liquidity_sweep(prices, timestamps)
        assert result["detected"] is False
        assert result["direction"] == ""

    def test_upward_spike_with_reversal_down(self):
        """Price spikes up then reverses down -> SELL signal."""
        now = time.time()
        # Build a spike up followed by reversal down within sweep window
        prices = []
        timestamps = []
        base = 2000.0

        # Normal prices for first 5 ticks
        for i in range(5):
            prices.append(base + i * 0.01)
            timestamps.append(now - 4.0 + i * 0.2)

        # Spike up (fast move) - 5 ticks
        for i in range(5):
            prices.append(base + 0.05 + i * 0.10)
            timestamps.append(now - 3.0 + i * 0.2)

        # Peak at base + 0.45
        # Reversal down - 5 ticks
        peak = prices[-1]
        for i in range(5):
            prices.append(peak - i * 0.15)
            timestamps.append(now - 2.0 + i * 0.2)

        result = detect_liquidity_sweep(prices, timestamps)
        assert result["detected"] is True
        assert result["direction"] == "SELL"
        assert result["spike_magnitude"] > 0
        assert result["reversal_magnitude"] > 0

    def test_downward_spike_with_reversal_up(self):
        """Price spikes down then reverses up -> BUY signal."""
        now = time.time()
        prices = []
        timestamps = []
        base = 2000.0

        # Normal prices
        for i in range(5):
            prices.append(base - i * 0.01)
            timestamps.append(now - 4.0 + i * 0.2)

        # Spike down (fast drop) - 5 ticks
        for i in range(5):
            prices.append(base - 0.05 - i * 0.10)
            timestamps.append(now - 3.0 + i * 0.2)

        # Trough
        trough = prices[-1]
        # Reversal up - 5 ticks
        for i in range(5):
            prices.append(trough + i * 0.15)
            timestamps.append(now - 2.0 + i * 0.2)

        result = detect_liquidity_sweep(prices, timestamps)
        assert result["detected"] is True
        assert result["direction"] == "BUY"

    def test_spike_without_reversal_no_detection(self):
        """Spike up without reversal should not trigger."""
        now = time.time()
        prices = []
        timestamps = []
        base = 2000.0

        # Steady upward move (no reversal)
        for i in range(15):
            prices.append(base + i * 0.05)
            timestamps.append(now - 3.0 + i * 0.2)

        result = detect_liquidity_sweep(prices, timestamps)
        assert result["detected"] is False

    def test_insufficient_data(self):
        """Too few ticks should return no detection."""
        result = detect_liquidity_sweep([2000.0, 2000.1], [time.time(), time.time()])
        assert result["detected"] is False

    def test_empty_data(self):
        """Empty data should return no detection."""
        result = detect_liquidity_sweep([], [])
        assert result["detected"] is False

    def test_confidence_between_zero_and_one(self):
        """Confidence should always be between 0 and 1."""
        now = time.time()
        prices = []
        timestamps = []
        base = 2000.0

        # Create strong sweep pattern
        for i in range(5):
            prices.append(base)
            timestamps.append(now - 4.5 + i * 0.1)

        # Big spike up
        for i in range(5):
            prices.append(base + i * 0.15)
            timestamps.append(now - 4.0 + i * 0.2)

        # Full reversal
        peak = prices[-1]
        for i in range(5):
            prices.append(peak - i * 0.20)
            timestamps.append(now - 3.0 + i * 0.2)

        result = detect_liquidity_sweep(prices, timestamps)
        if result["detected"]:
            assert 0.0 <= result["confidence"] <= 1.0

    def test_returns_expected_keys(self):
        """Result should have all expected keys."""
        result = detect_liquidity_sweep([2000.0] * 10, [time.time()] * 10)
        assert "detected" in result
        assert "direction" in result
        assert "spike_magnitude" in result
        assert "reversal_magnitude" in result
        assert "confidence" in result
