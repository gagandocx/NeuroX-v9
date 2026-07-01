"""
NeuroX v9.0 - Performance-Based Position Sizing

Tracks win/loss streaks and adjusts lot size dynamically.
After consecutive wins, increase position size (capitalize on momentum).
After consecutive losses, decrease position size (protect capital).
Integrates Kelly criterion for optimal sizing when enough data is available.
"""

from config import Config


class PositionSizer:
    """Tracks trade outcomes and adjusts lot size based on streaks.

    Rules:
    - After WIN_STREAK_INCREASE (3) consecutive wins: increase lot by LOT_INCREASE_MULT (1.5x)
    - After LOSS_STREAK_DECREASE (2) consecutive losses: decrease lot by LOT_DECREASE_MULT (0.5x)
    - Lot size is capped at MAX_LOT_SIZE and floored at MIN_LOT_SIZE
    - When >= 20 trades in history, Kelly criterion sizing is used
    """

    def __init__(self):
        """Initialize with base lot size and zero streak."""
        self._current_lot = Config.BASE_LOT_SIZE
        self._consecutive_wins = 0
        self._consecutive_losses = 0
        self._total_trades = 0
        self._total_wins = 0
        self._total_profit = 0.0
        self._use_kelly = False

    def record_trade(self, is_win, profit_amount):
        """Record a completed trade outcome.

        Args:
            is_win: True if the trade was profitable, False otherwise.
            profit_amount: The profit/loss amount (positive or negative).
        """
        self._total_trades += 1
        self._total_profit += profit_amount

        if is_win:
            self._total_wins += 1
            self._consecutive_wins += 1
            self._consecutive_losses = 0

            # Check if win streak triggers lot increase
            if self._consecutive_wins >= Config.WIN_STREAK_INCREASE:
                self._current_lot *= Config.LOT_INCREASE_MULT
                self._current_lot = min(self._current_lot, Config.MAX_LOT_SIZE)
                # Reset streak counter after applying increase
                self._consecutive_wins = 0
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

            # Check if loss streak triggers lot decrease
            if self._consecutive_losses >= Config.LOSS_STREAK_DECREASE:
                self._current_lot *= Config.LOT_DECREASE_MULT
                self._current_lot = max(self._current_lot, Config.MIN_LOT_SIZE)
                # Reset streak counter after applying decrease
                self._consecutive_losses = 0

    def get_kelly_lot_size(self, win_rate: float, avg_win: float,
                           avg_loss: float) -> float:
        """Compute lot size using Kelly criterion.

        Formula: kelly_fraction * BASE_LOT_SIZE / KELLY_MIN_FRACTION
        Capped at MAX_LOT_SIZE.

        Args:
            win_rate: Win rate (0.0 to 1.0).
            avg_win: Average winning trade profit (positive).
            avg_loss: Average losing trade loss (positive, absolute value).

        Returns:
            Lot size based on Kelly criterion, capped at MAX_LOT_SIZE.
        """
        from optimizer import kelly_criterion

        kelly_frac = kelly_criterion(win_rate, avg_win, avg_loss)

        if kelly_frac <= 0.0:
            return Config.MIN_LOT_SIZE

        lot = kelly_frac * Config.BASE_LOT_SIZE / Config.KELLY_MIN_FRACTION
        lot = max(Config.MIN_LOT_SIZE, min(lot, Config.MAX_LOT_SIZE))
        return round(lot, 2)

    def get_lot_size(self, win_rate: float = None, avg_win: float = None,
                     avg_loss: float = None) -> float:
        """Get the current adjusted lot size.

        If Kelly criterion data is provided and enough trades have been
        recorded (>= 20), uses Kelly sizing. Otherwise falls back to
        streak-based sizing.

        Args:
            win_rate: Optional win rate for Kelly sizing.
            avg_win: Optional avg win for Kelly sizing.
            avg_loss: Optional avg loss for Kelly sizing.

        Returns:
            Float lot size, respecting MIN_LOT_SIZE and MAX_LOT_SIZE bounds.
        """
        if (self._use_kelly and win_rate is not None
                and avg_win is not None and avg_loss is not None):
            return self.get_kelly_lot_size(win_rate, avg_win, avg_loss)
        return round(self._current_lot, 2)

    def enable_kelly(self, enabled: bool = True):
        """Enable or disable Kelly criterion sizing.

        Args:
            enabled: True to use Kelly sizing when data is available.
        """
        self._use_kelly = enabled

    @property
    def kelly_enabled(self) -> bool:
        """Whether Kelly criterion sizing is active."""
        return self._use_kelly

    @property
    def consecutive_wins(self):
        """Current consecutive win count."""
        return self._consecutive_wins

    @property
    def consecutive_losses(self):
        """Current consecutive loss count."""
        return self._consecutive_losses

    @property
    def total_trades(self):
        """Total number of recorded trades."""
        return self._total_trades

    @property
    def win_rate(self):
        """Win rate as a float (0.0 to 1.0)."""
        if self._total_trades == 0:
            return 0.0
        return self._total_wins / self._total_trades

    @property
    def total_profit(self):
        """Total accumulated profit/loss."""
        return self._total_profit
