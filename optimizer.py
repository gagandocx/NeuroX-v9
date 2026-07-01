"""
NeuroX v9.0 - Self-Optimizing Engine (Phase 3)

Rolling performance tracker, time-of-day profiling, and Kelly criterion
for adaptive parameter tuning and optimal position sizing.
"""

from collections import deque
from typing import Dict, Optional

from config import Config


def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Compute Kelly criterion fraction for optimal position sizing.

    Kelly fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

    Clamped to [0.0, KELLY_MAX_FRACTION] for safety (quarter-Kelly).

    Args:
        win_rate: Win rate as float (0.0 to 1.0).
        avg_win: Average winning trade profit (positive).
        avg_loss: Average losing trade loss (positive, absolute value).

    Returns:
        Kelly fraction clamped between 0.0 and Config.KELLY_MAX_FRACTION.
    """
    if avg_win <= 0.0:
        return 0.0

    kelly = (win_rate * avg_win - (1.0 - win_rate) * avg_loss) / avg_win

    # Clamp to safe range
    kelly = max(0.0, min(kelly, Config.KELLY_MAX_FRACTION))
    return kelly


class RollingTracker:
    """Tracks last N trades and provides performance metrics + auto-tuning.

    Maintains a rolling window of trade results and computes win rate,
    average win/loss, profit factor, and suggested parameter adjustments.
    """

    def __init__(self, max_size: int = None):
        """Initialize with configurable rolling window size.

        Args:
            max_size: Maximum number of trades to track (default: ROLLING_TRACKER_SIZE).
        """
        size = max_size if max_size is not None else Config.ROLLING_TRACKER_SIZE
        self._trades = deque(maxlen=size)

    def record_trade(self, profit: float, duration_seconds: float,
                     hour: int, direction: str):
        """Record a completed trade.

        Args:
            profit: Profit/loss amount (positive = win, negative = loss).
            duration_seconds: Duration of trade in seconds.
            hour: Hour of day (0-23) when trade was opened.
            direction: Trade direction ('BUY' or 'SELL').
        """
        self._trades.append({
            "profit": profit,
            "duration": duration_seconds,
            "hour": hour,
            "direction": direction,
        })

    def get_win_rate(self) -> float:
        """Get win rate from rolling window.

        Returns:
            Float between 0.0 and 1.0. Returns 0.0 if no trades.
        """
        if not self._trades:
            return 0.0
        wins = sum(1 for t in self._trades if t["profit"] > 0)
        return wins / len(self._trades)

    def get_avg_win(self) -> float:
        """Get average profit of winning trades.

        Returns:
            Average win amount. Returns 0.0 if no winning trades.
        """
        wins = [t["profit"] for t in self._trades if t["profit"] > 0]
        if not wins:
            return 0.0
        return sum(wins) / len(wins)

    def get_avg_loss(self) -> float:
        """Get average loss of losing trades (returned as positive value).

        Returns:
            Average loss magnitude (positive). Returns 0.0 if no losing trades.
        """
        losses = [abs(t["profit"]) for t in self._trades if t["profit"] <= 0]
        if not losses:
            return 0.0
        return sum(losses) / len(losses)

    def get_profit_factor(self) -> float:
        """Get profit factor (gross profit / gross loss).

        Returns:
            Profit factor. Returns 0.0 if no losses, float('inf') conceptually
            but capped at 999.0 for practicality.
        """
        gross_profit = sum(t["profit"] for t in self._trades if t["profit"] > 0)
        gross_loss = sum(abs(t["profit"]) for t in self._trades if t["profit"] <= 0)

        if gross_loss == 0.0:
            return 999.0 if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def get_trade_count(self) -> int:
        """Get total number of trades in the rolling window."""
        return len(self._trades)

    def suggest_parameters(self) -> Dict[str, float]:
        """Suggest parameter adjustments based on recent performance.

        Rules:
        - Win rate > 60%: tighten thresholds by 10% (more aggressive)
        - Win rate < 40%: widen thresholds by 20% (more conservative)
        - Otherwise: no change (return current values)

        Returns:
            Dict with suggested MOMENTUM_THRESHOLD, TICK_MOMENTUM_THRESHOLD,
            and COOLDOWN_SECONDS values.
        """
        win_rate = self.get_win_rate()

        momentum_thresh = Config.MOMENTUM_THRESHOLD
        tick_momentum_thresh = Config.TICK_MOMENTUM_THRESHOLD
        cooldown = Config.COOLDOWN_SECONDS

        if len(self._trades) < 10:
            # Not enough data - return defaults
            return {
                "MOMENTUM_THRESHOLD": momentum_thresh,
                "TICK_MOMENTUM_THRESHOLD": tick_momentum_thresh,
                "COOLDOWN_SECONDS": cooldown,
            }

        if win_rate > 0.60:
            # Winning - tighten thresholds 10% (lower = more trades)
            momentum_thresh *= 0.90
            tick_momentum_thresh *= 0.90
            cooldown = max(1, cooldown * 0.90)
        elif win_rate < 0.40:
            # Losing - widen thresholds 20% (higher = fewer trades)
            momentum_thresh *= 1.20
            tick_momentum_thresh *= 1.20
            cooldown = cooldown * 1.20

        return {
            "MOMENTUM_THRESHOLD": round(momentum_thresh, 4),
            "TICK_MOMENTUM_THRESHOLD": round(tick_momentum_thresh, 4),
            "COOLDOWN_SECONDS": round(cooldown, 2),
        }

    def to_dict(self) -> Dict:
        """Serialize tracker state for persistence.

        Returns:
            Dict with trades list and metadata.
        """
        return {
            "trades": list(self._trades),
            "win_rate": self.get_win_rate(),
            "avg_win": self.get_avg_win(),
            "avg_loss": self.get_avg_loss(),
            "profit_factor": self.get_profit_factor(),
            "trade_count": self.get_trade_count(),
        }


class TimeProfiler:
    """Tracks per-hour trading performance and adjusts aggression.

    Maintains 24 hourly buckets tracking profit/loss to learn which
    hours of the day are most profitable.
    """

    def __init__(self):
        """Initialize 24 hourly performance buckets."""
        # Each bucket: {"total_profit": float, "trade_count": int}
        self._buckets = [{"total_profit": 0.0, "trade_count": 0} for _ in range(24)]

    def record_trade(self, hour: int, profit: float):
        """Record a trade for a specific hour.

        Args:
            hour: Hour of day (0-23).
            profit: Profit/loss amount.
        """
        if 0 <= hour <= 23:
            self._buckets[hour]["total_profit"] += profit
            self._buckets[hour]["trade_count"] += 1

    def get_hour_score(self, hour: int) -> float:
        """Get profitability score for a specific hour.

        Returns a value between -1.0 and +1.0:
        - Positive: hour is profitable
        - Negative: hour is losing
        - Zero: no data or break-even

        Args:
            hour: Hour of day (0-23).

        Returns:
            Float between -1.0 and +1.0.
        """
        if hour < 0 or hour > 23:
            return 0.0

        bucket = self._buckets[hour]
        if bucket["trade_count"] == 0:
            return 0.0

        avg_profit = bucket["total_profit"] / bucket["trade_count"]

        # Normalize: use sigmoid-like scaling based on average profit
        # $1 average profit = score of ~0.76, $0.50 = ~0.46, -$0.50 = ~-0.46
        # Tanh provides smooth -1 to +1 mapping
        import math
        score = math.tanh(avg_profit * 2.0)
        return max(-1.0, min(1.0, score))

    def get_aggression_mult(self, hour: int) -> float:
        """Get aggression multiplier for position sizing at given hour.

        Maps hour score to multiplier:
        - Score -1.0 -> 0.5x (half size in losing hours)
        - Score  0.0 -> 1.0x (normal in neutral hours)
        - Score +1.0 -> 2.0x (double in winning hours)

        Linear interpolation between these points.

        Args:
            hour: Hour of day (0-23).

        Returns:
            Float between 0.5 and 2.0.
        """
        score = self.get_hour_score(hour)

        # Linear mapping: score in [-1, 1] -> mult in [0.5, 2.0]
        # mult = 1.0 + score * 0.75 would give [0.25, 1.75]
        # Use: mult = 1.0 + score * (range/2)
        # For [0.5, 2.0]: center=1.25, half_range=0.75
        # Actually: -1 -> 0.5, 0 -> 1.25, +1 -> 2.0 (linear)
        # Formula: mult = 1.25 + score * 0.75
        # But spec says 0 -> 1.0: so -1 -> 0.5, 0 -> 1.0, +1 -> 2.0
        # For this asymmetric mapping:
        if score >= 0:
            # 0 -> 1.0, 1 -> 2.0
            mult = 1.0 + score * 1.0
        else:
            # -1 -> 0.5, 0 -> 1.0
            mult = 1.0 + score * 0.5

        return max(0.5, min(2.0, mult))

    def to_dict(self) -> Dict:
        """Serialize profiler state.

        Returns:
            Dict with hourly bucket data.
        """
        return {
            "buckets": self._buckets,
        }
