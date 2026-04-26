# =============================================================================
# config.py -- AutonomusAI Configuration
# Pip values verified directly from Exness MT5 broker data
# =============================================================================

# --- Timeframes ---
TF_H1  = "H1"
TF_M15 = "M15"
TF_M5  = "M5"
TF_M1  = "M1"

# --- Trend Engine ---
EMA_PERIOD = 50

# --- CRT Detector ---
CRT_LOOKBACK       = 20
CRT_VOLATILITY_PCT = 0.018

# --- Liquidity Engine ---
LIQUIDITY_LOOKBACK = 15
SWEEP_BUFFER_PCT   = 0.0002

# --- Order Block Engine ---
OB_LOOKBACK        = 30
IMPULSE_MULTIPLIER = 1.2

# --- FVG Filter ---
USE_FVG_FILTER = False

# --- Risk Management ---
RISK_PCT       = 0.03    # 3% risk per trade
MAX_RISK_PCT   = 0.50
SL_BUFFER_PIPS = 3
MIN_RR         = 1.5
MAX_REENTRIES  = 2

# --- News Bot Settings ---
NEWS_TRADING_ENABLED = True
NEWS_TIERS = {
    "TIER_1": ["NFP", "CPI", "FOMC", "ECB Rate Decision", "BoE Rate Decision", "BoJ Rate Decision"],
    "TIER_2": ["Retail Sales", "ISM Manufacturing", "ISM Services", "GDP", "Core PCE", "RBA Rate Decision"],
    "TIER_3": ["Jobless Claims", "JOLTS", "Consumer Confidence"]
}

# Thresholds for 'Actual - Forecast' to trigger Trend Strategy
NEWS_THRESHOLDS = {
    "CPI": 0.2,          # 0.2% deviation
    "NFP": 50.0,         # 50k deviation
    "GDP": 0.3,          # 0.3% deviation
    "Retail Sales": 0.5, # 0.5% deviation
    "Default": 1.0       # Generic multiplier
}

NEWS_RISK = { "TIER_1": 0.01, "TIER_2": 0.005, "TIER_3": 0.0025 }
NEWS_STALL_MINUTES = 10  # Wait time for FADE strategy
NEWS_FOMC_WAIT_MINUTES = 30 # Wait for Powell speech

# --- Execution ---
MAX_SPREAD_PIPS = 30
SLIPPAGE_PIPS   = 3
MAGIC_NUMBER    = 20250101
TRADE_COMMENT   = "AutonomusAI"

# --- Backtesting ---
BACKTEST_INITIAL_BALANCE = 10_000.0
BACKTEST_COMMISSION_PCT  = 0.0001

# =============================================================================
# SYMBOL REGISTRY
# =============================================================================

SYMBOL           = "XAUUSDm"
SYMBOL_FALLBACKS = ["XAUUSD", "XAUUSDm", "XAUUSD."]

# Symbols confirmed profitable from 1-month real backtest
# REMOVED: USTECm (33% DD), GBPJPYm (0% WR), USOILm (-49% monthly)
MULTI_SYMBOLS = [
    "XAUUSDm",   # Gold   -- consistent, +12% monthly, low DD
    "US30m",     # Dow    -- reliable, +2.5% monthly
    "XAGUSDm",   # Silver -- best performer, +449% monthly (verified)
    "EURUSDm",   # Fiber  -- most liquid forex
]

# Symbol specs: (pip_size, pip_value_per_1_lot, min_lot, digits)
# pip_value = tick_value * (pip_size / tick_size) -- verified from MT5
SYMBOL_SPECS = {
    "EURUSDm":     (0.0001, 166.17,  0.01, 5),   # tick_val=16.617, tick_size=0.00001
    "GBPUSDm":     (0.0001, 166.17,  0.01, 5),
    "USDJPYm":     (0.01,   103.3,   0.01, 3),
    "AUDUSDm":     (0.0001, 166.17,  0.01, 5),
    "USDCADm":     (0.0001, 120.7,   0.01, 5),
    "NZDUSDm":     (0.0001, 166.17,  0.01, 5),
    "USDCHFm":     (0.0001, 166.17,  0.01, 5),
    "EURJPYm":     (0.01,   103.3,   0.01, 3),
    "GBPJPYm":     (0.01,   103.3,   0.01, 3),
    "XAUUSDm":     (0.1,    16.62,   0.01, 3),   # tick_val=1.662, tick_size=0.001
    "XAGUSDm":     (0.1,    830.86,  0.01, 3),   # tick_val=83.086, tick_size=0.001, contract=5000oz
    "US30m":       (1.0,    16.62,   0.01, 1),   # tick_val=1.662, tick_size=0.1
    "US30_x10m":   (1.0,    16.62,   0.01, 1),
    "USTECm":      (0.25,   1.66,    0.01, 2),
    "US500m":      (0.25,   1.66,    0.03, 2),
    "US500_x100m": (0.25,   1.66,    0.01, 2),
    "USOILm":      (0.01,   166.17,  0.01, 3),   # kept for reference only
    "UK100m":      (1.0,    2.22,    0.01, 1),
    "DE30m":       (1.0,    1.93,    0.01, 1),
    "FR40m":       (1.0,    1.93,    0.01, 1),
}
