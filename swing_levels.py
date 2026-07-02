"""
NeuroX v9.0 - Swing Level Detection

Computes swing high/low from recent M1 bar data for SL placement.
A swing high is a bar whose High is higher than N bars before and after.
A swing low is a bar whose Low is lower than N bars before and after.
"""

import logging
from typing import Optional, List

from config import Config

logger = logging.getLogger("SwingLevels")


def compute_swing_sl(
    completed_bars: List[dict],
    direction: str,
    entry_price: float,
    lookback: int = None,
    swing_width: int = 2,
) -> float:
    """
    Compute the stop loss price based on the last obvious swing high/low.

    For BUY trades: SL is placed at the last swing low (below entry).
    For SELL trades: SL is placed at the last swing high (above entry).

    Args:
        completed_bars: List of dicts with keys Open, High, Low, Close.
        direction: "BUY" or "SELL".
        entry_price: The trade entry price.
        lookback: Number of recent bars to search. Defaults to Config.SWING_SL_LOOKBACK.
        swing_width: Number of bars on each side to confirm a swing point.

    Returns:
        The swing level as the SL price. If no swing found within lookback,
        uses SWING_SL_MIN_DISTANCE from entry as fallback.
    """
    if lookback is None:
        lookback = Config.SWING_SL_LOOKBACK

    min_distance = Config.SWING_SL_MIN_DISTANCE

    if not completed_bars or len(completed_bars) < (swing_width * 2 + 1):
        # Not enough bars - use fallback
        return _fallback_sl(direction, entry_price, min_distance)

    # Use only the last 'lookback' bars
    bars = completed_bars[-lookback:] if len(completed_bars) > lookback else list(completed_bars)

    if direction == "BUY":
        # Look for swing lows (SL below entry)
        swing_low = _find_last_swing_low(bars, swing_width)
        if swing_low is not None and swing_low < entry_price:
            # Ensure minimum distance
            distance = entry_price - swing_low
            if distance >= min_distance:
                return swing_low
            else:
                return entry_price - min_distance
        # Fallback
        return entry_price - min_distance

    elif direction == "SELL":
        # Look for swing highs (SL above entry)
        swing_high = _find_last_swing_high(bars, swing_width)
        if swing_high is not None and swing_high > entry_price:
            # Ensure minimum distance
            distance = swing_high - entry_price
            if distance >= min_distance:
                return swing_high
            else:
                return entry_price + min_distance
        # Fallback
        return entry_price + min_distance

    # Unknown direction
    return _fallback_sl(direction, entry_price, min_distance)


def _find_last_swing_high(bars: List[dict], width: int) -> Optional[float]:
    """
    Find the last swing high in the bar list.

    A swing high is a bar whose High is higher than 'width' bars
    on each side.

    Args:
        bars: List of OHLC dicts.
        width: Number of bars on each side to confirm.

    Returns:
        The swing high price, or None if not found.
    """
    if len(bars) < (width * 2 + 1):
        return None

    # Scan from right to left (most recent first) to find the LAST swing high
    for i in range(len(bars) - 1 - width, width - 1, -1):
        high = bars[i]["High"]
        is_swing = True

        # Check bars to the left
        for j in range(1, width + 1):
            if bars[i - j]["High"] >= high:
                is_swing = False
                break

        if not is_swing:
            continue

        # Check bars to the right
        for j in range(1, width + 1):
            if i + j >= len(bars):
                is_swing = False
                break
            if bars[i + j]["High"] >= high:
                is_swing = False
                break

        if is_swing:
            return high

    return None


def _find_last_swing_low(bars: List[dict], width: int) -> Optional[float]:
    """
    Find the last swing low in the bar list.

    A swing low is a bar whose Low is lower than 'width' bars
    on each side.

    Args:
        bars: List of OHLC dicts.
        width: Number of bars on each side to confirm.

    Returns:
        The swing low price, or None if not found.
    """
    if len(bars) < (width * 2 + 1):
        return None

    # Scan from right to left (most recent first) to find the LAST swing low
    for i in range(len(bars) - 1 - width, width - 1, -1):
        low = bars[i]["Low"]
        is_swing = True

        # Check bars to the left
        for j in range(1, width + 1):
            if bars[i - j]["Low"] <= low:
                is_swing = False
                break

        if not is_swing:
            continue

        # Check bars to the right
        for j in range(1, width + 1):
            if i + j >= len(bars):
                is_swing = False
                break
            if bars[i + j]["Low"] <= low:
                is_swing = False
                break

        if is_swing:
            return low

    return None


def _fallback_sl(direction: str, entry_price: float, min_distance: float) -> float:
    """Compute fallback SL using minimum distance from entry."""
    if direction == "BUY":
        return entry_price - min_distance
    elif direction == "SELL":
        return entry_price + min_distance
    return entry_price - min_distance
