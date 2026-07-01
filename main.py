"""
NeuroX v9.0 - EMA Trend Trader
Main loop: read ticks, read EMA from EA, fire signal on EMA direction.
Zero network dependency - reads local tick price file from EA.
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime

from config import Config
from bridge import Bridge
from tick_collector import TickCollector

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
    """Read EMA 9, EMA 15, max_distance, open positions, and ADX from EA.

    The EA writes EMA values from the live chart to a shared file every tick,
    giving Python instant access to accurate EMA without warmup.
    Format: ema9|ema15|max_distance|open_positions|adx_value

    Returns:
        (ema9, ema15, max_distance, open_positions, adx_value) or
        (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0) if unavailable.
    """
    try:
        ema_path = bridge.common_path / Config.EMA_FILE
        if not ema_path.exists():
            return (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0)
        content = ema_path.read_text(encoding="utf-16").strip()
        if "|" not in content:
            return (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0)
        parts = content.split("|")
        ema9 = float(parts[0])
        ema15 = float(parts[1])
        max_distance = float(parts[2]) if len(parts) >= 3 else Config.EMA_MAX_DISTANCE
        open_positions = int(parts[3]) if len(parts) >= 4 else 0
        adx_value = float(parts[4]) if len(parts) >= 5 else 100.0
        return (ema9, ema15, max_distance, open_positions, adx_value)
    except Exception:
        return (0.0, 0.0, Config.EMA_MAX_DISTANCE, 0, 100.0)


def get_ema_trend_label_from_ea(ea_ema9: float, ea_ema15: float, current_price: float) -> str:
    """Get EMA crossover trend label using EA-provided EMA values.

    Args:
        ea_ema9: EMA 9 value from EA file.
        ea_ema15: EMA 15 value from EA file.
        current_price: Current tick price.

    Returns:
        Label like '9>15 BUY $0.45' or '9<15 SELL $1.50' or 'WARMUP'.
    """
    if ea_ema9 <= 0 or ea_ema15 <= 0:
        return "WARMUP"
    distance = abs(current_price - ea_ema9)
    if ea_ema9 > ea_ema15:
        return f"9>15 BUY ${distance:.2f}"
    elif ea_ema9 < ea_ema15:
        return f"9<15 SELL ${distance:.2f}"
    else:
        return "FLAT"


def fire_signal(bridge: Bridge, direction: str, price: float, label: str):
    """Fire a trade signal and update cooldown state."""
    global last_signal_time

    sig = create_signal(direction, price)
    if bridge.write_signal(sig):
        last_signal_time = time.time()
        logger.info(f"{label}: {direction} @ ${price:.2f}")


def create_signal(direction: str, price: float) -> dict:
    """Create a signal dict for the bridge.

    Args:
        direction: 'BUY' or 'SELL'.
        price: Current price at signal time.
    """
    lot = Config.LOT_SIZE
    lot = max(Config.MIN_LOT_SIZE, min(lot, Config.MAX_LOT_SIZE))
    lot = round(lot, 2)

    return {
        "timestamp": datetime.now().strftime("%Y.%m.%d %H:%M:%S"),
        "symbol": Config.SYMBOL,
        "action": direction,
        "confidence": 1.0,
        "sl_pips": 0.0,
        "tp_pips": 9999.0,
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

    logger.info("Main loop running. Ctrl+C to stop.")

    try:
        while running:
            # 1. Write heartbeat
            bridge.write_heartbeat()

            # 2. Read tick (for current price)
            tick_collector.update()
            current_price = tick_collector.last_price

            # 3. Read EMA from EA file (includes open position count)
            ea_ema9, ea_ema15, ea_max_distance, ea_open_positions, ea_adx = read_ema_from_ea(bridge)

            # Determine EMA direction via crossover (9 vs 15)
            # Only BUY when EMA 9 > EMA 15, only SELL when EMA 15 > EMA 9
            # This ensures no two-side trades at the same time
            ema_allowed_direction = None
            if ea_ema9 > 0.0 and ea_ema15 > 0.0:
                if ea_ema9 > ea_ema15:
                    ema_allowed_direction = "BUY"
                elif ea_ema9 < ea_ema15:
                    ema_allowed_direction = "SELL"

            # 4. Signal logic: momentum-based scaling using EA's actual position count
            intel_decision = "WAITING"
            intel_reason = ""

            if ema_allowed_direction is not None and current_price > 0.0:
                distance = abs(current_price - ea_ema9)
                if ea_adx < Config.MIN_ADX_THRESHOLD:
                    intel_decision = "FILTERED"
                    intel_reason = "ADX_RANGING"
                elif distance > ea_max_distance:
                    intel_decision = "FILTERED"
                    intel_reason = "EMA_DISTANCE"
                elif ea_open_positions >= Config.MAX_POSITIONS:
                    intel_decision = "MAX_POS"
                    intel_reason = ""
                elif ea_open_positions >= 1:
                    # Already have position(s) - scale only on momentum
                    tick_momentum = tick_collector.get_tick_momentum()
                    tick_strength = tick_collector.get_tick_momentum_strength()
                    if (tick_momentum == ema_allowed_direction
                            and tick_strength >= Config.SCALE_IN_THRESHOLD
                            and can_trade()):
                        fire_signal(bridge, ema_allowed_direction, current_price, "SCALE IN")
                        intel_decision = "SCALING"
                        intel_reason = ""
                    else:
                        intel_decision = "HOLDING"
                        intel_reason = ""
                elif can_trade():
                    # No positions - fire first entry
                    fire_signal(bridge, ema_allowed_direction, current_price, "EMA TREND")
                    intel_decision = "TRADING"
                    intel_reason = ""
                else:
                    intel_decision = "COOLDOWN"
                    intel_reason = "COOLDOWN"
            elif current_price > 0.0 and (ea_ema9 <= 0.0 or ea_ema15 <= 0.0):
                intel_decision = "WAITING"
                intel_reason = "NEED_EA_EMA"
            elif current_price <= 0.0:
                intel_decision = "WAITING"
                intel_reason = "NO_TICK"
            else:
                intel_decision = "WAITING"
                intel_reason = "FLAT"

            # 5. Write intelligence (EMA_TREND, decision)
            ema_label = get_ema_trend_label_from_ea(ea_ema9, ea_ema15, current_price)
            adx_label = f"ADX={ea_adx:.1f}"
            bridge.write_intelligence(
                strategy="EMA_TREND",
                decision=intel_decision,
                reason=intel_reason,
                ema_trend=f"{ema_label} {adx_label}",
            )

            # 6. Sleep 100ms
            time.sleep(Config.LOOP_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        logger.info(f"NeuroX v{Config.VERSION} stopped.")


if __name__ == "__main__":
    main()
