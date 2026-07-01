"""
NeuroX v9.40 - Multi-Timeframe Confluence Module

Aggregates M1 bars into M5 and M15 timeframes, computes momentum on each,
and determines confluence (alignment) across all timeframes.

Logic:
- Build M5 bars by aggregating 5 consecutive M1 bars
- Build M15 bars by aggregating 15 consecutive M1 bars
- Compute momentum on M1, M5, and M15
- If all 3 agree: high conviction (stack positions)
- If M1 disagrees with higher timeframes: reduce size or skip
"""

import pandas as pd

from config import Config
from momentum import compute_momentum


def aggregate_bars(m1_bars, period):
    """Aggregate M1 bars into higher timeframe bars.

    Takes a list/deque of M1 bar dicts and aggregates them into bars
    of the specified period (e.g., 5 for M5, 15 for M15).

    Args:
        m1_bars: Sequence of M1 bar dicts with 'Open', 'High', 'Low', 'Close' keys.
        period: Number of M1 bars per higher-TF bar (5 for M5, 15 for M15).

    Returns:
        pd.DataFrame with 'Open', 'High', 'Low', 'Close' columns for the
        aggregated bars. Empty DataFrame if insufficient data.
    """
    bars_list = list(m1_bars)

    if len(bars_list) < period:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close"])

    aggregated = []
    # Only use complete groups (discard partial trailing bars)
    num_complete = len(bars_list) // period

    for i in range(num_complete):
        group = bars_list[i * period:(i + 1) * period]
        agg_open = group[0]["Open"]
        agg_high = max(bar["High"] for bar in group)
        agg_low = min(bar["Low"] for bar in group)
        agg_close = group[-1]["Close"]
        aggregated.append({
            "Open": agg_open,
            "High": agg_high,
            "Low": agg_low,
            "Close": agg_close,
        })

    return pd.DataFrame(aggregated)


def compute_mtf_confluence(completed_bars):
    """Compute multi-timeframe confluence from M1 bars.

    Builds M5 and M15 bars from the provided M1 bars, computes momentum
    on each timeframe, and returns the confluence assessment.

    Args:
        completed_bars: Sequence (deque or list) of M1 bar dicts with
            'Open', 'High', 'Low', 'Close' keys.

    Returns:
        Dict with:
        - 'all_agree': bool - True if M1, M5, and M15 momentum all align
        - 'm1_direction': str - M1 momentum ('BUY', 'SELL', or 'FLAT')
        - 'm5_direction': str - M5 momentum ('BUY', 'SELL', or 'FLAT')
        - 'm15_direction': str - M15 momentum ('BUY', 'SELL', or 'FLAT')
        - 'conviction_level': str - 'HIGH', 'MEDIUM', 'LOW', or 'NONE'
        - 'position_mult': float - Position size multiplier (0.0 to 1.5)
    """
    bars_list = list(completed_bars)

    result = {
        "all_agree": False,
        "m1_direction": "FLAT",
        "m5_direction": "FLAT",
        "m15_direction": "FLAT",
        "conviction_level": "NONE",
        "position_mult": 1.0,
    }

    # Need minimum bars for M1 momentum
    if len(bars_list) < Config.MTF_MIN_M1_BARS:
        return result

    # Build M1 DataFrame for momentum computation
    m1_df = pd.DataFrame(bars_list)
    m1_direction = compute_momentum(m1_df)
    result["m1_direction"] = m1_direction

    # Build M5 bars and compute momentum
    m5_df = aggregate_bars(bars_list, Config.MTF_M5_PERIOD)
    if not m5_df.empty and len(m5_df) >= 2:
        m5_direction = compute_momentum(m5_df)
        result["m5_direction"] = m5_direction
    else:
        result["m5_direction"] = "FLAT"

    # Build M15 bars and compute momentum
    m15_df = aggregate_bars(bars_list, Config.MTF_M15_PERIOD)
    if not m15_df.empty and len(m15_df) >= 2:
        m15_direction = compute_momentum(m15_df)
        result["m15_direction"] = m15_direction
    else:
        result["m15_direction"] = "FLAT"

    # Determine confluence
    m1_dir = result["m1_direction"]
    m5_dir = result["m5_direction"]
    m15_dir = result["m15_direction"]

    # Count how many active directions agree
    active_directions = [d for d in [m1_dir, m5_dir, m15_dir] if d != "FLAT"]

    if len(active_directions) == 0:
        result["conviction_level"] = "NONE"
        result["position_mult"] = 0.5
        return result

    # Check if all active directions agree
    all_same = len(set(active_directions)) == 1

    if len(active_directions) == 3 and all_same:
        # All 3 timeframes agree - highest conviction
        result["all_agree"] = True
        result["conviction_level"] = "HIGH"
        result["position_mult"] = Config.MTF_HIGH_CONVICTION_MULT
    elif len(active_directions) >= 2 and all_same:
        # 2 agree (one is FLAT) - medium conviction
        result["conviction_level"] = "MEDIUM"
        result["position_mult"] = 1.0
    elif m1_dir != "FLAT" and m5_dir != "FLAT" and m1_dir != m5_dir:
        # M1 disagrees with M5 - low conviction, reduce size
        result["conviction_level"] = "LOW"
        result["position_mult"] = Config.MTF_LOW_CONVICTION_MULT
    elif m1_dir != "FLAT" and m15_dir != "FLAT" and m1_dir != m15_dir:
        # M1 disagrees with M15 - low conviction, reduce size
        result["conviction_level"] = "LOW"
        result["position_mult"] = Config.MTF_LOW_CONVICTION_MULT
    else:
        # Mixed signals
        result["conviction_level"] = "MEDIUM"
        result["position_mult"] = 1.0

    return result
