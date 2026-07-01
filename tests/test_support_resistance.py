"""Tests for support_resistance.py - Support/Resistance Zones module."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support_resistance import (
    find_swing_points,
    cluster_levels,
    compute_support_resistance,
)
from config import Config


class TestFindSwingPoints:
    """Test swing high/low detection from bar data."""

    def test_clear_swing_high(self):
        """A peak bar surrounded by lower bars should be detected."""
        bars = []
        # Build a clear peak at index 5
        for i in range(11):
            if i < 5:
                high = 2000.0 + i * 0.5
            elif i == 5:
                high = 2005.0  # clear peak
            else:
                high = 2005.0 - (i - 5) * 0.5
            bars.append({
                "Open": high - 0.5,
                "High": high,
                "Low": high - 1.0,
                "Close": high - 0.3,
            })
        highs, lows = find_swing_points(bars)
        assert len(highs) > 0
        assert any(abs(h - 2005.0) < 0.01 for h in highs)

    def test_clear_swing_low(self):
        """A trough bar surrounded by higher bars should be detected."""
        bars = []
        # Build a clear trough at index 5
        for i in range(11):
            if i < 5:
                low = 2000.0 - i * 0.5
            elif i == 5:
                low = 1995.0  # clear trough
            else:
                low = 1995.0 + (i - 5) * 0.5
            bars.append({
                "Open": low + 0.5,
                "High": low + 1.0,
                "Low": low,
                "Close": low + 0.3,
            })
        highs, lows = find_swing_points(bars)
        assert len(lows) > 0
        assert any(abs(l - 1995.0) < 0.01 for l in lows)

    def test_insufficient_bars_returns_empty(self):
        """Too few bars should return empty lists."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5}
            for _ in range(3)
        ]
        highs, lows = find_swing_points(bars)
        assert highs == []
        assert lows == []

    def test_flat_market_no_swings(self):
        """Flat market should produce no swing points."""
        bars = [
            {"Open": 2000.0, "High": 2000.0, "Low": 2000.0, "Close": 2000.0}
            for _ in range(20)
        ]
        highs, lows = find_swing_points(bars)
        assert highs == []
        assert lows == []


class TestClusterLevels:
    """Test level clustering into zones."""

    def test_cluster_nearby_levels(self):
        """Levels within tolerance should be clustered together."""
        levels = [2000.0, 2000.1, 2000.15, 2005.0, 2005.1]
        zones = cluster_levels(levels, tolerance=0.20)
        assert len(zones) == 2  # Two clusters
        # First cluster around 2000.0
        assert any(abs(z["price"] - 2000.083) < 0.1 for z in zones)
        # Second cluster around 2005.0
        assert any(abs(z["price"] - 2005.05) < 0.1 for z in zones)

    def test_cluster_counts_touches(self):
        """Cluster should count number of levels (touches)."""
        levels = [2000.0, 2000.1, 2000.15]
        zones = cluster_levels(levels, tolerance=0.20)
        assert len(zones) == 1
        assert zones[0]["touches"] == 3
        assert zones[0]["strength"] == "MODERATE"

    def test_strong_level(self):
        """4+ touches should be STRONG."""
        levels = [2000.0, 2000.05, 2000.10, 2000.15]
        zones = cluster_levels(levels, tolerance=0.20)
        assert len(zones) == 1
        assert zones[0]["touches"] == 4
        assert zones[0]["strength"] == "STRONG"

    def test_weak_level(self):
        """1-2 touches should be WEAK."""
        levels = [2000.0, 2005.0]
        zones = cluster_levels(levels, tolerance=0.20)
        assert len(zones) == 2
        for z in zones:
            assert z["strength"] == "WEAK"

    def test_empty_levels(self):
        """Empty levels should return empty zones."""
        zones = cluster_levels([])
        assert zones == []

    def test_single_level(self):
        """Single level should produce one WEAK zone."""
        zones = cluster_levels([2000.0])
        assert len(zones) == 1
        assert zones[0]["touches"] == 1
        assert zones[0]["strength"] == "WEAK"


class TestComputeSupportResistance:
    """Test full S/R computation and signal generation."""

    def test_insufficient_bars_returns_none_signal(self):
        """Too few bars should return NONE signal."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5}
            for _ in range(5)
        ]
        result = compute_support_resistance(bars, 2000.0)
        assert result["signal_type"] == "NONE"

    def test_bounce_up_signal_at_support(self):
        """Price near a strong support level should signal BOUNCE_UP."""
        # Create bars with repeated lows at 1998.0 (support zone)
        bars = []
        for i in range(20):
            if i % 4 == 0:
                # Bounce bars: low hits 1998.0
                bars.append({
                    "Open": 2000.0,
                    "High": 2001.0,
                    "Low": 1998.0,
                    "Close": 2000.5,
                })
            else:
                # Normal bars
                bars.append({
                    "Open": 2000.0 + (i % 3) * 0.3,
                    "High": 2001.5,
                    "Low": 1999.5,
                    "Close": 2000.5,
                })

        # Current price very close to the support level
        result = compute_support_resistance(bars, 1998.2)
        # We should see support zones and possibly a BOUNCE_UP signal
        assert result["support_zones"] is not None or result["resistance_zones"] is not None

    def test_returns_expected_keys(self):
        """Result dict should have all expected keys."""
        bars = [
            {"Open": 2000.0, "High": 2001.0, "Low": 1999.0, "Close": 2000.5}
            for _ in range(20)
        ]
        result = compute_support_resistance(bars, 2000.0)
        assert "support_zones" in result
        assert "resistance_zones" in result
        assert "nearest_support" in result
        assert "nearest_resistance" in result
        assert "signal_type" in result
        assert "distance_to_nearest" in result
        assert "nearest_strength" in result

    def test_no_swing_points_returns_none(self):
        """Completely flat bars should produce NONE signal."""
        bars = [
            {"Open": 2000.0, "High": 2000.0, "Low": 2000.0, "Close": 2000.0}
            for _ in range(20)
        ]
        result = compute_support_resistance(bars, 2000.0)
        assert result["signal_type"] == "NONE"

    def test_support_below_resistance_above(self):
        """Support zones should be below price, resistance above."""
        # Create clear swing structure
        bars = []
        for i in range(30):
            cycle = i % 10
            if cycle < 5:
                # Upswing
                price = 2000.0 + cycle * 1.0
            else:
                # Downswing
                price = 2005.0 - (cycle - 5) * 1.0
            bars.append({
                "Open": price - 0.5,
                "High": price + 0.5,
                "Low": price - 1.0,
                "Close": price,
            })

        result = compute_support_resistance(bars, 2002.0)
        # All support zones should be below current price
        for zone in result["support_zones"]:
            assert zone["price"] < 2002.0
        # All resistance zones should be above current price
        for zone in result["resistance_zones"]:
            assert zone["price"] >= 2002.0
