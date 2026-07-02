"""
NeuroX v9.0 - Advanced Multi-Indicator Choppy/Ranging Market Filter

Combines multiple uncorrelated indicators to detect ranging/choppy markets.
If a configurable number of indicators agree the market is ranging, trading
is blocked. This provides robust filtering that no single indicator can achieve.

Indicators used:
  1. ADX (Average Directional Index) - trend strength
  2. Choppiness Index - market choppiness (range 0-100)
  3. Bollinger Band Width - volatility squeeze detection
  4. ATR Ratio (current vs average) - relative volatility
  5. Variance Ratio - mean-reversion detection

The function accepts pre-computed indicator values from the EA bridge
(ADX, Choppiness Index, BB values) and computes others as needed.
"""

from config import Config


def is_market_choppy(
    adx_value: float = 100.0,
    choppiness_index: float = 0.0,
    bb_upper: float = 0.0,
    bb_lower: float = 0.0,
    current_price: float = 0.0,
    current_atr: float = 0.0,
    avg_atr: float = 0.0,
    variance_ratio: float = 1.0,
) -> tuple:
    """Determine if the market is choppy/ranging using multiple indicators.

    Uses a voting system: if RANGING_FILTER_AGREEMENT or more indicators
    agree the market is ranging, returns True with the reasons.

    Args:
        adx_value: Current ADX value (0-100). Below threshold = ranging.
        choppiness_index: Choppiness Index value (0-100). Above threshold = choppy.
        bb_upper: Upper Bollinger Band value.
        bb_lower: Lower Bollinger Band value.
        current_price: Current market price (for BB width % calc).
        current_atr: Current ATR value.
        avg_atr: Average ATR value (for ratio comparison).
        variance_ratio: Pre-computed variance ratio (0-2+). Below threshold = mean-reverting.

    Returns:
        Tuple of (is_choppy: bool, reasons: str).
        reasons is a semicolon-separated list of triggered indicators.
    """
    if not Config.CHOPPY_FILTER_ENABLED:
        return (False, "")

    ranging_votes = 0
    reasons = []

    # 1. ADX check: low ADX = no trend
    if adx_value < Config.MIN_ADX_THRESHOLD:
        ranging_votes += 1
        reasons.append(f"ADX={adx_value:.1f}<{Config.MIN_ADX_THRESHOLD}")

    # 2. Choppiness Index: high CI = choppy/ranging market
    if choppiness_index > 0 and choppiness_index > Config.CHOPPINESS_INDEX_THRESHOLD:
        ranging_votes += 1
        reasons.append(f"CI={choppiness_index:.1f}>{Config.CHOPPINESS_INDEX_THRESHOLD}")

    # 3. Bollinger Band Width squeeze: narrow bands = low volatility/ranging
    if bb_upper > 0 and bb_lower > 0 and current_price > 0:
        bb_width = bb_upper - bb_lower
        bb_width_pct = (bb_width / current_price) * 100.0
        if bb_width_pct < Config.BOLLINGER_SQUEEZE_THRESHOLD:
            ranging_votes += 1
            reasons.append(f"BB_SQZ={bb_width_pct:.2f}%<{Config.BOLLINGER_SQUEEZE_THRESHOLD}%")

    # 4. ATR Ratio: current ATR much lower than average = low volatility
    if current_atr > 0 and avg_atr > 0:
        atr_ratio = current_atr / avg_atr
        if atr_ratio < Config.ATR_RATIO_RANGING_THRESHOLD:
            ranging_votes += 1
            reasons.append(f"ATR_R={atr_ratio:.2f}<{Config.ATR_RATIO_RANGING_THRESHOLD}")

    # 5. Variance Ratio: low VR = mean-reverting/ranging behavior
    if variance_ratio > 0 and variance_ratio < Config.VARIANCE_RATIO_THRESHOLD:
        ranging_votes += 1
        reasons.append(f"VR={variance_ratio:.2f}<{Config.VARIANCE_RATIO_THRESHOLD}")

    is_choppy = ranging_votes >= Config.RANGING_FILTER_AGREEMENT
    reason_str = ";".join(reasons) if reasons else ""

    return (is_choppy, reason_str)
