"""
NeuroX v9.0 - Momentum Direction Detection

Extracted and simplified from v8's signal_generator._compute_momentum_direction.
Pure momentum from M1 candles - no models, no ensemble, no regime detection.
"""

import numpy as np
import pandas as pd

from config import Config


def compute_atr(prices_df: pd.DataFrame, period: int = 14) -> tuple:
    """
    Compute ATR (Average True Range) from OHLC data.

    Args:
        prices_df: DataFrame with 'High', 'Low', 'Close' columns.
        period: ATR period (default 14).

    Returns:
        Tuple of (current_atr, avg_atr). Returns (0.0, 0.0) if
        insufficient data.
    """
    if not isinstance(prices_df, pd.DataFrame):
        return (0.0, 0.0)

    required = {"High", "Low", "Close"}
    if not required.issubset(prices_df.columns):
        return (0.0, 0.0)

    if len(prices_df) < period + 1:
        return (0.0, 0.0)

    high = prices_df["High"].values
    low = prices_df["Low"].values
    close = prices_df["Close"].values

    # True Range: max(H-L, |H-prevC|, |L-prevC|)
    tr = np.zeros(len(high) - 1)
    for i in range(1, len(high)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i - 1] = max(hl, hc, lc)

    if len(tr) < period:
        return (0.0, 0.0)

    # Simple moving average of TR for the ATR
    atr_values = []
    for i in range(period - 1, len(tr)):
        atr_values.append(np.mean(tr[i - period + 1:i + 1]))

    if not atr_values:
        return (0.0, 0.0)

    current_atr = atr_values[-1]
    avg_atr = np.mean(atr_values)

    return (current_atr, avg_atr)


def compute_momentum(prices, adaptive_atr: float = None,
                     avg_atr: float = None) -> str:
    """
    Compute short-term momentum direction from M1 candles.

    Uses adaptive lookback: if ATR is high (>1.5x average), uses shorter
    lookback (3 bars) for faster reaction. If ATR is normal/low, uses
    longer lookback (7 bars) for smoother signals.

    Supports volume-weighted mode when DataFrame has a 'Volume' column.

    Args:
        prices: DataFrame with 'Close' column (and optionally 'Volume')
                or numpy array of close prices.
        adaptive_atr: Current ATR value for adaptive lookback selection.
        avg_atr: Average ATR for comparison.

    Returns:
        "BUY" if price rose over last N bars by more than threshold.
        "SELL" if price fell over last N bars by more than threshold.
        "FLAT" if movement is below threshold.
    """
    # Adaptive momentum: select lookback based on ATR
    if adaptive_atr is not None and avg_atr is not None and avg_atr > 0:
        if adaptive_atr > Config.ATR_THRESHOLD_MULT * avg_atr:
            lookback = Config.HIGH_ATR_LOOKBACK
        else:
            lookback = Config.LOW_ATR_LOOKBACK
    else:
        lookback = Config.MOMENTUM_LOOKBACK

    # Extract close prices
    if isinstance(prices, pd.DataFrame):
        if "Close" not in prices.columns:
            return "FLAT"
        close = prices["Close"].values

        # Volume-weighted momentum if Volume column is present
        if "Volume" in prices.columns and len(close) >= lookback + 2:
            volume = prices["Volume"].values
            recent_close = close[-(lookback + 1):]
            recent_volume = volume[-(lookback + 1):]

            price_changes = np.diff(recent_close)
            volumes = recent_volume[1:]

            total_volume = np.sum(volumes)
            if total_volume > 0:
                vw_momentum = np.sum(price_changes * volumes) / total_volume
                threshold = _compute_threshold(adaptive_atr, avg_atr)

                if abs(vw_momentum) < threshold:
                    return "FLAT"
                elif vw_momentum > 0:
                    return "BUY"
                else:
                    return "SELL"

    elif isinstance(prices, np.ndarray):
        close = prices
    else:
        return "FLAT"

    if len(close) < lookback + 2:
        return "FLAT"

    # Compare current close to close N bars ago
    current_close = close[-1]
    reference_close = close[-(lookback + 1)]
    diff = current_close - reference_close

    threshold = _compute_threshold(adaptive_atr, avg_atr)

    if abs(diff) < threshold:
        return "FLAT"
    elif diff > 0:
        return "BUY"
    else:
        return "SELL"


def _compute_threshold(adaptive_atr: float = None, avg_atr: float = None) -> float:
    """Compute momentum threshold, optionally scaled by ATR ratio."""
    base_threshold = Config.MOMENTUM_THRESHOLD

    if adaptive_atr is not None and avg_atr is not None and avg_atr > 0:
        atr_ratio = adaptive_atr / avg_atr
        return base_threshold * max(0.30, min(1.50, atr_ratio))

    return base_threshold


def detect_regime(prices_df: pd.DataFrame, current_atr: float, avg_atr: float) -> str:
    """
    Detect market regime: 'trending' or 'ranging'.

    Uses two criteria that must BOTH agree for 'ranging':
    (a) ATR ratio: current_atr / avg_atr < REGIME_ATR_RATIO_THRESHOLD
        suggests low relative volatility (ranging).
    (b) Variance ratio test on close prices: compares the variance of
        incremental moves to the variance of the full walk. A ratio below
        REGIME_VARIANCE_RATIO_THRESHOLD indicates mean-reverting behavior.

    Defaults to 'trending' if insufficient data or criteria disagree.

    Args:
        prices_df: DataFrame with 'Close' column.
        current_atr: Current ATR value.
        avg_atr: Average ATR value.

    Returns:
        'trending' or 'ranging'.
    """
    # Default to trending if inputs are invalid
    if avg_atr <= 0 or current_atr <= 0:
        return "trending"

    if not isinstance(prices_df, pd.DataFrame) or "Close" not in prices_df.columns:
        return "trending"

    lookback = Config.REGIME_VARIANCE_RATIO_LOOKBACK
    close = prices_df["Close"].values

    if len(close) < lookback + 1:
        return "trending"

    # Criterion (a): ATR ratio
    atr_ratio = current_atr / avg_atr
    atr_suggests_ranging = atr_ratio < Config.REGIME_ATR_RATIO_THRESHOLD

    # Criterion (b): Variance ratio
    # Use last 'lookback' close prices for the variance ratio test
    recent_close = close[-(lookback + 1):]
    increments = np.diff(recent_close)

    # Variance of incremental moves
    var_increments = np.var(increments)

    if var_increments == 0:
        return "trending"

    # Variance of the full walk: (close[-1] - close[0])^2 / n^2
    # normalized to compare with incremental variance
    n = len(increments)
    full_move = recent_close[-1] - recent_close[0]
    # Expected walk variance for random walk: n * var_increments
    # Actual walk variance: full_move^2
    # Variance ratio = actual / expected
    expected_walk_var = n * var_increments
    actual_walk_var = full_move ** 2

    if expected_walk_var == 0:
        return "trending"

    variance_ratio = actual_walk_var / expected_walk_var
    variance_suggests_ranging = variance_ratio < Config.REGIME_VARIANCE_RATIO_THRESHOLD

    # Both criteria must agree for 'ranging'
    if atr_suggests_ranging and variance_suggests_ranging:
        return "ranging"

    return "trending"


def compute_ema(close_prices, period: int = None) -> float:
    """
    Compute Exponential Moving Average from close prices.

    Uses the standard EMA formula: EMA_t = alpha * price_t + (1 - alpha) * EMA_{t-1}
    where alpha = 2 / (period + 1).

    Args:
        close_prices: numpy array or pandas Series of close prices.
        period: EMA period (default: Config.EMA_MASTER_PERIOD).

    Returns:
        Current EMA value, or 0.0 if insufficient data.
    """
    if period is None:
        period = Config.EMA_MASTER_PERIOD

    if isinstance(close_prices, pd.Series):
        close_prices = close_prices.values

    if not isinstance(close_prices, np.ndarray):
        close_prices = np.array(close_prices)

    if len(close_prices) < period:
        return 0.0

    alpha = 2.0 / (period + 1)

    # Seed EMA with SMA of first 'period' values
    ema = np.mean(close_prices[:period])

    # Compute EMA for remaining values
    for i in range(period, len(close_prices)):
        ema = alpha * close_prices[i] + (1.0 - alpha) * ema

    return ema


def compute_mean_reversion_signal(prices_df: pd.DataFrame) -> str:
    """
    Compute mean reversion signal for ranging markets.

    Determines where the current price sits within the local range
    (high/low over MEAN_REVERSION_LOOKBACK bars). If price is near
    the bottom of the range, return 'BUY' (buy the dip). If near
    the top, return 'SELL' (sell the rip). Otherwise 'FLAT'.

    Args:
        prices_df: DataFrame with 'Close' (and optionally 'High', 'Low') columns.

    Returns:
        'BUY', 'SELL', or 'FLAT'.
    """
    if not isinstance(prices_df, pd.DataFrame) or "Close" not in prices_df.columns:
        return "FLAT"

    lookback = Config.MEAN_REVERSION_LOOKBACK

    if len(prices_df) < lookback:
        return "FLAT"

    recent = prices_df.iloc[-lookback:]

    # Use High/Low if available, otherwise use Close for range
    if "High" in prices_df.columns and "Low" in prices_df.columns:
        local_high = recent["High"].max()
        local_low = recent["Low"].min()
    else:
        local_high = recent["Close"].max()
        local_low = recent["Close"].min()

    price_range = local_high - local_low

    # Range must be large enough
    if price_range < Config.MEAN_REVERSION_MIN_RANGE:
        return "FLAT"

    # Determine where current price sits in the range (0 = low, 1 = high)
    current_price = prices_df["Close"].iloc[-1]
    position_in_range = (current_price - local_low) / price_range

    # Buy near the bottom, sell near the top
    if position_in_range <= Config.MEAN_REVERSION_ENTRY_PCT:
        return "BUY"
    elif position_in_range >= (1.0 - Config.MEAN_REVERSION_ENTRY_PCT):
        return "SELL"

    return "FLAT"
