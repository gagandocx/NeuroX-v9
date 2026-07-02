"""
NeuroX v9.0 - Configuration
Simple config for pure momentum HF scalper.
"""


class Config:
    """All configuration in one place."""

    # Identification
    VERSION = "9.40"
    BUILD = "20250703"
    MAGIC_NUMBER = 20250629

    # Symbol
    SYMBOL = "XAUUSD"

    # Tick data (from EA tick price file)
    TICK_FILE = "neurox_v9_tick_price.txt"
    EMA_FILE = "neurox_v9_ema.txt"
    MIN_BARS_FOR_MOMENTUM = 8

    # Trading
    LOT_SIZE = 0.10
    COOLDOWN_SECONDS = 1
    MAX_HOLD_SECONDS = 120
    MAX_POSITIONS = 5  # Max positions before stopping signals
    SCALE_IN_THRESHOLD = 0.30  # $ tick momentum needed to scale in additional positions

    # Momentum strength gate for multi-position scaling
    # Tick momentum: price move must exceed this multiple of TICK_MOMENTUM_THRESHOLD
    # Bar momentum: price move must exceed this multiple of MOMENTUM_THRESHOLD
    STRONG_MOMENTUM_MULT = 1.5  # 1.5x base threshold = strong momentum

    # Hysteresis (minimum price move before reversing direction)
    HYSTERESIS_THRESHOLD = 0.50  # $0.50 minimum move to flip direction

    # Momentum
    MOMENTUM_LOOKBACK = 8
    MOMENTUM_THRESHOLD = 0.60  # $0.60 minimum move

    # Adaptive momentum (ATR-based lookback selection)
    HIGH_ATR_LOOKBACK = 3   # Fast reaction in volatile markets
    LOW_ATR_LOOKBACK = 7    # Smoother in calm markets
    ATR_THRESHOLD_MULT = 1.5  # ATR > 1.5x avg = high volatility

    # Trailing stop tiers: (profit_threshold, lock_amount)
    # NOTE: Retained for reference/future use. The EA handles trailing stops
    # tick-by-tick; this Python-side config is not actively consumed by main.py.
    TRAIL_TIERS = [
        (0.50, 0.00),   # After $0.50 profit: trail at breakeven
        (1.00, 0.50),   # After $1.00 profit: lock $0.50
        (2.00, 1.50),   # After $2.00 profit: lock $1.50
        (3.00, 2.50),   # After $3.00 profit: lock $2.50
    ]

    # Bridge
    SIGNAL_FILE_PREFIX = "neurox_v9_"
    INTELLIGENCE_FILE = "neurox_v9_intelligence.txt"

    # Tick momentum (instant trading before bars are ready)
    TICK_MOMENTUM_LOOKBACK = 20
    TICK_MOMENTUM_THRESHOLD = 0.30

    # ═══════════════════════════════════════════════════════════════════
    # ═══ CHANGE THIS TO ADJUST HOW FAR FROM EMA 9 ENTRIES ARE ALLOWED ═══
    # ═══════════════════════════════════════════════════════════════════
    EMA_MAX_DISTANCE = 0.80    # Only enter within $0.80 of EMA 9 (increase = more trades, decrease = tighter entries)
    # ═══════════════════════════════════════════════════════════════════

    # EMA Master Trend (price vs EMA 9) - absolute direction filter
    EMA_MASTER_PERIOD = 9             # EMA period for master trend (price vs EMA)
    EMA_MASTER_ENABLED = True         # Enable/disable EMA master trend filter

    # EMA Crossover (DEPRECATED - direction now uses price vs EMA 9 only)
    # Kept for backward compatibility with EA bridge protocol
    EMA_CROSSOVER_FAST = 9            # (deprecated) Fast EMA period
    EMA_CROSSOVER_SLOW = 15           # (deprecated) Slow EMA period
    EMA_CROSSOVER_LOT_MULT = 2.0      # (deprecated) Lot multiplier
    EMA_CROSSOVER_MAX_POSITIONS = 5   # (deprecated) Max positions when crossover confirmed
    EMA_NORMAL_MAX_POSITIONS = 2      # (deprecated) Max positions without crossover

    # Choppy market filters
    MIN_ATR_THRESHOLD = 0.20          # Minimum ATR to allow trading (low vol = sit out)
    TICK_CONSISTENCY_LOOKBACK = 40    # Number of recent ticks to analyze for consistency
    TICK_CONSISTENCY_MIN_PCT = 0.0    # Disabled - EMA handles trend filtering
    SIGNAL_PERSISTENCE_COUNT = 1     # 1 = effectively disabled (fires on first signal)

    # ADX Ranging Market Filter
    MIN_ADX_THRESHOLD = 20.0          # Below this = ranging/choppy, don't trade

    # ═══════════════════════════════════════════════════════════════════
    # Advanced Multi-Indicator Choppy/Ranging Market Filter
    # Multiple uncorrelated indicators vote - if enough agree market is
    # ranging/choppy, trading is blocked. This is the primary filter.
    # ═══════════════════════════════════════════════════════════════════
    CHOPPY_FILTER_ENABLED = True
    CHOPPINESS_INDEX_PERIOD = 14           # Lookback period for Choppiness Index
    CHOPPINESS_INDEX_THRESHOLD = 61.8      # CI above this = choppy (range: 0-100)
    BOLLINGER_BAND_WIDTH_PERIOD = 20       # BB period for squeeze detection
    BOLLINGER_SQUEEZE_THRESHOLD = 0.5      # BB width % below this = squeeze/ranging
    ATR_RATIO_PERIOD = 14                  # Period for ATR ratio computation
    ATR_RATIO_RANGING_THRESHOLD = 0.75     # current_atr/avg_atr below this = low volatility
    VARIANCE_RATIO_THRESHOLD = 0.5         # Variance ratio below this = mean-reverting/ranging
    RANGING_FILTER_AGREEMENT = 2           # Number of indicators that must agree to block

    # Regime detection (dual-mode system)
    REGIME_ATR_RATIO_THRESHOLD = 0.8       # current_atr/avg_atr < this = ranging/choppy
    REGIME_VARIANCE_RATIO_LOOKBACK = 20    # Bars for variance ratio computation
    REGIME_VARIANCE_RATIO_THRESHOLD = 0.5  # Variance ratio < this = mean-reverting

    # Mean reversion (ranging market strategy)
    MEAN_REVERSION_LOOKBACK = 10           # Bars to compute local high/low range
    MEAN_REVERSION_ENTRY_PCT = 0.20        # Enter when price is within 20% of range extreme
    MEAN_REVERSION_MIN_RANGE = 1.00        # Minimum range width ($) for mean reversion

    # Main loop
    LOOP_INTERVAL = 0.1  # seconds between tick reads (100ms, zero-latency local file)

    # Phase 1: Instant Reversal + Profit Locking
    TICK_VELOCITY_WINDOW = 2.0        # seconds - time window for velocity spike detection
    TICK_VELOCITY_THRESHOLD = 0.30    # $ - minimum price move to trigger velocity spike
    EXHAUSTION_BAR_COUNT = 3          # consecutive shrinking bars to detect exhaustion
    AGGRESSIVE_TRAIL_PROFIT = 0.50    # $ profit to activate aggressive trailing
    AGGRESSIVE_TRAIL_DISTANCE = 0.15  # $ trailing distance when aggressive
    SCALP_PROFIT_THRESHOLD = 0.30     # $ profit to trigger quick scalp exit
    SCALP_TIME_LIMIT = 10.0           # seconds - max time for scalp mode trigger
    BRAIN_SETTINGS_FILE = "neurox_v9_brain_settings.csv"

    # Phase 2: Predictive Intelligence
    WEIGHTED_TICK_VETO_ENABLED = False  # Disabled - EMA handles trend, no need for weighted tick veto
    ACCELERATION_LOOKBACK = 10
    WEIGHTED_TICK_LOOKBACK = 20
    PATTERN_LOOKBACK = 30
    ADAPTIVE_THRESHOLD_ENABLED = True
    V_REVERSAL_MIN_DROP = 0.20
    V_REVERSAL_MIN_RECOVERY_PCT = 0.70
    DOUBLE_TOP_TOLERANCE = 0.10
    REJECTION_WICK_MIN = 0.15
    REJECTION_RETRACE_PCT = 0.60

    # Position sizing (profit-based)
    BASE_LOT_SIZE = 0.10
    MAX_LOT_SIZE = 0.50
    MIN_LOT_SIZE = 0.05
    WIN_STREAK_INCREASE = 3
    LOSS_STREAK_DECREASE = 2
    LOT_INCREASE_MULT = 1.5
    LOT_DECREASE_MULT = 0.5

    # Phase 3: Self-Optimizing
    ROLLING_TRACKER_SIZE = 100
    KELLY_MAX_FRACTION = 0.25
    KELLY_MIN_FRACTION = 0.01
    TIME_PROFILE_ENABLED = True
    AUTO_TUNE_ENABLED = True
    PERFORMANCE_FILE = "neurox_v9_performance.json"

    # ================================================================
    # Phase 4: Advanced Market Microstructure
    # ================================================================

    # --- Multi-Timeframe Confluence ---
    MTF_CONFLUENCE_ENABLED = False  # DISABLED: Pure M1 strategy only, no higher timeframe impact
    MTF_M5_PERIOD = 5              # Number of M1 bars per M5 bar
    MTF_M15_PERIOD = 15            # Number of M1 bars per M15 bar
    MTF_MIN_M1_BARS = 10           # Minimum M1 bars needed for MTF analysis
    MTF_HIGH_CONVICTION_MULT = 1.5  # Position multiplier when all TFs agree
    MTF_LOW_CONVICTION_MULT = 0.5   # Position multiplier when M1 disagrees with higher TFs

    # --- Liquidity Sweep Detection ---
    SWEEP_DETECTION_WINDOW = 5.0    # seconds - total window to detect spike + reversal
    SWEEP_SPIKE_THRESHOLD = 0.30    # $ - minimum price spike to qualify as sweep
    SWEEP_REVERSAL_PCT = 0.60       # Minimum retracement of spike (60%) to confirm reversal
    SWEEP_REVERSAL_WINDOW = 3.0     # seconds - max time for reversal after peak
    SWEEP_MIN_TICKS = 5             # Minimum ticks needed in window for detection

    # --- Tick Frequency Spike Detection ---
    TICK_FREQ_MEASUREMENT_WINDOW = 1.0   # seconds - window to count ticks
    TICK_FREQ_SPIKE_THRESHOLD = 50.0     # ticks/sec - institutional activity threshold
    TICK_FREQ_ELEVATED_THRESHOLD = 25.0  # ticks/sec - elevated activity threshold
    TICK_FREQ_SPIKE_AMPLIFIER = 1.5      # Signal amplifier multiplier on spike

    # --- Cumulative Delta (Buy/Sell Pressure) ---
    DELTA_WINDOW = 30                # Rolling window size (number of ticks)
    DELTA_DIRECTION_THRESHOLD = 5.0  # Minimum net delta to declare direction
    DELTA_PRICE_MOVE_THRESHOLD = 0.10  # $ - minimum price move to determine price direction

    # --- Support/Resistance Zones ---
    SR_LOOKBACK_BARS = 60             # Bars to scan (approx 1 hour of M1 bars)
    SR_SWING_WIDTH = 2                # Bars on each side to confirm swing point
    SR_CLUSTER_TOLERANCE = 0.20       # $ - max distance to cluster levels together
    SR_MIN_TOUCHES = 3                # Minimum touches for a tradeable level
    SR_STRONG_TOUCHES = 4             # Touches for a strong level
    SR_PROXIMITY_THRESHOLD = 0.30     # $ - distance from level to generate signal
    SR_BREAKOUT_VELOCITY = 0.30       # $ - minimum velocity to confirm breakout
    SR_MIN_BARS = 10                  # Minimum bars needed for S/R computation
