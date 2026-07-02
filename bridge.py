"""
NeuroX v9.0 - Signal Bridge

Simplified from v8's signals/pipe_bridge.py.
Flag-based shared memory + legacy CSV fallback.
All files use "neurox_v9_" prefix.
"""

import os
import time
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any

from config import Config

logger = logging.getLogger("Bridge")

# File names (neurox_v9_ prefix for all)
PREFIX = Config.SIGNAL_FILE_PREFIX

SIGNAL_DATA_FILE = "neurox_signal.bin"
SIGNAL_FLAG_FILE = "neurox_signal_ready.flag"
CONFIRM_DATA_FILE = "neurox_confirm.bin"
CONFIRM_FLAG_FILE = "neurox_confirm_ready.flag"
EXIT_DATA_FILE = "neurox_exit.bin"
EXIT_FLAG_FILE = "neurox_exit_ready.flag"

# Legacy CSV files (with v9 prefix)
LEGACY_SIGNAL_FILE = f"{PREFIX}signal.csv"
LEGACY_CONFIRM_FILE = f"{PREFIX}confirm.csv"
LEGACY_HEARTBEAT_FILE = f"{PREFIX}heartbeat.txt"
LEGACY_EXIT_FILE = f"{PREFIX}exit.csv"
LEGACY_STATUS_FILE = f"{PREFIX}status.txt"


class Bridge:
    """
    Signal bridge between Python and MT5 EA.
    Uses flag-based shared memory files + legacy CSV fallback.
    """

    def __init__(self, mt5_common_path: Optional[str] = None):
        self._lock = threading.Lock()
        self._confirm_lock = threading.Lock()
        self._signals_sent = 0

        if mt5_common_path:
            self.common_path = Path(mt5_common_path)
        else:
            self.common_path = self._detect_mt5_common_path()

        self.common_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"[Bridge] Path: {self.common_path}")

    @staticmethod
    def _detect_mt5_common_path() -> Path:
        """Auto-detect MT5 Common Files path."""
        env_path = os.environ.get("MT5_COMMON_PATH")
        if env_path and os.path.isdir(env_path):
            return Path(env_path)

        appdata = os.environ.get("APPDATA", "")
        default = Path(appdata) / "MetaQuotes" / "Terminal" / "Common" / "Files"
        if default.exists():
            return default

        fallback = Path.cwd() / "mt5_common"
        fallback.mkdir(exist_ok=True)
        return fallback

    def write_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Write a trade signal for MT5 to read.

        Args:
            signal: Dict with keys: action, confidence, lot_size, symbol, etc.

        Returns:
            True if written successfully.
        """
        with self._lock:
            try:
                line = self._format_signal_line(signal)

                # Flag-based write
                data_path = self.common_path / SIGNAL_DATA_FILE
                data_path.write_text(line, encoding="ascii")
                flag_path = self.common_path / SIGNAL_FLAG_FILE
                flag_path.write_text("1", encoding="utf-16")

                # Legacy CSV fallback
                self._write_legacy_signal(line)

                self._signals_sent += 1
                return True
            except Exception as e:
                logger.error(f"[Bridge] Signal write error: {e}")
                return False

    def _format_signal_line(self, signal: Dict[str, Any]) -> str:
        """Format signal as CSV line."""
        timestamp = signal.get("timestamp",
                               datetime.now().strftime("%Y.%m.%d %H:%M:%S"))
        symbol = signal.get("symbol", Config.SYMBOL)
        action = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 1.0)
        sl_pips = signal.get("sl_pips", 0.0)
        tp_pips = signal.get("tp_pips", 9999.0)
        lot_size = signal.get("lot_size", Config.LOT_SIZE)
        model_name = signal.get("model_name", "momentum_v9")
        regime = signal.get("regime", "momentum")
        entry_type = signal.get("entry_type", "MARKET")
        limit_price = signal.get("limit_price", 0.0)

        return (f"{timestamp},{symbol},{action},"
                f"{confidence:.4f},{sl_pips:.1f},{tp_pips:.1f},"
                f"{lot_size:.2f},{model_name},{regime},"
                f"{entry_type},{limit_price:.5f}")

    def _write_legacy_signal(self, line: str):
        """Write legacy CSV signal file."""
        header = ("timestamp,symbol,action,confidence,sl_pips,tp_pips,"
                  "lot_size,model_name,regime,entry_type,limit_price")
        csv_path = self.common_path / LEGACY_SIGNAL_FILE
        csv_path.write_text(f"{header}\n{line}\n", encoding="ascii")

    def write_exit_signal(self, ticket, action: str = "CLOSE_FULL",
                          lot_pct: float = 1.0, new_sl: float = 0.0,
                          reason: str = "trailing_stop") -> bool:
        """Write an exit signal for the EA."""
        try:
            line = f"{ticket},{action},{lot_pct:.2f},{new_sl:.5f},{reason}"

            # Flag-based
            data_path = self.common_path / EXIT_DATA_FILE
            with open(data_path, "a", encoding="ascii") as f:
                f.write(line + "\n")
            flag_path = self.common_path / EXIT_FLAG_FILE
            flag_path.write_text("1", encoding="utf-16")

            # Legacy CSV
            csv_path = self.common_path / LEGACY_EXIT_FILE
            timestamp = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
            header = "timestamp,ticket,action,lot_pct,new_sl,reason"
            csv_line = f"{timestamp},{ticket},{action},{lot_pct:.2f},{new_sl:.5f},{reason}"
            csv_path.write_text(f"{header}\n{csv_line}\n", encoding="ascii")

            return True
        except Exception as e:
            logger.error(f"[Bridge] Exit signal error: {e}")
            return False

    def write_heartbeat(self) -> bool:
        """Write Python heartbeat for MT5 connection detection."""
        try:
            hb_path = self.common_path / LEGACY_HEARTBEAT_FILE
            timestamp = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
            hb_path.write_text(timestamp + "\n", encoding="ascii")
            return True
        except Exception:
            return False

    def write_intelligence(self, strategy: str = "EMA_TREND", decision: str = "WAITING",
                           reason: str = "", ema_trend: str = "",
                           regime: str = "EMA", atr_value: float = 0.0,
                           atr_pass: bool = True, tick_pct: float = 0.0,
                           tick_dir: str = "", persistence_count: int = 0,
                           persistence_dir: str = "",
                           choppy_votes: str = "",
                           swing_sl: str = "",
                           breakeven_status: str = "",
                           reversal_status: str = "") -> bool:
        """Write intelligence state for EA dashboard display.

        Writes a pipe-delimited line to the intelligence file. The file is
        overwritten each call so the EA always reads the latest state.

        Primary fields (EMA-only mode):
            strategy: Active strategy (always 'EMA_TREND').
            decision: Overall decision ('TRADING', 'COOLDOWN', 'WAITING').
            reason: Reason for decision (e.g. 'COOLDOWN', 'NEED_EA_EMA').
            ema_trend: EMA trend label from EA data.

        New dashboard fields:
            choppy_votes: Choppy filter status like '2/5 TRENDING' or '3/5 CHOPPY'.
            swing_sl: Current swing SL level string like '$2648.50'.
            breakeven_status: 'INACTIVE' or 'ARMED $5+' or 'LOCKED $1'.
            reversal_status: 'CLEAR' or 'DETECTED'.

        Legacy fields (kept for EA parser compatibility, default to empty/zero):
            regime: Market regime label.
            atr_value: ATR value (unused, defaults to 0).
            atr_pass: ATR pass flag (unused, defaults to True).
            tick_pct: Tick consistency pct (unused, defaults to 0).
            tick_dir: Tick direction (unused, defaults to '').
            persistence_count: Signal persistence count (unused, defaults to 0).
            persistence_dir: Persistence direction (unused, defaults to '').

        Returns:
            True if written successfully.
        """
        try:
            intel_path = self.common_path / Config.INTELLIGENCE_FILE
            atr_pass_str = "1" if atr_pass else "0"
            line = (f"{regime}|{atr_value}|{atr_pass_str}|{tick_pct}|{tick_dir}|"
                    f"{persistence_count}|{persistence_dir}|{strategy}|{decision}|{reason}|"
                    f"{ema_trend}|{choppy_votes}|{swing_sl}|{breakeven_status}|{reversal_status}")
            intel_path.write_text(line, encoding="ascii")
            return True
        except Exception:
            return False

    def write_brain_settings(self, be_profit: float, trail_start: float,
                             trail_distance: float) -> bool:
        """Write brain settings CSV for EA dynamic trail overrides.

        Creates/overwrites neurox_v9_brain_settings.csv with trailing parameters
        that the EA reads to dynamically tighten or loosen its trailing stop.

        Args:
            be_profit: Break-even profit threshold.
            trail_start: Profit level to start trailing.
            trail_distance: Trailing stop distance.

        Returns:
            True if written successfully.
        """
        try:
            csv_path = self.common_path / Config.BRAIN_SETTINGS_FILE
            content = (
                "setting,value\n"
                f"g_brain_be_profit,{be_profit:.2f}\n"
                f"g_brain_trail_start,{trail_start:.2f}\n"
                f"g_brain_trail_distance,{trail_distance:.2f}\n"
            )
            csv_path.write_text(content, encoding="ascii")
            return True
        except Exception as e:
            logger.error(f"[Bridge] Brain settings write error: {e}")
            return False

    def write_performance_state(self, tracker_data: dict) -> bool:
        """Serialize rolling tracker state to performance JSON file.

        Writes the tracker state to PERFORMANCE_FILE so state persists
        across restarts.

        Args:
            tracker_data: Dict with trades list and performance metrics.

        Returns:
            True if written successfully.
        """
        import json
        try:
            perf_path = self.common_path / Config.PERFORMANCE_FILE
            perf_path.write_text(
                json.dumps(tracker_data, indent=2),
                encoding="utf-8"
            )
            return True
        except Exception as e:
            logger.error(f"[Bridge] Performance state write error: {e}")
            return False

    def read_confirmation(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Read trade execution confirmation from MT5.

        Args:
            timeout: Max seconds to wait.

        Returns:
            Dict with confirmation data, or None.
        """
        start = time.time()
        while True:
            confirm = self._try_read_confirmation()
            if confirm is not None:
                return confirm
            if time.time() - start >= timeout:
                return None
            time.sleep(0.01)

    def _try_read_confirmation(self) -> Optional[Dict[str, Any]]:
        """Non-blocking confirmation read."""
        with self._confirm_lock:
            try:
                # Flag-based
                flag_path = self.common_path / CONFIRM_FLAG_FILE
                if flag_path.exists():
                    flag_val = flag_path.read_text(encoding="utf-16").strip()
                    if flag_val == "1":
                        data_path = self.common_path / CONFIRM_DATA_FILE
                        if data_path.exists():
                            line = data_path.read_text(encoding="utf-16").strip()
                            flag_path.write_text("0", encoding="utf-16")
                            return self._parse_confirmation(line)

                # Legacy CSV fallback
                csv_path = self.common_path / LEGACY_CONFIRM_FILE
                if csv_path.exists():
                    content = csv_path.read_text(encoding="utf-8").strip()
                    lines = content.split("\n")
                    if len(lines) >= 2:
                        return self._parse_confirmation(lines[1])
            except Exception:
                pass
        return None

    def _parse_confirmation(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse confirmation CSV line."""
        parts = line.strip().split(",")
        if len(parts) < 9:
            return None
        try:
            return {
                "timestamp": parts[0],
                "ticket": int(parts[1]) if parts[1].isdigit() else 0,
                "symbol": parts[2],
                "action": parts[3],
                "lot_size": float(parts[4]),
                "open_price": float(parts[5]),
                "sl": float(parts[6]),
                "tp": float(parts[7]),
                "status": parts[8],
                "profit": float(parts[9]) if len(parts) > 9 else 0.0,
            }
        except (ValueError, IndexError):
            return None

    def check_mt5_connection(self) -> bool:
        """Check if MT5 EA is running by reading its heartbeat."""
        try:
            hb_path = self.common_path / f"{PREFIX}mt5_heartbeat.txt"
            if not hb_path.exists():
                return False
            content = hb_path.read_text(encoding="ascii").strip()
            if not content:
                return False
            ts = datetime.strptime(content, "%Y.%m.%d %H:%M:%S")
            age = (datetime.now() - ts).total_seconds()
            return age < 5.0
        except Exception:
            return False

    def clear_flags(self):
        """Clear all flag files on startup."""
        for flag in [SIGNAL_FLAG_FILE, CONFIRM_FLAG_FILE, EXIT_FLAG_FILE]:
            try:
                (self.common_path / flag).write_text("0", encoding="utf-16")
            except Exception:
                pass

    @property
    def signals_sent(self) -> int:
        return self._signals_sent
