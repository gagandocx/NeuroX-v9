"""
NeuroX v9.40 - Liquidity Sweep Detection Module

Detects when price spikes fast in one direction (velocity spike) then
INSTANTLY reverses within 3-5 seconds. This is a liquidity grab pattern.
Gold does this 10-20 times per day.

Logic:
- Track recent tick prices and timestamps
- Detect fast spike: price moves > threshold in < sweep_window seconds
- Detect instant reversal: price retraces > reversal_pct within reversal_window
- Enter in the reversal direction with high confidence
"""

import time

from config import Config


def detect_liquidity_sweep(tick_prices, tick_timestamps):
    """Detect a liquidity sweep (fast spike + instant reversal).

    A liquidity sweep occurs when price spikes fast in one direction
    (stop-hunting by institutions) then immediately reverses. The
    reversal direction is the high-confidence trade signal.

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        tick_timestamps: Sequence of timestamps corresponding to each tick.

    Returns:
        Dict with:
        - 'detected': bool - True if a liquidity sweep was detected
        - 'direction': str - Reversal direction ('BUY' or 'SELL'), '' if not detected
        - 'spike_magnitude': float - Size of the initial spike
        - 'reversal_magnitude': float - Size of the reversal
        - 'confidence': float - Confidence level (0.0 to 1.0)
    """
    result = {
        "detected": False,
        "direction": "",
        "spike_magnitude": 0.0,
        "reversal_magnitude": 0.0,
        "confidence": 0.0,
    }

    prices = list(tick_prices)
    timestamps = list(tick_timestamps)

    if len(prices) < Config.SWEEP_MIN_TICKS or len(timestamps) < Config.SWEEP_MIN_TICKS:
        return result

    # Ensure prices and timestamps are same length
    min_len = min(len(prices), len(timestamps))
    prices = prices[-min_len:]
    timestamps = timestamps[-min_len:]

    now = timestamps[-1]
    current_price = prices[-1]

    # Look back within the sweep detection window
    sweep_window = Config.SWEEP_DETECTION_WINDOW

    # Find the oldest tick within the sweep window
    window_start_idx = None
    for i in range(len(timestamps) - 1, -1, -1):
        if now - timestamps[i] > sweep_window:
            window_start_idx = i + 1
            break

    if window_start_idx is None:
        window_start_idx = 0

    if window_start_idx >= len(prices) - 2:
        return result

    window_prices = prices[window_start_idx:]
    window_timestamps = timestamps[window_start_idx:]

    if len(window_prices) < 3:
        return result

    # Find the extreme point (peak or trough) in the window
    max_price = max(window_prices)
    min_price = min(window_prices)
    max_idx = window_prices.index(max_price)
    min_idx = window_prices.index(min_price)

    start_price = window_prices[0]

    # Check for upward spike followed by reversal down (bearish sweep -> BUY reversal? No.)
    # Upward spike = institutions hunted sell stops above, then dumped. Reversal is DOWN.
    # Downward spike = institutions hunted buy stops below, then bought. Reversal is UP.

    spike_up = max_price - start_price
    spike_down = start_price - min_price

    # Determine which spike is dominant
    if spike_up >= Config.SWEEP_SPIKE_THRESHOLD and max_idx < len(window_prices) - 1:
        # Upward spike detected - check for reversal back down
        # Reversal = price dropping from the peak
        reversal = max_price - current_price
        time_since_peak = now - window_timestamps[max_idx]

        if (reversal >= spike_up * Config.SWEEP_REVERSAL_PCT
                and time_since_peak <= Config.SWEEP_REVERSAL_WINDOW):
            # Liquidity sweep detected: spiked up, reversed down
            result["detected"] = True
            result["direction"] = "SELL"
            result["spike_magnitude"] = spike_up
            result["reversal_magnitude"] = reversal
            # Confidence based on how much of the spike was retraced
            retrace_ratio = min(reversal / spike_up, 1.5)
            result["confidence"] = min(retrace_ratio * 0.7, 1.0)
            return result

    if spike_down >= Config.SWEEP_SPIKE_THRESHOLD and min_idx < len(window_prices) - 1:
        # Downward spike detected - check for reversal back up
        reversal = current_price - min_price
        time_since_trough = now - window_timestamps[min_idx]

        if (reversal >= spike_down * Config.SWEEP_REVERSAL_PCT
                and time_since_trough <= Config.SWEEP_REVERSAL_WINDOW):
            # Liquidity sweep detected: spiked down, reversed up
            result["detected"] = True
            result["direction"] = "BUY"
            result["spike_magnitude"] = spike_down
            result["reversal_magnitude"] = reversal
            retrace_ratio = min(reversal / spike_down, 1.5)
            result["confidence"] = min(retrace_ratio * 0.7, 1.0)
            return result

    return result
