"""Tests for bridge.py"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import Bridge, LEGACY_SIGNAL_FILE, LEGACY_HEARTBEAT_FILE, LEGACY_EXIT_FILE
from config import Config


@pytest.fixture
def tmp_bridge(tmp_path):
    """Create a Bridge instance using a temp directory."""
    return Bridge(mt5_common_path=str(tmp_path))


class TestBridgeWriteSignal:
    """Test signal writing."""

    def test_write_signal_creates_files(self, tmp_bridge):
        """write_signal should create signal data and flag files."""
        signal = {
            "action": "BUY",
            "confidence": 0.95,
            "lot_size": 0.01,
        }
        result = tmp_bridge.write_signal(signal)
        assert result is True

        # Check flag file
        flag_path = tmp_bridge.common_path / "neurox_signal_ready.flag"
        assert flag_path.exists()
        assert flag_path.read_text().strip() == "1"

        # Check data file
        data_path = tmp_bridge.common_path / "neurox_signal.bin"
        assert data_path.exists()
        content = data_path.read_text()
        assert "BUY" in content
        assert "XAUUSD" in content

    def test_signal_file_prefix(self, tmp_bridge):
        """Legacy signal file should use neurox_v9_ prefix."""
        signal = {"action": "SELL"}
        tmp_bridge.write_signal(signal)

        csv_path = tmp_bridge.common_path / LEGACY_SIGNAL_FILE
        assert csv_path.exists()
        assert "neurox_v9_" in LEGACY_SIGNAL_FILE

    def test_signals_sent_counter(self, tmp_bridge):
        """Signal counter should increment."""
        assert tmp_bridge.signals_sent == 0
        tmp_bridge.write_signal({"action": "BUY"})
        assert tmp_bridge.signals_sent == 1
        tmp_bridge.write_signal({"action": "SELL"})
        assert tmp_bridge.signals_sent == 2


class TestBridgeExitSignal:
    """Test exit signal writing."""

    def test_write_exit_signal(self, tmp_bridge):
        """write_exit_signal should create exit files."""
        result = tmp_bridge.write_exit_signal(
            ticket=12345,
            action="CLOSE_FULL",
            lot_pct=1.0,
            new_sl=0.0,
            reason="trailing_stop",
        )
        assert result is True

        # Check flag
        flag_path = tmp_bridge.common_path / "neurox_exit_ready.flag"
        assert flag_path.exists()
        assert flag_path.read_text().strip() == "1"

        # Check legacy CSV
        csv_path = tmp_bridge.common_path / LEGACY_EXIT_FILE
        assert csv_path.exists()
        content = csv_path.read_text()
        assert "12345" in content
        assert "CLOSE_FULL" in content
        assert "neurox_v9_" in LEGACY_EXIT_FILE


class TestBridgeHeartbeat:
    """Test heartbeat writing."""

    def test_write_heartbeat(self, tmp_bridge):
        """write_heartbeat should create heartbeat file."""
        result = tmp_bridge.write_heartbeat()
        assert result is True

        hb_path = tmp_bridge.common_path / LEGACY_HEARTBEAT_FILE
        assert hb_path.exists()
        assert "neurox_v9_" in LEGACY_HEARTBEAT_FILE


class TestBridgeConfirmation:
    """Test confirmation reading."""

    def test_read_confirmation_no_data(self, tmp_bridge):
        """No confirmation available should return None."""
        result = tmp_bridge.read_confirmation(timeout=0.1)
        assert result is None

    def test_read_confirmation_pipe(self, tmp_bridge):
        """Should read confirmation from flag-based file."""
        # Simulate MT5 writing confirmation
        data = "2025.06.29 10:00:00,12345,XAUUSD,BUY,0.01,2650.50,2648.50,2655.50,FILLED,0.00,0.0010"
        data_path = tmp_bridge.common_path / "neurox_confirm.bin"
        data_path.write_text(data, encoding="ascii")

        flag_path = tmp_bridge.common_path / "neurox_confirm_ready.flag"
        flag_path.write_text("1", encoding="ascii")

        result = tmp_bridge.read_confirmation(timeout=1.0)
        assert result is not None
        assert result["ticket"] == 12345
        assert result["action"] == "BUY"
        assert result["status"] == "FILLED"
        assert result["open_price"] == 2650.50


class TestBridgePrefix:
    """Verify all files use neurox_v9_ prefix."""

    def test_all_legacy_files_have_prefix(self):
        """All legacy file constants should contain neurox_v9_."""
        assert "neurox_v9_" in LEGACY_SIGNAL_FILE
        assert "neurox_v9_" in LEGACY_HEARTBEAT_FILE
        assert "neurox_v9_" in LEGACY_EXIT_FILE

    def test_config_prefix(self):
        """Config should specify neurox_v9_ prefix."""
        assert Config.SIGNAL_FILE_PREFIX == "neurox_v9_"


class TestBridgeIntelligence:
    """Test intelligence file writing for EA dashboard."""

    def test_write_intelligence_creates_file(self, tmp_bridge):
        """write_intelligence should create the intelligence file."""
        result = tmp_bridge.write_intelligence(
            regime="TRENDING",
            atr_value=1.25,
            atr_pass=True,
            tick_pct=0.75,
            tick_dir="BUY",
            persistence_count=3,
            persistence_dir="BUY",
            strategy="MOMENTUM",
            decision="TRADING",
            reason="",
        )
        assert result is True

        intel_path = tmp_bridge.common_path / Config.INTELLIGENCE_FILE
        assert intel_path.exists()

    def test_write_intelligence_format(self, tmp_bridge):
        """Intelligence file should be pipe-delimited with exactly 15 fields."""
        tmp_bridge.write_intelligence(
            regime="RANGING",
            atr_value=0.35,
            atr_pass=False,
            tick_pct=0.55,
            tick_dir="SELL",
            persistence_count=1,
            persistence_dir="SELL",
            strategy="MEAN_REVERSION",
            decision="FILTERED",
            reason="ATR_LOW",
            ema_trend="DOWN",
            choppy_votes="3/5 CHOPPY",
            swing_sl="$2648.50",
            breakeven_status="INACTIVE",
            reversal_status="CLEAR",
        )

        intel_path = tmp_bridge.common_path / Config.INTELLIGENCE_FILE
        content = intel_path.read_text(encoding="ascii").strip()
        fields = content.split("|")
        assert len(fields) == 15

    def test_write_intelligence_overwrites(self, tmp_bridge):
        """Intelligence file should be overwritten each call, not appended."""
        tmp_bridge.write_intelligence(
            regime="TRENDING",
            atr_value=1.00,
            atr_pass=True,
            tick_pct=0.80,
            tick_dir="BUY",
            persistence_count=2,
            persistence_dir="BUY",
            strategy="MOMENTUM",
            decision="TRADING",
            reason="",
        )
        tmp_bridge.write_intelligence(
            regime="RANGING",
            atr_value=0.30,
            atr_pass=False,
            tick_pct=0.45,
            tick_dir="SELL",
            persistence_count=1,
            persistence_dir="SELL",
            strategy="MEAN_REVERSION",
            decision="FILTERED",
            reason="ATR_LOW",
        )

        intel_path = tmp_bridge.common_path / Config.INTELLIGENCE_FILE
        content = intel_path.read_text(encoding="ascii").strip()
        # Should only contain the latest write (no newlines = single line)
        assert "\n" not in content
        assert "RANGING" in content
        assert "TRENDING" not in content

    def test_write_intelligence_values(self, tmp_bridge):
        """Verify specific field values are written correctly."""
        tmp_bridge.write_intelligence(
            regime="UNKNOWN",
            atr_value=0.0,
            atr_pass=True,
            tick_pct=0.62,
            tick_dir="BUY",
            persistence_count=0,
            persistence_dir="",
            strategy="TICK_MOMENTUM",
            decision="WAITING",
            reason="",
            choppy_votes="1/5 TRENDING",
            swing_sl="$2650.00",
            breakeven_status="ARMED $5+",
            reversal_status="CLEAR",
        )

        intel_path = tmp_bridge.common_path / Config.INTELLIGENCE_FILE
        content = intel_path.read_text(encoding="ascii").strip()
        fields = content.split("|")

        assert fields[0] == "UNKNOWN"
        assert fields[1] == "0.0"
        assert fields[2] == "1"  # atr_pass=True -> "1"
        assert fields[3] == "0.62"
        assert fields[4] == "BUY"
        assert fields[5] == "0"
        assert fields[6] == ""
        assert fields[7] == "TICK_MOMENTUM"
        assert fields[8] == "WAITING"
        assert fields[9] == ""
        assert fields[10] == ""  # ema_trend defaults to ""
        assert fields[11] == "1/5 TRENDING"
        assert fields[12] == "$2650.00"
        assert fields[13] == "ARMED $5+"
        assert fields[14] == "CLEAR"
