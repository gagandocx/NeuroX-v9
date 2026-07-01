"""Tests for Phase 1: Tick detection, exhaustion, brain settings, and velocity spikes.

Note: Velocity spike signal integration, scalp mode, and brain settings integration
tests from main.py were removed when the main loop was simplified to EMA-only logic.
These tests now cover the standalone module functionality (TickCollector, Bridge).
"""

import os
import sys
import time
from collections import deque
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from bridge import Bridge
from tick_collector import TickCollector


@pytest.fixture
def tmp_bridge(tmp_path):
    """Create a Bridge instance using a temp directory."""
    return Bridge(mt5_common_path=str(tmp_path))


@pytest.fixture
def tick_collector_instance(tmp_path):
    """Create a TickCollector with a dummy tick file path."""
    tick_file = str(tmp_path / "tick_price.txt")
    return TickCollector(tick_file)


# --- Config Tests ---

class TestPhase1Config:
    """Test Phase 1 configuration parameters."""

    def test_version_bumped(self):
        """VERSION should be 9.40."""
        assert Config.VERSION == "9.40"

    def test_build_bumped(self):
        """BUILD should be 20250703."""
        assert Config.BUILD == "20250703"

    def test_tick_velocity_window(self):
        assert Config.TICK_VELOCITY_WINDOW == 2.0

    def test_tick_velocity_threshold(self):
        assert Config.TICK_VELOCITY_THRESHOLD == 0.30

    def test_exhaustion_bar_count(self):
        assert Config.EXHAUSTION_BAR_COUNT == 3

    def test_aggressive_trail_profit(self):
        assert Config.AGGRESSIVE_TRAIL_PROFIT == 0.50

    def test_aggressive_trail_distance(self):
        assert Config.AGGRESSIVE_TRAIL_DISTANCE == 0.15

    def test_scalp_profit_threshold(self):
        assert Config.SCALP_PROFIT_THRESHOLD == 0.30

    def test_scalp_time_limit(self):
        assert Config.SCALP_TIME_LIMIT == 10.0

    def test_brain_settings_file(self):
        assert Config.BRAIN_SETTINGS_FILE == "neurox_v9_brain_settings.csv"


# --- Tick Velocity Spike Detection ---

class TestDetectVelocitySpike:
    """Test tick velocity spike detection in TickCollector."""

    def test_no_spike_insufficient_ticks(self, tick_collector_instance):
        """Should return (None, 0.0) with less than 2 ticks."""
        direction, mag = tick_collector_instance.detect_velocity_spike()
        assert direction is None
        assert mag == 0.0

    def test_no_spike_small_move(self, tick_collector_instance):
        """No spike when price move is below threshold."""
        tc = tick_collector_instance
        now = time.time()
        # Simulate small move: $0.10 in 1 second
        tc._tick_prices.extend([2000.00, 2000.05, 2000.10])
        tc._tick_timestamps.extend([now - 1.0, now - 0.5, now])

        direction, mag = tc.detect_velocity_spike()
        assert direction is None
        assert mag == 0.0

    def test_buy_spike_detected(self, tick_collector_instance):
        """BUY spike when price moves up >= threshold in window."""
        tc = tick_collector_instance
        now = time.time()
        # $0.35 move up in 1.5 seconds
        tc._tick_prices.extend([2000.00, 2000.15, 2000.35])
        tc._tick_timestamps.extend([now - 1.5, now - 0.8, now])

        direction, mag = tc.detect_velocity_spike()
        assert direction == "BUY"
        assert mag >= 0.30

    def test_sell_spike_detected(self, tick_collector_instance):
        """SELL spike when price moves down >= threshold in window."""
        tc = tick_collector_instance
        now = time.time()
        # $0.40 move down in 1.0 seconds
        tc._tick_prices.extend([2000.40, 2000.20, 2000.00])
        tc._tick_timestamps.extend([now - 1.0, now - 0.5, now])

        direction, mag = tc.detect_velocity_spike()
        assert direction == "SELL"
        assert mag >= 0.30

    def test_no_spike_outside_time_window(self, tick_collector_instance):
        """No spike when move happened outside the time window."""
        tc = tick_collector_instance
        now = time.time()
        # $0.50 move but over 3 seconds (outside 2s window)
        tc._tick_prices.extend([2000.00, 2000.25, 2000.50])
        tc._tick_timestamps.extend([now - 3.0, now - 1.5, now])

        direction, mag = tc.detect_velocity_spike()
        # The comparison is between current tick and ticks within window
        # now - (now-1.5) = 1.5s < 2.0s, diff = 2000.50 - 2000.25 = 0.25 < 0.30
        # now - (now-3.0) = 3.0s > 2.0s, skipped
        assert direction is None
        assert mag == 0.0

    def test_spike_exactly_at_threshold(self, tick_collector_instance):
        """Spike detected when move is at or above threshold."""
        tc = tick_collector_instance
        now = time.time()
        # Use values that produce a clean difference >= 0.30
        tc._tick_prices.extend([2000.00, 2000.31])
        tc._tick_timestamps.extend([now - 1.0, now])

        direction, mag = tc.detect_velocity_spike()
        assert direction == "BUY"
        assert mag >= 0.30

    def test_spike_magnitude_returned(self, tick_collector_instance):
        """Magnitude should be the actual price move."""
        tc = tick_collector_instance
        now = time.time()
        tc._tick_prices.extend([2000.00, 2000.50])
        tc._tick_timestamps.extend([now - 0.5, now])

        direction, mag = tc.detect_velocity_spike()
        assert direction == "BUY"
        assert abs(mag - 0.50) < 0.001


# --- Momentum Exhaustion Detection ---

class TestDetectExhaustion:
    """Test momentum exhaustion detection in TickCollector."""

    def test_no_exhaustion_insufficient_bars(self, tick_collector_instance):
        """Should return False with fewer than EXHAUSTION_BAR_COUNT+1 bars."""
        tc = tick_collector_instance
        # Only 2 bars, need 4 (3+1)
        tc._completed_bars.extend([
            {"Open": 2000, "High": 2002, "Low": 1998, "Close": 2001},
            {"Open": 2001, "High": 2002.5, "Low": 1999, "Close": 2002},
        ])
        assert tc.detect_exhaustion() is False

    def test_exhaustion_detected_shrinking_bars(self, tick_collector_instance):
        """Should return True when last 3 bars have shrinking ranges."""
        tc = tick_collector_instance
        # Need 4 bars: 1 reference + 3 shrinking
        tc._completed_bars.extend([
            {"Open": 2000, "High": 2004, "Low": 1996, "Close": 2002},  # range=8
            {"Open": 2002, "High": 2005, "Low": 1999, "Close": 2003},  # range=6
            {"Open": 2003, "High": 2005.5, "Low": 2001, "Close": 2004},  # range=4.5
            {"Open": 2004, "High": 2005, "Low": 2003, "Close": 2004.5},  # range=2
        ])
        assert tc.detect_exhaustion() is True

    def test_no_exhaustion_expanding_bars(self, tick_collector_instance):
        """Should return False when bars are expanding."""
        tc = tick_collector_instance
        tc._completed_bars.extend([
            {"Open": 2000, "High": 2001, "Low": 1999.5, "Close": 2000.5},  # range=1.5
            {"Open": 2000.5, "High": 2002, "Low": 1998.5, "Close": 2001},  # range=3.5
            {"Open": 2001, "High": 2004, "Low": 1997, "Close": 2002},      # range=7
            {"Open": 2002, "High": 2007, "Low": 1995, "Close": 2003},      # range=12
        ])
        assert tc.detect_exhaustion() is False

    def test_no_exhaustion_mixed_bars(self, tick_collector_instance):
        """Should return False when bars are not all shrinking."""
        tc = tick_collector_instance
        tc._completed_bars.extend([
            {"Open": 2000, "High": 2005, "Low": 1995, "Close": 2002},  # range=10
            {"Open": 2002, "High": 2005, "Low": 1999, "Close": 2003},  # range=6 (shrink)
            {"Open": 2003, "High": 2006, "Low": 1997, "Close": 2004},  # range=9 (expand!)
            {"Open": 2004, "High": 2005, "Low": 2003, "Close": 2004.5},  # range=2 (shrink)
        ])
        assert tc.detect_exhaustion() is False

    def test_exhaustion_equal_range_not_shrinking(self, tick_collector_instance):
        """Equal ranges should not count as shrinking."""
        tc = tick_collector_instance
        tc._completed_bars.extend([
            {"Open": 2000, "High": 2005, "Low": 1995, "Close": 2002},  # range=10
            {"Open": 2002, "High": 2005, "Low": 2000, "Close": 2003},  # range=5
            {"Open": 2003, "High": 2005.5, "Low": 2000.5, "Close": 2004},  # range=5 (equal!)
            {"Open": 2004, "High": 2005, "Low": 2003, "Close": 2004.5},  # range=2
        ])
        assert tc.detect_exhaustion() is False


# --- Bridge Brain Settings ---

class TestWriteBrainSettings:
    """Test bridge.write_brain_settings() CSV output."""

    def test_creates_csv_file(self, tmp_bridge):
        """Should create the brain settings CSV file."""
        result = tmp_bridge.write_brain_settings(0.30, 0.50, 0.15)
        assert result is True
        csv_path = tmp_bridge.common_path / Config.BRAIN_SETTINGS_FILE
        assert csv_path.exists()

    def test_csv_content_format(self, tmp_bridge):
        """CSV should have correct header and values."""
        tmp_bridge.write_brain_settings(0.30, 0.50, 0.15)
        csv_path = tmp_bridge.common_path / Config.BRAIN_SETTINGS_FILE
        content = csv_path.read_text()
        lines = content.strip().split("\n")

        assert lines[0] == "setting,value"
        assert lines[1] == "g_brain_be_profit,0.30"
        assert lines[2] == "g_brain_trail_start,0.50"
        assert lines[3] == "g_brain_trail_distance,0.15"

    def test_csv_overwrites_previous(self, tmp_bridge):
        """Writing again should overwrite (not append)."""
        tmp_bridge.write_brain_settings(0.30, 0.50, 0.15)
        tmp_bridge.write_brain_settings(0.50, 1.00, 0.40)
        csv_path = tmp_bridge.common_path / Config.BRAIN_SETTINGS_FILE
        content = csv_path.read_text()
        lines = content.strip().split("\n")

        assert len(lines) == 4  # header + 3 rows
        assert lines[1] == "g_brain_be_profit,0.50"
        assert lines[2] == "g_brain_trail_start,1.00"
        assert lines[3] == "g_brain_trail_distance,0.40"

    def test_csv_different_values(self, tmp_bridge):
        """Should correctly format different floating point values."""
        tmp_bridge.write_brain_settings(1.23, 4.56, 7.89)
        csv_path = tmp_bridge.common_path / Config.BRAIN_SETTINGS_FILE
        content = csv_path.read_text()
        assert "g_brain_be_profit,1.23" in content
        assert "g_brain_trail_start,4.56" in content
        assert "g_brain_trail_distance,7.89" in content


# --- Tick Timestamps Deque ---

class TestTickTimestamps:
    """Test that tick timestamps are recorded alongside prices."""

    def test_timestamps_recorded_on_update(self, tmp_path):
        """_tick_timestamps should grow with each tick update."""
        tick_file = tmp_path / "tick_price.txt"
        tick_file.write_text("2000.50", encoding="utf-16")
        tc = TickCollector(str(tick_file))

        tc.update()
        assert len(tc._tick_timestamps) == 1
        assert len(tc._tick_prices) == 1

        tc.update()
        assert len(tc._tick_timestamps) == 2
        assert len(tc._tick_prices) == 2

    def test_timestamps_maxlen_matches_prices(self, tick_collector_instance):
        """Both deques should have same maxlen (50)."""
        tc = tick_collector_instance
        assert tc._tick_prices.maxlen == 50
        assert tc._tick_timestamps.maxlen == 50

    def test_timestamps_are_monotonic(self, tmp_path):
        """Timestamps should be monotonically increasing."""
        tick_file = tmp_path / "tick_price.txt"
        tick_file.write_text("2000.50", encoding="utf-16")
        tc = TickCollector(str(tick_file))

        tc.update()
        time.sleep(0.01)
        tc.update()

        assert tc._tick_timestamps[-1] >= tc._tick_timestamps[0]
