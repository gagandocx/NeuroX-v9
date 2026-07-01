"""
NeuroX v9.40 - Tick Frequency Spike Detection Module

Counts ticks per second to detect institutional activity.
Normal gold tick rate = 5-15 ticks/sec.
Spike to 50+ ticks/sec = institutional activity, strong move coming.

Logic:
- Count ticks within the last 1 second
- Normal range: 5-15 tps (defined by config)
- Spike threshold: 50+ tps (configurable)
- When tick frequency is high AND momentum aligns, increase conviction
"""

from config import Config


def compute_tick_frequency(tick_timestamps):
    """Compute current tick frequency (ticks per second).

    Counts how many ticks occurred in the most recent measurement window
    (default 1 second).

    Args:
        tick_timestamps: Sequence of timestamps (float, time.time() values)
            corresponding to recent ticks.

    Returns:
        Dict with:
        - 'ticks_per_second': float - Current tick rate
        - 'is_spike': bool - True if rate exceeds spike threshold
        - 'amplifier_mult': float - Signal amplifier multiplier (1.0 normal, up to 1.5 on spike)
        - 'activity_level': str - 'NORMAL', 'ELEVATED', or 'INSTITUTIONAL'
    """
    result = {
        "ticks_per_second": 0.0,
        "is_spike": False,
        "amplifier_mult": 1.0,
        "activity_level": "NORMAL",
    }

    timestamps = list(tick_timestamps)

    if len(timestamps) < 2:
        return result

    now = timestamps[-1]
    measurement_window = Config.TICK_FREQ_MEASUREMENT_WINDOW

    # Count ticks within the measurement window
    count = 0
    for ts in reversed(timestamps):
        if now - ts <= measurement_window:
            count += 1
        else:
            break

    # Calculate ticks per second
    tps = count / measurement_window
    result["ticks_per_second"] = tps

    # Determine activity level and amplifier
    if tps >= Config.TICK_FREQ_SPIKE_THRESHOLD:
        result["is_spike"] = True
        result["activity_level"] = "INSTITUTIONAL"
        result["amplifier_mult"] = Config.TICK_FREQ_SPIKE_AMPLIFIER
    elif tps >= Config.TICK_FREQ_ELEVATED_THRESHOLD:
        result["activity_level"] = "ELEVATED"
        # Linear interpolation between 1.0 and spike amplifier
        ratio = ((tps - Config.TICK_FREQ_ELEVATED_THRESHOLD)
                 / (Config.TICK_FREQ_SPIKE_THRESHOLD - Config.TICK_FREQ_ELEVATED_THRESHOLD))
        result["amplifier_mult"] = 1.0 + ratio * (Config.TICK_FREQ_SPIKE_AMPLIFIER - 1.0)
    else:
        result["activity_level"] = "NORMAL"
        result["amplifier_mult"] = 1.0

    return result
