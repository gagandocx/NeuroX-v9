"""
NeuroX v9.40 - Dynamic Support/Resistance Zones Module

Tracks where price bounced/rejected in the last 1-2 hours using M1 bars.
Builds dynamic S/R levels from bounce points.

Logic:
- Scan recent bars for swing highs (resistance) and swing lows (support)
- Cluster nearby levels into zones (within tolerance)
- Count touches: 3+ touches = strong level
- If price approaches a strong level: expect bounce (mean reversion)
- If price BREAKS through with high velocity: breakout continuation signal
"""

from config import Config


def find_swing_points(completed_bars, lookback=None):
    """Find swing highs and swing lows from M1 bar data.

    A swing high is a bar whose High is greater than the N bars before and after.
    A swing low is a bar whose Low is less than the N bars before and after.

    Args:
        completed_bars: Sequence of M1 bar dicts with 'Open', 'High', 'Low', 'Close' keys.
        lookback: Number of bars to scan. Defaults to Config.SR_LOOKBACK_BARS.

    Returns:
        Tuple of (swing_highs, swing_lows):
        - swing_highs: list of price levels where swing highs occurred
        - swing_lows: list of price levels where swing lows occurred
    """
    if lookback is None:
        lookback = Config.SR_LOOKBACK_BARS

    bars = list(completed_bars)

    if len(bars) < lookback:
        bars_to_scan = bars
    else:
        bars_to_scan = bars[-lookback:]

    swing_highs = []
    swing_lows = []
    swing_width = Config.SR_SWING_WIDTH

    for i in range(swing_width, len(bars_to_scan) - swing_width):
        current_high = bars_to_scan[i]["High"]
        current_low = bars_to_scan[i]["Low"]

        # Check if this is a swing high
        is_swing_high = True
        for j in range(1, swing_width + 1):
            if (bars_to_scan[i - j]["High"] >= current_high
                    or bars_to_scan[i + j]["High"] >= current_high):
                is_swing_high = False
                break

        if is_swing_high:
            swing_highs.append(current_high)

        # Check if this is a swing low
        is_swing_low = True
        for j in range(1, swing_width + 1):
            if (bars_to_scan[i - j]["Low"] <= current_low
                    or bars_to_scan[i + j]["Low"] <= current_low):
                is_swing_low = False
                break

        if is_swing_low:
            swing_lows.append(current_low)

    return swing_highs, swing_lows


def cluster_levels(levels, tolerance=None):
    """Cluster nearby price levels into zones.

    Groups levels that are within tolerance of each other. The zone
    price is the average of all levels in the cluster.

    Args:
        levels: List of price levels.
        tolerance: Maximum distance between levels in same cluster.
            Defaults to Config.SR_CLUSTER_TOLERANCE.

    Returns:
        List of dicts, each with:
        - 'price': float - Average price of the zone
        - 'touches': int - Number of levels that formed this zone
        - 'strength': str - 'WEAK' (1-2 touches), 'MODERATE' (3), 'STRONG' (4+)
    """
    if tolerance is None:
        tolerance = Config.SR_CLUSTER_TOLERANCE

    if not levels:
        return []

    # Sort levels for clustering
    sorted_levels = sorted(levels)
    clusters = []
    current_cluster = [sorted_levels[0]]

    for i in range(1, len(sorted_levels)):
        if sorted_levels[i] - sorted_levels[i - 1] <= tolerance:
            current_cluster.append(sorted_levels[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [sorted_levels[i]]

    clusters.append(current_cluster)

    # Convert clusters to zone dicts
    zones = []
    for cluster in clusters:
        zone_price = sum(cluster) / len(cluster)
        touches = len(cluster)

        if touches >= Config.SR_STRONG_TOUCHES:
            strength = "STRONG"
        elif touches >= Config.SR_MIN_TOUCHES:
            strength = "MODERATE"
        else:
            strength = "WEAK"

        zones.append({
            "price": zone_price,
            "touches": touches,
            "strength": strength,
        })

    return zones


def compute_support_resistance(completed_bars, current_price):
    """Compute dynamic S/R zones and generate trading signal.

    Args:
        completed_bars: Sequence of M1 bar dicts with OHLC data.
        current_price: Current tick price.

    Returns:
        Dict with:
        - 'support_zones': list - Support zones (below current price)
        - 'resistance_zones': list - Resistance zones (above current price)
        - 'nearest_support': float - Nearest support level (0.0 if none)
        - 'nearest_resistance': float - Nearest resistance level (0.0 if none)
        - 'signal_type': str - 'BOUNCE_UP', 'BOUNCE_DOWN', 'BREAKOUT_UP',
                               'BREAKOUT_DOWN', or 'NONE'
        - 'distance_to_nearest': float - Distance to the nearest S/R level
        - 'nearest_strength': str - Strength of nearest level
    """
    result = {
        "support_zones": [],
        "resistance_zones": [],
        "nearest_support": 0.0,
        "nearest_resistance": 0.0,
        "signal_type": "NONE",
        "distance_to_nearest": 0.0,
        "nearest_strength": "WEAK",
    }

    bars = list(completed_bars)

    if len(bars) < Config.SR_MIN_BARS:
        return result

    # Find swing points
    swing_highs, swing_lows = find_swing_points(bars)

    # Cluster into zones
    all_levels = swing_highs + swing_lows
    all_zones = cluster_levels(all_levels)

    if not all_zones:
        return result

    # Separate into support (below price) and resistance (above price)
    for zone in all_zones:
        if zone["price"] < current_price:
            result["support_zones"].append(zone)
        else:
            result["resistance_zones"].append(zone)

    # Find nearest support (highest support below current price)
    if result["support_zones"]:
        nearest_sup = max(result["support_zones"], key=lambda z: z["price"])
        result["nearest_support"] = nearest_sup["price"]
    else:
        nearest_sup = None

    # Find nearest resistance (lowest resistance above current price)
    if result["resistance_zones"]:
        nearest_res = min(result["resistance_zones"], key=lambda z: z["price"])
        result["nearest_resistance"] = nearest_res["price"]
    else:
        nearest_res = None

    # Determine signal based on proximity to levels
    proximity_threshold = Config.SR_PROXIMITY_THRESHOLD

    if nearest_sup and (current_price - nearest_sup["price"]) <= proximity_threshold:
        # Price is near support
        result["distance_to_nearest"] = current_price - nearest_sup["price"]
        result["nearest_strength"] = nearest_sup["strength"]

        if nearest_sup["touches"] >= Config.SR_MIN_TOUCHES:
            # Strong support - expect bounce up
            result["signal_type"] = "BOUNCE_UP"

    elif nearest_res and (nearest_res["price"] - current_price) <= proximity_threshold:
        # Price is near resistance
        result["distance_to_nearest"] = nearest_res["price"] - current_price
        result["nearest_strength"] = nearest_res["strength"]

        if nearest_res["touches"] >= Config.SR_MIN_TOUCHES:
            # Strong resistance - expect bounce down
            result["signal_type"] = "BOUNCE_DOWN"

    # Check for breakout (price has just broken through a level)
    if len(bars) >= 2:
        prev_close = bars[-2]["Close"]

        # Check if price broke above resistance
        if nearest_res and prev_close < nearest_res["price"] and current_price > nearest_res["price"]:
            velocity = current_price - prev_close
            if velocity >= Config.SR_BREAKOUT_VELOCITY:
                result["signal_type"] = "BREAKOUT_UP"
                result["distance_to_nearest"] = current_price - nearest_res["price"]
                result["nearest_strength"] = nearest_res["strength"]

        # Check if price broke below support
        if nearest_sup and prev_close > nearest_sup["price"] and current_price < nearest_sup["price"]:
            velocity = prev_close - current_price
            if velocity >= Config.SR_BREAKOUT_VELOCITY:
                result["signal_type"] = "BREAKOUT_DOWN"
                result["distance_to_nearest"] = nearest_sup["price"] - current_price
                result["nearest_strength"] = nearest_sup["strength"]

    return result
