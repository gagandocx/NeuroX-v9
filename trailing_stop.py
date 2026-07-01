"""
NeuroX v9.0 - Trailing Stop Manager

Simplified from v8's strategies/trailing_stop_manager.py.
Same daemon thread with 100ms checks, same 4-tier system.
Uses a get_price_fn callable instead of reading tick files directly.
"""

import time
import logging
import threading
from typing import Optional, Callable, List, Tuple

from config import Config

logger = logging.getLogger("TrailingStop")


class TrailingStopManager:
    """
    Manages trailing stops for a single active position.

    Reads price via a callable at 100ms intervals, computes live P&L,
    and fires exit signals through the bridge when conditions are met.
    """

    def __init__(
        self,
        get_price_fn: Callable[[], float],
        write_exit_fn: Callable,
        tiers: Optional[List[Tuple[float, float]]] = None,
        max_hold_seconds: float = None,
        check_interval_ms: int = 100,
    ):
        """
        Args:
            get_price_fn: Callable that returns current price (float).
                          Should return 0.0 if price unavailable.
            write_exit_fn: Callable with signature
                (ticket, action, lot_pct, new_sl, reason) -> bool
            tiers: List of (profit_threshold, lock_amount) tuples.
            max_hold_seconds: Max seconds before forced close.
            check_interval_ms: Milliseconds between price checks.
        """
        self._get_price = get_price_fn
        self._write_exit = write_exit_fn
        self._tiers = tiers or Config.TRAIL_TIERS
        self._max_hold_seconds = max_hold_seconds or Config.MAX_HOLD_SECONDS
        self._check_interval_s = check_interval_ms / 1000.0

        # Position tracking state
        self._tracking = False
        self._direction: Optional[str] = None
        self._entry_price: float = 0.0
        self._ticket: str = ""
        self._start_time: float = 0.0
        self._active_tier_index: int = -1

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
            target=self._monitor_loop, daemon=True, name="TrailingStopMonitor"
        )
        self._thread.start()
        logger.info("[TrailingStop] Monitor thread started")

    def stop(self):
        """Stop the background monitoring thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("[TrailingStop] Monitor thread stopped")

    def start_tracking(self, direction: str, entry_price: float, ticket: str):
        """
        Begin tracking a new position for trailing stops.

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
            self._start_time = time.time()
            self._active_tier_index = -1
        self._close_fired.clear()
        logger.info(
            f"[TrailingStop] Tracking: {direction} @ ${entry_price:.2f} ticket={ticket}"
        )

    def stop_tracking(self):
        """Stop tracking the current position."""
        with self._lock:
            self._tracking = False
            self._direction = None
            self._entry_price = 0.0
            self._ticket = ""
            self._start_time = 0.0
            self._active_tier_index = -1
        self._close_fired.clear()

    @property
    def is_tracking(self) -> bool:
        """Whether we are currently tracking a position."""
        return self._tracking

    @property
    def close_fired(self) -> bool:
        """Whether trailing stop has fired a close for current position."""
        return self._close_fired.is_set()

    def _compute_pnl(self, current_price: float) -> float:
        """Compute unrealized P&L."""
        if self._direction == "BUY":
            return current_price - self._entry_price
        elif self._direction == "SELL":
            return self._entry_price - current_price
        return 0.0

    def _get_trail_price(self) -> Optional[float]:
        """Compute trailing stop price based on active tier."""
        if self._active_tier_index < 0:
            return None

        _, lock_amount = self._tiers[self._active_tier_index]

        if self._direction == "BUY":
            return self._entry_price + lock_amount
        elif self._direction == "SELL":
            return self._entry_price - lock_amount
        return None

    def _check_trail_hit(self, current_price: float, trail_price: float) -> bool:
        """Check if price has retraced past the trail level."""
        if self._direction == "BUY":
            return current_price <= trail_price
        elif self._direction == "SELL":
            return current_price >= trail_price
        return False

    def _fire_close(self, reason: str, ticket: str):
        """Fire a CLOSE_FULL exit signal."""
        self._close_fired.set()
        logger.info(f"[TrailingStop] CLOSE ticket={ticket} reason={reason}")
        try:
            self._write_exit(
                ticket=ticket,
                action="CLOSE_FULL",
                lot_pct=1.0,
                new_sl=0.0,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"[TrailingStop] Failed to write exit: {e}")

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

                with self._lock:
                    if not self._tracking:
                        self._stop_event.wait(self._check_interval_s)
                        continue

                    # Check max hold time
                    elapsed = time.time() - self._start_time
                    if elapsed >= self._max_hold_seconds:
                        fire_reason = f"max_hold_{self._max_hold_seconds:.0f}s"
                        fire_ticket = self._ticket
                        self._tracking = False
                    else:
                        # Compute P&L and update tiers
                        pnl = self._compute_pnl(current_price)

                        for i, (threshold, _) in enumerate(self._tiers):
                            if pnl >= threshold and i > self._active_tier_index:
                                self._active_tier_index = i
                                logger.info(
                                    f"[TrailingStop] Tier {i}: pnl=${pnl:.2f} "
                                    f">= ${threshold:.2f}"
                                )

                        # Check trail hit
                        trail_price = self._get_trail_price()
                        if trail_price is not None:
                            if self._check_trail_hit(current_price, trail_price):
                                lock = self._tiers[self._active_tier_index][1]
                                fire_reason = (
                                    f"trail_tier{self._active_tier_index}_"
                                    f"lock${lock:.2f}"
                                )
                                fire_ticket = self._ticket
                                self._tracking = False

                if fire_reason is not None:
                    self._fire_close(fire_reason, fire_ticket)

            except Exception as e:
                logger.error(f"[TrailingStop] Error: {e}")

            self._stop_event.wait(self._check_interval_s)
