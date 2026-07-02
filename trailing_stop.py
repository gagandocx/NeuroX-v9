"""
NeuroX v9.0 - Candle Close Manager

Replaces the old 4-tier TrailingStopManager. New system:
- Trades close at M1 candle close (when minute changes)
- $5 profit breakeven: moves SL to entry + $1
- Advanced M1 reversal detection for early loss cutting
- Runs on 100ms interval like old trailing stop
"""

import time
import logging
import threading
from typing import Optional, Callable, List

from config import Config

logger = logging.getLogger("CandleClose")


class CandleCloseManager:
    """
    Manages candle-close exits for a single active position.

    Reads price via a callable at 100ms intervals. When a new M1 candle
    closes (minute changes), fires a CLOSE_FULL exit signal. Also handles
    $5 breakeven move and reversal detection for early exit.
    """

    def __init__(
        self,
        get_price_fn: Callable[[], float],
        write_exit_fn: Callable,
        get_bar_minute_fn: Callable[[], Optional[int]] = None,
        get_current_bar_fn: Callable[[], Optional[dict]] = None,
        get_recent_bars_fn: Callable[[], List[dict]] = None,
        check_interval_ms: int = 100,
    ):
        """
        Args:
            get_price_fn: Callable that returns current price (float).
                          Should return 0.0 if price unavailable.
            write_exit_fn: Callable with signature
                (ticket, action, lot_pct, new_sl, reason) -> bool
            get_bar_minute_fn: Callable returning current bar's start minute (int 0-59)
                               or None if no bar started yet.
            get_current_bar_fn: Callable returning current forming bar dict
                                {Open, High, Low, Close} or None.
            get_recent_bars_fn: Callable returning list of recent completed bar dicts.
            check_interval_ms: Milliseconds between price checks.
        """
        self._get_price = get_price_fn
        self._write_exit = write_exit_fn
        self._get_bar_minute = get_bar_minute_fn
        self._get_current_bar = get_current_bar_fn
        self._get_recent_bars = get_recent_bars_fn
        self._check_interval_s = check_interval_ms / 1000.0

        # Position tracking state
        self._tracking = False
        self._direction: Optional[str] = None
        self._entry_price: float = 0.0
        self._ticket: str = ""
        self._entry_time: float = 0.0

        # Candle tracking
        self._last_bar_minute: Optional[int] = None
        self._be_moved = False  # Whether breakeven has been applied

        # Close-fired flag for race prevention
        self._close_fired = threading.Event()

        # Thread control
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the background monitoring thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="CandleCloseMonitor"
        )
        self._thread.start()
        logger.info("[CandleClose] Monitor thread started")

    def stop(self):
        """Stop the background monitoring thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("[CandleClose] Monitor thread stopped")

    def start_tracking(self, direction: str, entry_price: float, ticket: str):
        """
        Begin tracking a new position for candle-close exit.

        Args:
            direction: "BUY" or "SELL"
            entry_price: Position entry price.
            ticket: Position ticket or ID string.
        """
        with self._lock:
            self._tracking = True
            self._direction = direction
            self._entry_price = entry_price
            self._ticket = ticket
            self._entry_time = time.time()
            self._be_moved = False
            # Snapshot the current bar minute at entry
            if self._get_bar_minute:
                self._last_bar_minute = self._get_bar_minute()
            else:
                self._last_bar_minute = None
        self._close_fired.clear()
        logger.info(
            f"[CandleClose] Tracking: {direction} @ ${entry_price:.2f} ticket={ticket}"
        )

    def stop_tracking(self):
        """Stop tracking the current position."""
        with self._lock:
            self._tracking = False
            self._direction = None
            self._entry_price = 0.0
            self._ticket = ""
            self._entry_time = 0.0
            self._last_bar_minute = None
            self._be_moved = False
        self._close_fired.clear()

    @property
    def is_tracking(self) -> bool:
        """Whether we are currently tracking a position."""
        return self._tracking

    @property
    def close_fired(self) -> bool:
        """Whether candle close exit has fired for current position."""
        return self._close_fired.is_set()

    @property
    def be_moved(self) -> bool:
        """Whether breakeven has been applied to the current position."""
        return self._be_moved

    def _compute_pnl(self, current_price: float) -> float:
        """Compute unrealized P&L in dollars."""
        if self._direction == "BUY":
            return current_price - self._entry_price
        elif self._direction == "SELL":
            return self._entry_price - current_price
        return 0.0

    def _check_candle_close(self) -> bool:
        """
        Check if a new M1 candle has closed (minute changed).

        NOTE: Known limitation - single-minute resolution creates a race window.
        If the 100ms loop misses a brief minute boundary (e.g., system load
        delay > 1 second), the signal fires on the following check but may be
        off by one candle. This is unlikely under normal conditions and
        acceptable given the 100ms check interval.

        Returns:
            True if candle close detected, False otherwise.
        """
        if self._get_bar_minute is None:
            return False

        current_minute = self._get_bar_minute()
        if current_minute is None:
            return False

        if self._last_bar_minute is None:
            self._last_bar_minute = current_minute
            return False

        if current_minute != self._last_bar_minute:
            self._last_bar_minute = current_minute
            return True

        return False

    def _check_breakeven(self, current_price: float) -> bool:
        """
        Check if profit >= $5 threshold to move SL to breakeven (entry + $1).

        Returns:
            True if BE move should be applied, False otherwise.
        """
        if self._be_moved:
            return False

        pnl = self._compute_pnl(current_price)
        return pnl >= Config.BREAKEVEN_PROFIT_THRESHOLD

    def _get_be_sl_price(self) -> float:
        """Compute the breakeven SL price (entry + $1 lock)."""
        lock = Config.BREAKEVEN_LOCK_AMOUNT
        if self._direction == "BUY":
            return self._entry_price + lock
        elif self._direction == "SELL":
            return self._entry_price - lock
        return self._entry_price

    def _check_reversal(self, current_price: float) -> bool:
        """
        Check if the current forming candle is a high-momentum reversal
        against the trade direction.

        NOTE: Known limitation - reversal detection is unavailable during
        cold start. _get_recent_bars() must return >= 3 bars for ATR
        comparison. On Python restart, this takes 3+ minutes of quiet
        accumulation. During this window, the only protection is the swing
        SL (which uses EA-provided swing levels as fallback at startup).

        Criteria:
        - Large body (>= REVERSAL_CANDLE_BODY_MIN)
        - Body ratio (>= REVERSAL_CANDLE_BODY_RATIO of full range)
        - Candle range >= REVERSAL_ATR_MULT * recent average bar range
        - Direction of candle is against the trade

        Returns:
            True if reversal detected, False otherwise.
        """
        if not Config.REVERSAL_DETECTION_ENABLED:
            return False

        if self._get_current_bar is None or self._get_recent_bars is None:
            return False

        current_bar = self._get_current_bar()
        if current_bar is None:
            return False

        bar_open = current_bar.get("Open", 0.0)
        bar_high = current_bar.get("High", 0.0)
        bar_low = current_bar.get("Low", 0.0)
        bar_close = current_bar.get("Close", 0.0)

        if bar_high == 0.0 or bar_low == 0.0:
            return False

        # Compute body and range
        body = abs(bar_close - bar_open)
        candle_range = bar_high - bar_low

        if candle_range <= 0:
            return False

        # Check minimum body size
        if body < Config.REVERSAL_CANDLE_BODY_MIN:
            return False

        # Check body ratio
        body_ratio = body / candle_range
        if body_ratio < Config.REVERSAL_CANDLE_BODY_RATIO:
            return False

        # Check candle direction is against our trade
        candle_direction = "BUY" if bar_close > bar_open else "SELL"
        if self._direction == "BUY" and candle_direction != "SELL":
            return False
        if self._direction == "SELL" and candle_direction != "BUY":
            return False

        # Check candle range vs recent ATR average
        recent_bars = self._get_recent_bars()
        if recent_bars and len(recent_bars) >= 3:
            ranges = [b["High"] - b["Low"] for b in recent_bars[-10:] if b["High"] > b["Low"]]
            if ranges:
                avg_range = sum(ranges) / len(ranges)
                if candle_range < Config.REVERSAL_ATR_MULT * avg_range:
                    return False
            else:
                return False
        else:
            # Not enough bars for ATR comparison - skip reversal check
            return False

        return True

    def _fire_close(self, reason: str, ticket: str):
        """Fire a CLOSE_FULL exit signal."""
        self._close_fired.set()
        logger.info(f"[CandleClose] CLOSE ticket={ticket} reason={reason}")
        try:
            self._write_exit(
                ticket=ticket,
                action="CLOSE_FULL",
                lot_pct=1.0,
                new_sl=0.0,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"[CandleClose] Failed to write exit: {e}")

    def _fire_modify_sl(self, ticket: str, new_sl: float, reason: str):
        """Fire a MODIFY_SL signal to move stop loss.

        Only marks _be_moved=True after a successful write. If the write
        fails (exception), _be_moved remains False so the next loop
        iteration will retry the breakeven move.
        """
        logger.info(
            f"[CandleClose] MODIFY_SL ticket={ticket} new_sl=${new_sl:.2f} reason={reason}"
        )
        try:
            self._write_exit(
                ticket=ticket,
                action="MODIFY_SL",
                lot_pct=0.0,
                new_sl=new_sl,
                reason=reason,
            )
            # Only mark as moved after successful write
            with self._lock:
                self._be_moved = True
        except Exception as e:
            logger.error(f"[CandleClose] Failed to write SL modify: {e}")
            # _be_moved stays False, will retry on next iteration

    def _monitor_loop(self):
        """Background loop: checks price every interval."""
        while not self._stop_event.is_set():
            try:
                if not self._tracking:
                    self._stop_event.wait(self._check_interval_s)
                    continue

                current_price = self._get_price()
                if current_price <= 0.0:
                    self._stop_event.wait(self._check_interval_s)
                    continue

                fire_reason: Optional[str] = None
                fire_ticket: str = ""
                modify_sl: Optional[float] = None

                with self._lock:
                    if not self._tracking:
                        self._stop_event.wait(self._check_interval_s)
                        continue

                    # Priority 1: Reversal detection (early exit)
                    if self._check_reversal(current_price):
                        fire_reason = "reversal_detected"
                        fire_ticket = self._ticket
                        self._tracking = False
                    # Priority 2: Candle close exit
                    elif self._check_candle_close():
                        fire_reason = "candle_close"
                        fire_ticket = self._ticket
                        self._tracking = False
                    # Priority 3: Breakeven move
                    elif self._check_breakeven(current_price):
                        modify_sl = self._get_be_sl_price()
                        fire_ticket = self._ticket

                if fire_reason is not None:
                    self._fire_close(fire_reason, fire_ticket)
                elif modify_sl is not None:
                    self._fire_modify_sl(
                        fire_ticket, modify_sl, "breakeven_5_lock_1"
                    )

            except Exception as e:
                logger.error(f"[CandleClose] Error: {e}")

            self._stop_event.wait(self._check_interval_s)
