"""
NeuroX v9.0 - EMA Trend Trader
Main loop: read ticks, read EMA from EA, fire signal on EMA direction.
Candle-close exit system: entry -> wait for M1 candle close -> exit -> re-evaluate.
Zero network dependency - reads local tick price file from EA.
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime

import numpy as np
import pandas as pd

from config import Config
from bridge import Bridge
from tick_collector import TickCollector
from choppy_filter import is_market_choppy, count_choppy_votes
from swing_levels import compute_swing_sl
from trailing_stop import CandleCloseManager
from momentum import compute_atr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("NeuroX")

# Global state
running = True
last_signal_time = 0.0
current_price = 0.0


def shutdown_handler(signum, frame):
    global running
    logger.info("Shutdown signal received")
    running = False


signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)


def can_trade() -> bool:
    """Check cooldown between trades."""
    elapsed = time.time() - last_signal_time
    return elapsed >= Config.COOLDOWN_SECONDS


def read_ema_from_ea(bridge) -> tuple:
    """Read EMA 9, EMA 15, max_distance, open positions, ADX, and additional indicators from EA.

    The EA writes EMA values from the live chart to a shared file every tick,
    giving Python instant access to accurate EMA without warmup.
    Format: ema9|ema15|max_distance|open_positions|adx_value|swing_high|swing_low|bb_upper|bb_lower|choppiness

    Returns:
        (ema9, ema15, max_distance, open_positions, adx_value,
         swing_high, swing_low, bb_upper, bb_lower, choppiness) or
        defaults if unavailable.
    """
    defaults = (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    try:
        ema_path = bridge.common_path / Config.EMA_FILE
        if not ema_path.exists():
            return defaults
        content = ema_path.read_text(encoding="utf-16").strip()
        if "|" not in content:
            return defaults
        parts = content.split("|")
        ema9 = float(parts[0])
        ema15 = float(parts[1])
        max_distance = float(parts[2]) if len(parts) >= 3 else Config.EMA_MAX_DISTANCE
        open_positions = int(parts[3]) if len(parts) >= 4 else 0
        adx_value = float(parts[4]) if len(parts) >= 5 else 100.0
        swing_high = float(parts[5]) if len(parts) >= 6 else 0.0
        swing_low = float(parts[6]) if len(parts) >= 7 else 0.0
        bb_upper = float(parts[7]) if len(parts) >= 8 else 0.0
        bb_lower = float(parts[8]) if len(parts) >= 9 else 0.0
        choppiness = float(parts[9]) if len(parts) >= 10 else 0.0
        return (ema9, ema15, max_distance, open_positions, adx_value,
                swing_high, swing_low, bb_upper, bb_lower, choppiness)
    except Exception:
        return defaults


def get_ema_trend_label_from_ea(ea_ema9: float, ea_ema15: float, current_price: float) -> str:
    """Get EMA trend label using price vs EMA 9 direction.

    Args:
        ea_ema9: EMA 9 value from EA file.
        ea_ema15: EMA 15 value from EA file (kept for compatibility, unused for direction).
        current_price: Current tick price.

    Returns:
        Label like 'P>EMA9 BUY $0.45' or 'P<EMA9 SELL $1.50' or 'WARMUP'.
    """
    if ea_ema9 <= 0:
        return "WARMUP"
    distance = abs(current_price - ea_ema9)
    if current_price > ea_ema9:
        return f"P>EMA9 BUY ${distance:.2f}"
    elif current_price < ea_ema9:
        return f"P<EMA9 SELL ${distance:.2f}"
    else:
        return "FLAT"


def fire_signal(bridge: Bridge, direction: str, price: float, label: str,
                sl_pips: float = 0.0):
    """Fire a trade signal and update cooldown state."""
    global last_signal_time

    sig = create_signal(direction, price, sl_pips=sl_pips)
    if bridge.write_signal(sig):
        last_signal_time = time.time()
        logger.info(f"{label}: {direction} @ ${price:.2f} SL=${sl_pips:.2f}")


def create_signal(direction: str, price: float, sl_pips: float = 0.0) -> dict:
    """Create a signal dict for the bridge.

    Args:
        direction: 'BUY' or 'SELL'.
        price: Current price at signal time.
        sl_pips: Stop loss distance in $ (swing high/low distance).
    """
    lot = Config.LOT_SIZE
    lot = max(Config.MIN_LOT_SIZE, min(lot, Config.MAX_LOT_SIZE))
    lot = round(lot, 2)

    # No TP when candle-close exit is active
    tp_pips = 0.0 if Config.NO_TP else 9999.0

    return {
        "timestamp": datetime.now().strftime("%Y.%m.%d %H:%M:%S"),
        "symbol": Config.SYMBOL,
        "action": direction,
        "confidence": 1.0,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "lot_size": lot,
        "model_name": "ema_trend_v9",
        "regime": "momentum",
        "entry_type": "MARKET",
        "limit_price": 0.0,
    }


def main():
    global running, last_signal_time, current_price

    logger.info(f"NeuroX v{Config.VERSION} starting (magic={Config.MAGIC_NUMBER})")

    bridge = Bridge()
    bridge.clear_flags()

    # Build tick file path from MT5 common path
    tick_file_path = os.path.join(
        str(bridge.common_path), Config.TICK_FILE
    )

    tick_collector = TickCollector(tick_file_path)

    # Candle close manager for exit management
    def get_bar_minute():
        if tick_collector._bar_start_minute is not None:
            return tick_collector._bar_start_minute.minute
        return None

    def get_current_bar():
        if tick_collector._bar_open > 0.0:
            return {
                "Open": tick_collector._bar_open,
                "High": tick_collector._bar_high,
                "Low": tick_collector._bar_low,
                "Close": tick_collector._bar_close,
            }
        return None

    def get_recent_bars():
        return list(tick_collector._completed_bars)

    candle_mgr = CandleCloseManager(
        get_price_fn=lambda: tick_collector.last_price,
        write_exit_fn=lambda ticket, action, lot_pct, new_sl, reason:
            bridge.write_exit_signal(ticket, action, lot_pct, new_sl, reason),
        get_bar_minute_fn=get_bar_minute,
        get_current_bar_fn=get_current_bar,
        get_recent_bars_fn=get_recent_bars,
    )
    candle_mgr.start()

    logger.info("Main loop running (candle-close exit mode). Ctrl+C to stop.")

    try:
        while running:
            # 1. Write heartbeat
            bridge.write_heartbeat()

            # 2. Read tick (for current price)
            tick_collector.update()
            current_price = tick_collector.last_price

            # 3. Read EMA from EA file (includes open position count)
            ea_ema9, ea_ema15, ea_max_distance, ea_open_positions, ea_adx, \
                ea_swing_high, ea_swing_low, ea_bb_upper, ea_bb_lower, ea_choppiness = read_ema_from_ea(bridge)

            # Determine EMA direction via price vs EMA 9
            # Only BUY when price > EMA 9, only SELL when price < EMA 9
            ema_allowed_direction = None
            if ea_ema9 > 0.0 and current_price > 0.0:
                if current_price > ea_ema9:
                    ema_allowed_direction = "BUY"
                elif current_price < ea_ema9:
                    ema_allowed_direction = "SELL"

            # 4. Signal logic: single position, candle-close exit cycle
            intel_decision = "WAITING"
            intel_reason = ""
            computed_atr = 0.0
            computed_avg_atr = 0.0
            computed_variance_ratio = 1.0

            if ema_allowed_direction is not None and current_price > 0.0:
                distance = abs(current_price - ea_ema9)

                # Multi-indicator choppy market filter
                # Compute ATR and variance ratio from completed bars to
                # activate the ATR-ratio and variance-ratio voters
                choppy, choppy_reason = False, ""
                computed_atr = 0.0
                computed_avg_atr = 0.0
                computed_variance_ratio = 1.0

                completed_bars = list(tick_collector._completed_bars)
                if len(completed_bars) >= Config.ATR_RATIO_PERIOD + 1:
                    bars_df = pd.DataFrame(completed_bars)
                    computed_atr, computed_avg_atr = compute_atr(
                        bars_df, period=Config.ATR_RATIO_PERIOD
                    )

                    # Compute variance ratio from close prices
                    vr_lookback = Config.REGIME_VARIANCE_RATIO_LOOKBACK
                    if len(completed_bars) >= vr_lookback + 1:
                        close_arr = bars_df["Close"].values[-(vr_lookback + 1):]
                        increments = np.diff(close_arr)
                        var_increments = np.var(increments)
                        if var_increments > 0:
                            n = len(increments)
                            full_move = close_arr[-1] - close_arr[0]
                            expected_walk_var = n * var_increments
                            actual_walk_var = full_move ** 2
                            computed_variance_ratio = actual_walk_var / expected_walk_var

                if Config.CHOPPY_FILTER_ENABLED:
                    choppy, choppy_reason = is_market_choppy(
                        adx_value=ea_adx,
                        choppiness_index=ea_choppiness,
                        bb_upper=ea_bb_upper,
                        bb_lower=ea_bb_lower,
                        current_price=current_price,
                        current_atr=computed_atr,
                        avg_atr=computed_avg_atr,
                        variance_ratio=computed_variance_ratio,
                    )

                if choppy:
                    intel_decision = "FILTERED"
                    intel_reason = f"CHOPPY_MARKET:{choppy_reason}"
                elif distance > ea_max_distance:
                    intel_decision = "FILTERED"
                    intel_reason = "EMA_DISTANCE"
                elif ea_open_positions >= Config.MAX_POSITIONS:
                    intel_decision = "MAX_POS"
                    intel_reason = ""
                elif candle_mgr.is_tracking:
                    # Already have a position being managed - wait for candle close
                    intel_decision = "HOLDING"
                    intel_reason = "CANDLE_WAIT"
                elif can_trade():
                    # No position - fire entry with swing SL
                    # Use EA-provided swing levels as fallback when Python
                    # bar buffer has fewer than SWING_SL_LOOKBACK bars
                    if not completed_bars:
                        completed_bars = list(tick_collector._completed_bars)
                    swing_sl = compute_swing_sl(
                        completed_bars, ema_allowed_direction, current_price,
                        ea_swing_high=ea_swing_high,
                        ea_swing_low=ea_swing_low,
                    )
                    # Convert swing SL to distance
                    sl_distance = abs(current_price - swing_sl)

                    fire_signal(
                        bridge, ema_allowed_direction, current_price,
                        "EMA TREND", sl_pips=sl_distance
                    )
                    # Start tracking for candle-close exit
                    candle_mgr.start_tracking(
                        ema_allowed_direction, current_price, "latest"
                    )
                    intel_decision = "TRADING"
                    intel_reason = ""
                else:
                    intel_decision = "COOLDOWN"
                    intel_reason = "COOLDOWN"
            elif current_price > 0.0 and ea_ema9 <= 0.0:
                intel_decision = "WAITING"
                intel_reason = "NEED_EA_EMA"
            elif current_price <= 0.0:
                intel_decision = "WAITING"
                intel_reason = "NO_TICK"
            else:
                intel_decision = "WAITING"
                intel_reason = "FLAT"

            # Check if candle close manager has closed the position
            if candle_mgr.close_fired:
                candle_mgr.stop_tracking()

            # 5. Write intelligence (EMA_TREND, decision)
            ema_label = get_ema_trend_label_from_ea(ea_ema9, ea_ema15, current_price)
            adx_label = f"ADX={ea_adx:.1f}"

            # Compute choppy votes for dashboard
            choppy_vote_count = count_choppy_votes(
                adx_value=ea_adx,
                choppiness_index=ea_choppiness,
                bb_upper=ea_bb_upper,
                bb_lower=ea_bb_lower,
                current_price=current_price,
                current_atr=computed_atr,
                avg_atr=computed_avg_atr,
                variance_ratio=computed_variance_ratio,
            )
            choppy_label = f"{choppy_vote_count}/5 CHOPPY" if choppy_vote_count >= Config.RANGING_FILTER_AGREEMENT else f"{choppy_vote_count}/5 TRENDING"

            # EMA distance for dashboard
            ema_distance_str = ""
            if ea_ema9 > 0.0 and current_price > 0.0:
                dist = abs(current_price - ea_ema9)
                ema_distance_str = f"${dist:.2f} / ${ea_max_distance:.2f}"

            # Swing SL for dashboard
            swing_sl_str = ""
            if candle_mgr.is_tracking and hasattr(candle_mgr, '_entry_price'):
                # Show the swing SL that was computed at entry
                swing_sl_str = "ACTIVE"
            else:
                swing_sl_str = "---"

            # Breakeven status for dashboard
            be_status_str = "INACTIVE"
            if candle_mgr.is_tracking:
                if candle_mgr.be_moved:
                    be_status_str = f"LOCKED ${Config.BREAKEVEN_LOCK_AMOUNT:.0f}"
                else:
                    be_status_str = f"ARMED ${Config.BREAKEVEN_PROFIT_THRESHOLD:.0f}+"

            # Reversal status for dashboard
            reversal_str = "CLEAR"

            bridge.write_intelligence(
                strategy="EMA_TREND",
                decision=intel_decision,
                reason=intel_reason,
                ema_trend=f"{ema_label} {adx_label}",
                choppy_votes=choppy_label,
                swing_sl=swing_sl_str,
                breakeven_status=be_status_str,
                reversal_status=reversal_str,
            )

            # 6. Sleep 100ms
            time.sleep(Config.LOOP_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        candle_mgr.stop()
        logger.info(f"NeuroX v{Config.VERSION} stopped.")


if __name__ == "__main__":
    main()
