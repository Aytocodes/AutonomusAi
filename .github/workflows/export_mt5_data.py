# =============================================================================
# export_mt5_data.py -- Exports XAUUSD M15 historical data from MT5 to CSV
# Run this while MetaTrader 5 is open and logged in.
# =============================================================================

import sys
import pandas as pd
from datetime import datetime

try:
    import MetaTrader5 as mt5
except ImportError:
    print("[ERROR] MetaTrader5 package not installed.")
    print("Run: pip install MetaTrader5")
    sys.exit(1)

# --- Settings ---
SYMBOLS      = ["XAUUSDm", "XAUUSD", "XAUUSD.", "XAUUSDc"]
BARS         = 5000        # Number of M15 bars to export (~52 days)
OUTPUT_FILE  = "xauusd_m15.csv"
TIMEFRAME    = mt5.TIMEFRAME_M15

# --- Connect ---
MT5_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"

print("[MT5] Initializing connection...")
if not mt5.initialize(path=MT5_PATH):
    print(f"[ERROR] MT5 failed to initialize: {mt5.last_error()}")
    print("Make sure MetaTrader 5 is open and logged into your account.")
    sys.exit(1)

account = mt5.account_info()
if account:
    print(f"[MT5] Connected -- Account: {account.login} | Broker: {account.company}")
else:
    print("[MT5] Connected (no account info available)")

# --- Resolve symbol ---
symbol = None
for sym in SYMBOLS:
    info = mt5.symbol_info(sym)
    if info is not None:
        # Make sure it's visible/enabled in Market Watch
        if not info.visible:
            mt5.symbol_select(sym, True)
        symbol = sym
        print(f"[MT5] Symbol found: {symbol}")
        break

if symbol is None:
    print(f"[ERROR] None of these symbols found on your broker: {SYMBOLS}")
    print("Open MT5 -> Market Watch -> right-click -> Show All, then try again.")
    mt5.shutdown()
    sys.exit(1)

# --- Fetch data ---
print(f"[MT5] Fetching {BARS} M15 bars for {symbol}...")
rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, BARS)

if rates is None or len(rates) == 0:
    print(f"[ERROR] No data returned: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

# --- Build DataFrame ---
df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
df = df.rename(columns={"tick_volume": "volume"})
df = df[["time", "open", "high", "low", "close", "volume"]]
df = df.sort_values("time").reset_index(drop=True)

# --- Save ---
df.to_csv(OUTPUT_FILE, index=False)

print(f"\n[DONE] Exported {len(df)} bars")
print(f"       From : {df['time'].iloc[0]}")
print(f"       To   : {df['time'].iloc[-1]}")
print(f"       File : {OUTPUT_FILE}")
print(f"\nNow run the backtest:")
print(f"  python AutonomusAI.py --mode backtest --csv {OUTPUT_FILE}")

mt5.shutdown()
