# =============================================================================
# export_all_symbols.py -- Export M15 data for all SMC-compatible symbols
# =============================================================================

import pandas as pd
import sys

try:
    import MetaTrader5 as mt5
except ImportError:
    print("Run: pip install MetaTrader5")
    sys.exit(1)

MT5_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
BARS     = 5000
TF       = mt5.TIMEFRAME_M15

# Best SMC-compatible symbols on Exness:
# - High liquidity, strong trending, clear market structure
# - Avoid exotic pairs (wide spreads, low volume)
SYMBOLS = [
    "XAUUSDm",    # Gold       -- best SMC instrument
    "GBPUSDm",    # Cable      -- strong trends, clean structure
    "EURUSDm",    # Fiber      -- most liquid forex pair
    "USDJPYm",    # Yen        -- strong trending, clear OBs
    "GBPJPYm",    # Beast      -- high volatility, big moves
    "US30m",      # Dow Jones  -- excellent SMC structure
    "USTECm",     # Nasdaq     -- strong trends, clear FVGs
    "US500m",     # S&P 500    -- institutional order flow
    "USOILm",     # Crude Oil  -- strong liquidity sweeps
    "XAGUSDm",    # Silver     -- follows gold structure
]

print("\n" + "="*55)
print("  AutonomusAI -- Multi-Symbol Data Export")
print("="*55 + "\n")

if not mt5.initialize(path=MT5_PATH):
    print(f"[ERROR] MT5 failed: {mt5.last_error()}")
    sys.exit(1)

account = mt5.account_info()
if account:
    print(f"[MT5] Connected -- {account.login} | {account.company}\n")

exported = []
failed   = []

for sym in SYMBOLS:
    try:
        # Enable symbol if not visible
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"[{sym}] Not found on broker -- skipping")
            failed.append(sym)
            continue
        if not info.visible:
            mt5.symbol_select(sym, True)

        rates = mt5.copy_rates_from_pos(sym, TF, 0, BARS)
        if rates is None or len(rates) == 0:
            print(f"[{sym}] No data returned -- skipping")
            failed.append(sym)
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.rename(columns={"tick_volume": "volume"})
        df = df[["time", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("time").reset_index(drop=True)

        filename = sym.lower().replace("m", "", 1) + "_m15.csv"
        df.to_csv(filename, index=False)

        spread = info.spread
        print(f"[{sym}] OK -- {len(df)} bars | "
              f"{df['time'].iloc[0].date()} to {df['time'].iloc[-1].date()} | "
              f"Spread: {spread} pts | Saved: {filename}")
        exported.append((sym, filename))

    except Exception as e:
        print(f"[{sym}] Error: {e}")
        failed.append(sym)

mt5.shutdown()

print(f"\n[DONE] Exported: {len(exported)} symbols | Failed: {len(failed)}")
if failed:
    print(f"       Failed: {failed}")

print("\nRun backtests:")
for sym, fname in exported:
    print(f"  python AutonomusAI.py --mode backtest --csv {fname} --symbol {sym}")
