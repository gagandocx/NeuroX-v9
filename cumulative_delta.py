"""
NeuroX v9.40 - Cumulative Delta (Buy/Sell Pressure) Module

Classifies each tick as buy (price UP) or sell (price DOWN) and tracks
cumulative delta over a rolling window.

Logic:
- Price UP from previous tick = buy tick (+1 delta)
- Price DOWN from previous tick = sell tick (-1 delta)
- Track cumulative delta over rolling window
- If price is flat but delta rising -> predict breakout UP
- If delta diverges from price direction -> early reversal warning
"""

from config import Config


def compute_cumulative_delta(tick_prices, window=None):
    """Compute cumulative delta from tick prices.

    Classifies each tick as buy or sell based on price change from
    the previous tick. Tracks cumulative delta over a rolling window.

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        window: Rolling window size. Defaults to Config.DELTA_WINDOW.

    Returns:
        Dict with:
        - 'delta_value': float - Cumulative delta value (positive = buying, negative = selling)
        - 'delta_direction': str - 'BUYING', 'SELLING', or 'NEUTRAL'
        - 'buy_count': int - Number of buy ticks in window
        - 'sell_count': int - Number of sell ticks in window
        - 'dominance_pct': float - Percentage of dominant direction (0.0 to 1.0)
    """
    if window is None:
        window = Config.DELTA_WINDOW

    prices = list(tick_prices)

    result = {
        "delta_value": 0.0,
        "delta_direction": "NEUTRAL",
        "buy_count": 0,
        "sell_count": 0,
        "dominance_pct": 0.0,
    }

    if len(prices) < 2:
        return result

    # Use only the rolling window worth of prices
    recent = prices[-window:] if len(prices) > window else prices

    buy_count = 0
    sell_count = 0
    cum_delta = 0.0

    for i in range(1, len(recent)):
        diff = recent[i] - recent[i - 1]
        if diff > 0:
            buy_count += 1
            cum_delta += 1.0
        elif diff < 0:
            sell_count += 1
            cum_delta -= 1.0
        # If diff == 0, no contribution (flat tick)

    result["delta_value"] = cum_delta
    result["buy_count"] = buy_count
    result["sell_count"] = sell_count

    total = buy_count + sell_count
    if total > 0:
        dominant = max(buy_count, sell_count)
        result["dominance_pct"] = dominant / total
    else:
        result["dominance_pct"] = 0.0

    # Determine direction
    if cum_delta > Config.DELTA_DIRECTION_THRESHOLD:
        result["delta_direction"] = "BUYING"
    elif cum_delta < -Config.DELTA_DIRECTION_THRESHOLD:
        result["delta_direction"] = "SELLING"
    else:
        result["delta_direction"] = "NEUTRAL"

    return result


def detect_delta_divergence(tick_prices, window=None):
    """Detect divergence between price direction and cumulative delta.

    Divergence occurs when:
    - Price is moving up but delta is negative (sells dominating) -> bearish divergence
    - Price is moving down but delta is positive (buys dominating) -> bullish divergence
    - Price is flat but delta has strong direction -> predict breakout

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        window: Rolling window size. Defaults to Config.DELTA_WINDOW.

    Returns:
        Dict with:
        - 'divergence_detected': bool - True if divergence found
        - 'divergence_type': str - 'BULLISH', 'BEARISH', 'BREAKOUT_UP',
                                    'BREAKOUT_DOWN', or 'NONE'
        - 'price_direction': str - 'UP', 'DOWN', or 'FLAT'
        - 'delta_direction': str - 'BUYING', 'SELLING', or 'NEUTRAL'
    """
    if window is None:
        window = Config.DELTA_WINDOW

    prices = list(tick_prices)

    result = {
        "divergence_detected": False,
        "divergence_type": "NONE",
        "price_direction": "FLAT",
        "delta_direction": "NEUTRAL",
    }

    if len(prices) < window:
        return result

    # Compute cumulative delta
    delta_info = compute_cumulative_delta(prices, window)
    result["delta_direction"] = delta_info["delta_direction"]

    # Determine price direction over the window
    recent = prices[-window:]
    price_change = recent[-1] - recent[0]
    price_threshold = Config.DELTA_PRICE_MOVE_THRESHOLD

    if price_change > price_threshold:
        result["price_direction"] = "UP"
    elif price_change < -price_threshold:
        result["price_direction"] = "DOWN"
    else:
        result["price_direction"] = "FLAT"

    # Detect divergences
    price_dir = result["price_direction"]
    delta_dir = delta_info["delta_direction"]

    if price_dir == "UP" and delta_dir == "SELLING":
        # Price going up but sellers dominating - bearish divergence
        result["divergence_detected"] = True
        result["divergence_type"] = "BEARISH"
    elif price_dir == "DOWN" and delta_dir == "BUYING":
        # Price going down but buyers dominating - bullish divergence
        result["divergence_detected"] = True
        result["divergence_type"] = "BULLISH"
    elif price_dir == "FLAT" and delta_dir == "BUYING":
        # Price flat but strong buying - predict breakout up
        result["divergence_detected"] = True
        result["divergence_type"] = "BREAKOUT_UP"
    elif price_dir == "FLAT" and delta_dir == "SELLING":
        # Price flat but strong selling - predict breakout down
        result["divergence_detected"] = True
        result["divergence_type"] = "BREAKOUT_DOWN"

    return result
