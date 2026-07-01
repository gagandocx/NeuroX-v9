"""Tests for tick_frequency.py - Tick Frequency Spike Detection module."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tick_frequency import compute_tick_frequency
from config import Config


class TestComputeTickFrequency:
    """Test tick frequency computation and spike detection."""

    def test_normal_frequency(self):
        """10 ticks in 1 second = 10 tps (normal)."""
        now = time.time()
        timestamps = [now - 1.0 + i * 0.1 for i in range(10)]
        result = compute_tick_frequency(timestamps)
        assert result["ticks_per_second"] == pytest.approx(10.0, abs=1.0)
        assert result["is_spike"] is False
        assert result["activity_level"] == "NORMAL"
        assert result["amplifier_mult"] == 1.0

    def test_spike_frequency(self):
        """60 ticks in 1 second = 60 tps (institutional spike)."""
        now = time.time()
        # 60 ticks packed within 1 second
        timestamps = [now - 1.0 + i * (1.0 / 60) for i in range(60)]
        result = compute_tick_frequency(timestamps)
        assert result["ticks_per_second"] >= 50.0
        assert result["is_spike"] is True
        assert result["activity_level"] == "INSTITUTIONAL"
        assert result["amplifier_mult"] == Config.TICK_FREQ_SPIKE_AMPLIFIER

    def test_elevated_frequency(self):
        """30 ticks in 1 second = elevated but not spike."""
        now = time.time()
        timestamps = [now - 1.0 + i * (1.0 / 30) for i in range(30)]
        result = compute_tick_frequency(timestamps)
        assert result["ticks_per_second"] >= 25.0
        assert result["is_spike"] is False
        assert result["activity_level"] == "ELEVATED"
        assert 1.0 < result["amplifier_mult"] < Config.TICK_FREQ_SPIKE_AMPLIFIER

    def test_low_frequency(self):
        """3 ticks in 1 second = low frequency."""
        now = time.time()
        timestamps = [now - 1.0, now - 0.5, now]
        result = compute_tick_frequency(timestamps)
        assert result["ticks_per_second"] <= 15.0
        assert result["is_spike"] is False
        assert result["activity_level"] == "NORMAL"

    def test_single_tick(self):
        """Single tick should return 0 tps."""
        result = compute_tick_frequency([time.time()])
        assert result["ticks_per_second"] == 0.0
        assert result["is_spike"] is False

    def test_empty_timestamps(self):
        """Empty timestamps should return 0 tps."""
        result = compute_tick_frequency([])
        assert result["ticks_per_second"] == 0.0
        assert result["is_spike"] is False

    def test_amplifier_mult_always_gte_one(self):
        """Amplifier should never be less than 1.0."""
        now = time.time()
        for n_ticks in [2, 5, 10, 30, 60]:
            timestamps = [now - 1.0 + i * (1.0 / n_ticks) for i in range(n_ticks)]
            result = compute_tick_frequency(timestamps)
            assert result["amplifier_mult"] >= 1.0

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        result = compute_tick_frequency([time.time()])
        assert "ticks_per_second" in result
        assert "is_spike" in result
        assert "amplifier_mult" in result
        assert "activity_level" in result
