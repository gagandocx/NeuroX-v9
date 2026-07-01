"""Tests for tick_collector.py"""

import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tick_collector import TickCollector
from config import Config


@pytest.fixture
def tick_file(tmp_path):
    """Create a temporary tick price file."""
    path = tmp_path / "neurox_v9_tick_price.txt"
    return str(path)


@pytest.fixture
def collector(tick_file):
    """Create a TickCollector with a temp file path."""
    return TickCollector(tick_file, bar_count=20)


class TestReadTick:
    """Test tick reading from file."""

    def test_read_valid_tick(self, collector, tick_file):
        """Should read a valid price from the file."""
        with open(tick_file, "w") as f:
            f.write("4081.50")
        assert collector.read_tick() == 4081.50

    def test_read_missing_file(self, collector):
        """Missing file should return 0.0."""
        assert collector.read_tick() == 0.0

    def test_read_empty_file(self, collector, tick_file):
        """Empty file should return 0.0."""
        with open(tick_file, "w") as f:
            f.write("")
        assert collector.read_tick() == 0.0

    def test_read_invalid_content(self, collector, tick_file):
        """Non-numeric content should return 0.0."""
        with open(tick_file, "w") as f:
            f.write("not_a_number")
        assert collector.read_tick() == 0.0

    def test_read_with_whitespace(self, collector, tick_file):
        """Should handle trailing newlines/spaces."""
        with open(tick_file, "w") as f:
            f.write("4081.50\n")
        assert collector.read_tick() == 4081.50


class TestBarAggregation:
    """Test tick to bar aggregation."""

    def test_no_data_returns_empty(self, collector):
        """No tick file should return empty DataFrame."""
        result = collector.update()
        assert result.empty

    def test_single_tick_returns_empty(self, collector, tick_file):
        """Single tick (no completed bars) should return empty."""
        with open(tick_file, "w") as f:
            f.write("4081.50")
        result = collector.update()
        # Only 0 completed bars (current bar is still open)
        assert result.empty

    def test_bar_closes_on_minute_change(self, collector, tick_file):
        """When minute changes, current bar should close."""
        base_time = datetime(2025, 6, 29, 12, 0, 0)

        with open(tick_file, "w") as f:
            f.write("4080.00")

        # Simulate ticks in minute 0
        with patch("tick_collector.datetime") as mock_dt:
            mock_dt.now.return_value = base_time
            collector.update()

            # Update OHLC within same minute
            with open(tick_file, "w") as f:
                f.write("4082.00")
            collector.update()

            with open(tick_file, "w") as f:
                f.write("4079.00")
            collector.update()

            with open(tick_file, "w") as f:
                f.write("4081.00")
            collector.update()

            # Move to next minute - should close the bar
            mock_dt.now.return_value = base_time + timedelta(minutes=1)
            with open(tick_file, "w") as f:
                f.write("4081.50")
            collector.update()

        # Should have 1 completed bar
        assert len(collector._completed_bars) == 1
        bar = collector._completed_bars[0]
        assert bar["Open"] == 4080.00
        assert bar["High"] == 4082.00
        assert bar["Low"] == 4079.00
        assert bar["Close"] == 4081.00

    def test_returns_dataframe_after_min_bars(self, collector, tick_file):
        """Should return DataFrame only after MIN_BARS_FOR_MOMENTUM bars."""
        base_time = datetime(2025, 6, 29, 12, 0, 0)

        with patch("tick_collector.datetime") as mock_dt:
            # Build enough bars
            for i in range(Config.MIN_BARS_FOR_MOMENTUM + 1):
                mock_dt.now.return_value = base_time + timedelta(minutes=i)
                price = 4080.0 + i * 0.1
                with open(tick_file, "w") as f:
                    f.write(f"{price:.2f}")
                result = collector.update()

        # Should now have enough bars
        assert not result.empty
        assert len(result) >= Config.MIN_BARS_FOR_MOMENTUM
        assert list(result.columns) == ["Open", "High", "Low", "Close"]

    def test_last_price_updated(self, collector, tick_file):
        """last_price should reflect the most recent tick."""
        with open(tick_file, "w") as f:
            f.write("4085.25")
        collector.update()
        assert collector.last_price == 4085.25

    def test_rolling_window_respects_bar_count(self, tick_file):
        """Completed bars should not exceed bar_count."""
        collector = TickCollector(tick_file, bar_count=5)
        base_time = datetime(2025, 6, 29, 12, 0, 0)

        with patch("tick_collector.datetime") as mock_dt:
            for i in range(10):
                mock_dt.now.return_value = base_time + timedelta(minutes=i)
                with open(tick_file, "w") as f:
                    f.write(f"{4080.0 + i:.2f}")
                collector.update()

        # Should cap at bar_count (5)
        assert len(collector._completed_bars) <= 5


class TestConfig:
    """Test config values for tick collection."""

    def test_tick_file_config(self):
        """Config should have TICK_FILE set."""
        assert Config.TICK_FILE == "neurox_v9_tick_price.txt"

    def test_min_bars_config(self):
        """Config should have MIN_BARS_FOR_MOMENTUM set."""
        assert Config.MIN_BARS_FOR_MOMENTUM == 8

    def test_no_yfinance_ticker(self):
        """YFINANCE_TICKER should not exist in config."""
        assert not hasattr(Config, "YFINANCE_TICKER")


class TestTickConsistencyMethod:
    """Test get_tick_consistency method on TickCollector."""

    def test_trending_up_high_consistency(self, collector):
        """Steadily rising ticks should show high BUY consistency."""
        for i in range(20):
            collector._tick_prices.append(2000.0 + i * 0.10)
        direction, pct = collector.get_tick_consistency()
        assert direction == "BUY"
        assert pct == 1.0

    def test_trending_down_high_consistency(self, collector):
        """Steadily falling ticks should show high SELL consistency."""
        for i in range(20):
            collector._tick_prices.append(2000.0 - i * 0.10)
        direction, pct = collector.get_tick_consistency()
        assert direction == "SELL"
        assert pct == 1.0

    def test_noisy_ticks_low_consistency(self, collector):
        """Alternating ticks should show ~50% consistency (FLAT)."""
        for i in range(20):
            if i % 2 == 0:
                collector._tick_prices.append(2000.0)
            else:
                collector._tick_prices.append(2000.10)
        direction, pct = collector.get_tick_consistency()
        # Alternating: roughly 50% up, 50% down
        assert pct <= 0.60

    def test_insufficient_data_returns_flat(self, collector):
        """With 0 or 1 ticks, should return FLAT with 0.0."""
        direction, pct = collector.get_tick_consistency()
        assert direction == "FLAT"
        assert pct == 0.0

        collector._tick_prices.append(2000.0)
        direction, pct = collector.get_tick_consistency()
        assert direction == "FLAT"
        assert pct == 0.0

    def test_custom_lookback(self, collector):
        """Should respect custom lookback parameter."""
        # First 10 ticks go down, then 10 ticks go up
        for i in range(10):
            collector._tick_prices.append(2000.0 - i * 0.10)
        for i in range(10):
            collector._tick_prices.append(1999.0 + i * 0.10)

        # Looking at only last 10 ticks (all up)
        direction, pct = collector.get_tick_consistency(lookback=10)
        assert direction == "BUY"
        assert pct == 1.0

    def test_flat_ticks_no_movement(self, collector):
        """All same-price ticks should return FLAT."""
        for i in range(10):
            collector._tick_prices.append(2000.0)
        direction, pct = collector.get_tick_consistency()
        assert direction == "FLAT"
        assert pct == 0.0

    def test_mostly_up_with_some_down(self, collector):
        """70% up moves should show BUY direction with ~0.7 consistency."""
        # 7 up moves + 3 down moves = 10 total moves (11 ticks)
        prices = [2000.0]
        for i in range(7):
            prices.append(prices[-1] + 0.10)
        for i in range(3):
            prices.append(prices[-1] - 0.10)
        for p in prices:
            collector._tick_prices.append(p)
        direction, pct = collector.get_tick_consistency()
        assert direction == "BUY"
        assert abs(pct - 0.70) < 0.01
