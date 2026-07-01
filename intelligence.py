"""
NeuroX v9.0 - Predictive Intelligence Module

Provides price acceleration detection, weighted tick direction analysis,
micro-pattern recognition, and adaptive threshold computation.
"""

from config import Config


def compute_acceleration(tick_prices, lookback=None):
    """Compute the 2nd derivative of price (rate of change of momentum).

    Measures whether momentum is speeding up (accelerating) or slowing down
    (decelerating). Uses finite differences over the lookback window.

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        lookback: Number of ticks to use. Defaults to Config.ACCELERATION_LOOKBACK.

    Returns:
        Tuple of (state, value):
        - state: 'ACCELERATING' if 2nd derivative > threshold,
                 'DECELERATING' if < -threshold,
                 'STABLE' otherwise.
        - value: The computed 2nd derivative value.
    """
    if lookback is None:
        lookback = Config.ACCELERATION_LOOKBACK

    prices = list(tick_prices)
    if len(prices) < lookback:
        return ("STABLE", 0.0)

    recent = prices[-lookback:]

    # Compute 1st derivatives (velocity at each point)
    velocities = []
    for i in range(1, len(recent)):
        velocities.append(recent[i] - recent[i - 1])

    if len(velocities) < 2:
        return ("STABLE", 0.0)

    # Compute 2nd derivatives (acceleration at each point)
    accelerations = []
    for i in range(1, len(velocities)):
        accelerations.append(velocities[i] - velocities[i - 1])

    if not accelerations:
        return ("STABLE", 0.0)

    # Average acceleration over the window
    avg_acceleration = sum(accelerations) / len(accelerations)

    # Threshold: use a fraction of the tick momentum threshold to detect meaningful change
    threshold = Config.TICK_MOMENTUM_THRESHOLD * 0.03  # 0.009 by default

    if avg_acceleration > threshold:
        return ("ACCELERATING", avg_acceleration)
    elif avg_acceleration < -threshold:
        return ("DECELERATING", avg_acceleration)
    else:
        return ("STABLE", avg_acceleration)


def compute_weighted_tick_direction(tick_prices, lookback=None):
    """Compute direction weighted by magnitude of each tick-to-tick move.

    Larger price moves count more than 1-cent moves, giving a truer
    picture of buying/selling pressure.

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        lookback: Number of ticks to use. Defaults to Config.WEIGHTED_TICK_LOOKBACK.

    Returns:
        Tuple of (direction, weighted_score):
        - direction: 'BUY' if net weighted direction is positive,
                     'SELL' if negative,
                     'FLAT' if near zero or insufficient data.
        - weighted_score: The net weighted score (positive = buying, negative = selling).
    """
    if lookback is None:
        lookback = Config.WEIGHTED_TICK_LOOKBACK

    prices = list(tick_prices)
    if len(prices) < lookback:
        return ("FLAT", 0.0)

    recent = prices[-lookback:]

    # Weight each move by its absolute magnitude (squared weighting for emphasis)
    weighted_sum = 0.0
    total_weight = 0.0

    for i in range(1, len(recent)):
        diff = recent[i] - recent[i - 1]
        magnitude = abs(diff)
        # Weight by magnitude: larger moves carry more influence
        weighted_sum += diff * magnitude
        total_weight += magnitude

    if total_weight == 0.0:
        return ("FLAT", 0.0)

    # Normalize by total weight to get a weighted direction score
    weighted_score = weighted_sum / total_weight

    # Threshold for determining direction
    threshold = Config.TICK_MOMENTUM_THRESHOLD * 0.3  # 0.09 by default

    if weighted_score > threshold:
        return ("BUY", weighted_score)
    elif weighted_score < -threshold:
        return ("SELL", weighted_score)
    else:
        return ("FLAT", weighted_score)


def detect_micro_patterns(tick_prices, lookback=None):
    """Detect micro-patterns from tick data: V-reversals, double-tops, rejection wicks.

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        lookback: Number of ticks to analyze. Defaults to Config.PATTERN_LOOKBACK.

    Returns:
        List of pattern dicts, each with:
        - 'pattern': One of 'v_reversal', 'double_top', 'rejection_wick'
        - 'direction': 'BUY' or 'SELL' indicating the implied trade direction
    """
    if lookback is None:
        lookback = Config.PATTERN_LOOKBACK

    prices = list(tick_prices)
    if len(prices) < lookback:
        return []

    recent = prices[-lookback:]
    patterns = []

    # --- V-Reversal Detection ---
    # Sharp drop followed by sharp recovery (bullish V-reversal)
    # or sharp rise followed by sharp drop (bearish V-reversal)
    _detect_v_reversals(recent, patterns)

    # --- Double-Top Detection ---
    # Two peaks at similar price levels (bearish signal)
    # or two troughs at similar levels (bullish double-bottom)
    _detect_double_tops(recent, patterns)

    # --- Rejection Wick Detection ---
    # Quick spike then retrace (shows rejection of a price level)
    _detect_rejection_wicks(recent, patterns)

    return patterns


def _detect_v_reversals(recent, patterns):
    """Detect V-reversal patterns in tick data.

    Bullish V-reversal: price drops >= V_REVERSAL_MIN_DROP then recovers
    >= V_REVERSAL_MIN_RECOVERY_PCT of the drop.

    Bearish V-reversal: price rises >= V_REVERSAL_MIN_DROP then drops
    >= V_REVERSAL_MIN_RECOVERY_PCT of the rise.
    """
    min_drop = Config.V_REVERSAL_MIN_DROP
    min_recovery_pct = Config.V_REVERSAL_MIN_RECOVERY_PCT

    # Split into two halves: first half for the move, second half for recovery
    mid = len(recent) // 2
    first_half = recent[:mid]
    second_half = recent[mid:]

    if not first_half or not second_half:
        return

    # Bullish V-reversal: drop in first half, recovery in second half
    first_start = first_half[0]
    first_low = min(first_half)
    drop = first_start - first_low

    if drop >= min_drop:
        # Check recovery in second half
        second_high = max(second_half)
        recovery = second_high - first_low
        if recovery >= drop * min_recovery_pct:
            patterns.append({"pattern": "v_reversal", "direction": "BUY"})

    # Bearish V-reversal (inverted V): rise in first half, drop in second half
    first_high = max(first_half)
    rise = first_high - first_start

    if rise >= min_drop:
        # Check drop in second half
        second_low = min(second_half)
        retrace = first_high - second_low
        if retrace >= rise * min_recovery_pct:
            patterns.append({"pattern": "v_reversal", "direction": "SELL"})


def _detect_double_tops(recent, patterns):
    """Detect double-top/double-bottom patterns.

    Double-top: two peaks within DOUBLE_TOP_TOLERANCE of each other (bearish).
    Double-bottom: two troughs within tolerance (bullish).
    """
    tolerance = Config.DOUBLE_TOP_TOLERANCE

    # Find local peaks and troughs
    peaks = []
    troughs = []

    for i in range(1, len(recent) - 1):
        if recent[i] > recent[i - 1] and recent[i] > recent[i + 1]:
            peaks.append((i, recent[i]))
        if recent[i] < recent[i - 1] and recent[i] < recent[i + 1]:
            troughs.append((i, recent[i]))

    # Double-top: two peaks at similar levels with some separation
    for i in range(len(peaks) - 1):
        for j in range(i + 1, len(peaks)):
            idx_diff = peaks[j][0] - peaks[i][0]
            if idx_diff >= 3:  # Minimum separation between peaks
                price_diff = abs(peaks[j][1] - peaks[i][1])
                if price_diff <= tolerance:
                    patterns.append({"pattern": "double_top", "direction": "SELL"})
                    return  # Only report one

    # Double-bottom: two troughs at similar levels
    for i in range(len(troughs) - 1):
        for j in range(i + 1, len(troughs)):
            idx_diff = troughs[j][0] - troughs[i][0]
            if idx_diff >= 3:
                price_diff = abs(troughs[j][1] - troughs[i][1])
                if price_diff <= tolerance:
                    patterns.append({"pattern": "double_top", "direction": "BUY"})
                    return  # Only report one


def _detect_rejection_wicks(recent, patterns):
    """Detect rejection wick patterns.

    Upward rejection: quick spike up then retrace down
    (price couldn't hold the high -- bearish).

    Downward rejection: quick spike down then retrace up
    (price couldn't hold the low -- bullish).
    """
    min_wick = Config.REJECTION_WICK_MIN
    retrace_pct = Config.REJECTION_RETRACE_PCT

    # Look at the last portion of data for the most recent rejection
    # Use the last third of the lookback window
    third = max(len(recent) // 3, 3)
    segment = recent[-third:]

    if len(segment) < 3:
        return

    start_price = segment[0]
    max_price = max(segment)
    min_price = min(segment)
    end_price = segment[-1]

    # Upward rejection: spiked up then came back down
    spike_up = max_price - start_price
    retrace_down = max_price - end_price

    if spike_up >= min_wick and retrace_down >= spike_up * retrace_pct:
        patterns.append({"pattern": "rejection_wick", "direction": "SELL"})
        return

    # Downward rejection: spiked down then came back up
    spike_down = start_price - min_price
    retrace_up = end_price - min_price

    if spike_down >= min_wick and retrace_up >= spike_down * retrace_pct:
        patterns.append({"pattern": "rejection_wick", "direction": "BUY"})


def compute_adaptive_thresholds(current_atr, avg_atr):
    """Scale trading thresholds based on current volatility ratio.

    High volatility = wider thresholds (avoid noise).
    Low volatility = tighter thresholds (capture smaller moves).

    Base thresholds: velocity=$0.30, scalp=$0.50, momentum=$0.60

    Args:
        current_atr: Current ATR value.
        avg_atr: Average ATR value (baseline).

    Returns:
        Dict with 'velocity_threshold', 'scalp_threshold', 'momentum_threshold'.
    """
    if avg_atr <= 0.0:
        # No baseline - return defaults
        return {
            "velocity_threshold": 0.30,
            "scalp_threshold": 0.50,
            "momentum_threshold": 0.60,
        }

    # Volatility ratio: >1.0 = higher than average, <1.0 = lower than average
    vol_ratio = current_atr / avg_atr

    # Clamp ratio to reasonable range (0.5 to 2.0)
    vol_ratio = max(0.5, min(2.0, vol_ratio))

    return {
        "velocity_threshold": 0.30 * vol_ratio,
        "scalp_threshold": 0.50 * vol_ratio,
        "momentum_threshold": 0.60 * vol_ratio,
    }
