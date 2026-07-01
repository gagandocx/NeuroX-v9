"""
NeuroX v9.40 - Spread-as-Signal Module

Approximates spread from consecutive tick differences or M1 bar high-low ranges.
Uses spread behavior as a trading signal:

- Spread widening = uncertainty, don't trade
- Spread tightening after wide = confidence returning, prepare to enter
- Spread spike + fast price move = news event, wait

Since the tick file only has bid price, spread is approximated from:
1. Tick-to-tick absolute differences (micro-spread proxy)
2. M1 bar High-Low range (intra-bar spread proxy)
"""

import numpy as np

from config import Config


def compute_spread_from_ticks(tick_prices, window=None):
    """Approximate spread from consecutive tick differences.

    Uses the median absolute tick-to-tick difference as a proxy for
    the current spread level.

    Args:
        tick_prices: Sequence of recent tick prices (deque or list).
        window: Number of recent ticks to analyze. Defaults to Config.SPREAD_TICK_WINDOW.

    Returns:
        Dict with:
        - 'spread_value': float - Estimated spread (median absolute tick difference)
        - 'spread_state': str - 'TIGHT', 'NORMAL', 'WIDE', or 'SPIKE'
        - 'can_trade': bool - True if spread conditions allow trading
        - 'spread_trend': str - 'TIGHTENING', 'WIDENING', or 'STABLE'
    """
    if window is None:
        window = Config.SPREAD_TICK_WINDOW

    prices = list(tick_prices)

    result = {
        "spread_value": 0.0,
        "spread_state": "NORMAL",
        "can_trade": True,
        "spread_trend": "STABLE",
    }

    if len(prices) < 4:
        return result

    recent = prices[-window:] if len(prices) > window else prices

    # Compute absolute tick-to-tick differences
    diffs = []
    for i in range(1, len(recent)):
        diffs.append(abs(recent[i] - recent[i - 1]))

    if not diffs:
        return result

    # Use median as the spread estimate (robust to outliers)
    spread_value = float(np.median(diffs))
    result["spread_value"] = spread_value

    # Determine spread state
    if spread_value >= Config.SPREAD_SPIKE_THRESHOLD:
        result["spread_state"] = "SPIKE"
        result["can_trade"] = False
    elif spread_value >= Config.SPREAD_WIDE_THRESHOLD:
        result["spread_state"] = "WIDE"
        result["can_trade"] = False
    elif spread_value <= Config.SPREAD_TIGHT_THRESHOLD:
        result["spread_state"] = "TIGHT"
        result["can_trade"] = True
    else:
        result["spread_state"] = "NORMAL"
        result["can_trade"] = True

    # Determine spread trend (compare first half vs second half)
    if len(diffs) >= 4:
        mid = len(diffs) // 2
        first_half_median = float(np.median(diffs[:mid]))
        second_half_median = float(np.median(diffs[mid:]))

        change_ratio = (second_half_median - first_half_median)
        if first_half_median > 0:
            change_ratio = change_ratio / first_half_median
        else:
            change_ratio = 0.0

        if change_ratio > Config.SPREAD_TREND_THRESHOLD:
            result["spread_trend"] = "WIDENING"
        elif change_ratio < -Config.SPREAD_TREND_THRESHOLD:
            result["spread_trend"] = "TIGHTENING"
        else:
            result["spread_trend"] = "STABLE"

    return result


def compute_spread_from_bars(completed_bars, window=None):
    """Approximate spread from M1 bar high-low ranges.

    Uses the average High-Low range of recent bars as a broader
    spread/volatility proxy.

    Args:
        completed_bars: Sequence of M1 bar dicts with 'High' and 'Low' keys.
        window: Number of recent bars to analyze. Defaults to Config.SPREAD_BAR_WINDOW.

    Returns:
        Dict with:
        - 'bar_spread': float - Average bar range (High - Low)
        - 'bar_spread_state': str - 'TIGHT', 'NORMAL', 'WIDE', or 'SPIKE'
        - 'can_trade': bool - True if bar spread allows trading
    """
    if window is None:
        window = Config.SPREAD_BAR_WINDOW

    bars = list(completed_bars)

    result = {
        "bar_spread": 0.0,
        "bar_spread_state": "NORMAL",
        "can_trade": True,
    }

    if len(bars) < 2:
        return result

    recent_bars = bars[-window:] if len(bars) > window else bars

    # Compute average high-low range
    ranges = []
    for bar in recent_bars:
        bar_range = bar["High"] - bar["Low"]
        ranges.append(bar_range)

    avg_range = float(np.mean(ranges))
    result["bar_spread"] = avg_range

    # Scale thresholds for bar-level (bars have larger ranges than ticks)
    bar_wide = Config.SPREAD_WIDE_THRESHOLD * Config.SPREAD_BAR_MULT
    bar_spike = Config.SPREAD_SPIKE_THRESHOLD * Config.SPREAD_BAR_MULT
    bar_tight = Config.SPREAD_TIGHT_THRESHOLD * Config.SPREAD_BAR_MULT

    if avg_range >= bar_spike:
        result["bar_spread_state"] = "SPIKE"
        result["can_trade"] = False
    elif avg_range >= bar_wide:
        result["bar_spread_state"] = "WIDE"
        result["can_trade"] = False
    elif avg_range <= bar_tight:
        result["bar_spread_state"] = "TIGHT"
        result["can_trade"] = True
    else:
        result["bar_spread_state"] = "NORMAL"
        result["can_trade"] = True

    return result
