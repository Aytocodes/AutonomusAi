# =============================================================================
# diagnose.py -- Live Signal Diagnostics with Timeframe Cascade
# Shows exactly which condition passes/fails on M15 -> M5 -> M1
# =============================================================================

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import pytz

MT5_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
_TF_MAP  = {"M1": 1, "M5": 5, "M15": 15, "H1": 16385}
NY_TZ    = pytz.timezone("America/New_York")

def get_ohlc(symbol, tf, count=200):
    rates = mt5.copy_rates_from_pos(symbol, _TF_MAP[tf], 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df[["open","high","low","close","tick_volume"]].rename(
        columns={"tick_volume": "volume"}
    )

mt5.initialize(path=MT5_PATH)
a = mt5.account_info()
print(f"\nAccount: {a.login} | Balance: {a.currency} {a.balance:,.2f}")
now_ny = datetime.now(NY_TZ).strftime("%H:%M NY time")
print(f"Current time: {now_ny}\n")

from trend_engine       import TrendEngine
from crt_detector       import CRTDetector
from liquidity_engine   import LiquidityEngine
from order_block_engine import OrderBlockEngine
from risk_manager       import RiskManager
from symbol_scanner     import scan_symbols
from config             import MIN_RR, CRT_VOLATILITY_PCT

trend_eng = TrendEngine()
crt_det   = CRTDetector()
liq_eng   = LiquidityEngine()
ob_eng    = OrderBlockEngine()
rm        = RiskManager()

symbols = scan_symbols(a.currency)

print("=" * 70)
print("  LIVE SIGNAL DIAGNOSTICS -- Cascade: M15 -> M5 -> M1")
print("=" * 70)

for sym in symbols:
    print(f"\n--- {sym} ---")

    df_h1  = get_ohlc(sym, "H1",  200)
    df_m15 = get_ohlc(sym, "M15", 100)
    df_m5  = get_ohlc(sym, "M5",  100)
    df_m1  = get_ohlc(sym, "M1",  100)

    if df_h1.empty:
        print("  [FAIL] No H1 data")
        continue

    # 1. Trend
    bias = trend_eng.get_bias(df_h1)
    ema  = trend_eng.get_ema(df_h1)
    slope = round(ema.iloc[-1] - ema.iloc[-5], 4)
    print(f"  [{'OK' if bias != 'neutral' else 'FAIL'}] Trend: {bias} | "
          f"Price={df_h1['close'].iloc[-1]:.5g} EMA={ema.iloc[-1]:.5g} Slope={slope}")

    if bias == "neutral":
        continue

    signal_found = False

    # Cascade through timeframes
    for tf_ctx, df_ctx, tf_entry, df_entry in [
        ("M15", df_m15, "M5",  df_m5),
        ("M5",  df_m5,  "M5",  df_m5),
        ("M1",  df_m1,  "M1",  df_m1),
    ]:
        if df_ctx.empty or len(df_ctx) < 25:
            print(f"  [SKIP] {tf_ctx}: insufficient data")
            continue

        # CRT
        crt = crt_det.detect(df_ctx)
        broken = crt_det.is_zone_broken(crt, df_ctx) if crt else True
        if crt is None:
            rng = (df_ctx["high"].iloc[-20:].max() - df_ctx["low"].iloc[-20:].min())
            pct = round(rng / df_ctx["close"].iloc[-1], 6)
            print(f"  [{tf_ctx}] CRT: FAIL (range={pct} > threshold={CRT_VOLATILITY_PCT})")
            continue
        print(f"  [{tf_ctx}] CRT: OK [{crt.low:.5g}-{crt.high:.5g}] broken={broken}")
        if broken:
            continue

        # Sweep
        sweep  = liq_eng.detect_sweep(df_ctx)
        levels = liq_eng.get_swing_levels(df_ctx)
        sh     = round(levels.get("swing_high", 0), 5)
        sl_lvl = round(levels.get("swing_low",  0), 5)
        print(f"  [{tf_ctx}] Sweep: {'OK -> ' + sweep.direction if sweep else 'FAIL'} "
              f"(H={sh} L={sl_lvl})")
        if sweep is None:
            continue
        if bias == "bullish" and sweep.direction != "bullish_sweep":
            print(f"  [{tf_ctx}] Sweep direction mismatch (need bullish_sweep)")
            continue
        if bias == "bearish" and sweep.direction != "bearish_sweep":
            print(f"  [{tf_ctx}] Sweep direction mismatch (need bearish_sweep)")
            continue

        # OB
        ob         = ob_eng.get_nearest_ob(df_entry, direction=bias)
        last_price = df_entry["close"].iloc[-1]
        in_ob      = ob.price_inside(last_price) if ob else False
        print(f"  [{tf_entry}] OB ({bias}): {'OK' if in_ob else 'FAIL'} "
              + (f"[{ob.ob_low:.5g}-{ob.ob_high:.5g}] price={last_price:.5g}" if ob else "None"))
        if not in_ob:
            continue

        # RR
        sl  = rm.stop_loss(bias, ob.ob_high, ob.ob_low, symbol=sym)
        tp  = rm.take_profit(bias, last_price, crt.high, crt.low, symbol=sym)
        rr  = rm.risk_reward(last_price, sl, tp)
        print(f"  [{tf_entry}] RR: {'OK' if rr >= MIN_RR else 'FAIL'} "
              f"= {rr} (min={MIN_RR}) SL={sl} TP={tp}")

        if rr >= MIN_RR:
            print(f"\n  *** SIGNAL READY: {bias.upper()} on {sym} [{tf_ctx}/{tf_entry}] ***")
            signal_found = True
            break

    if not signal_found:
        print(f"  [--] No signal on any timeframe")

print("\n" + "=" * 70)
mt5.shutdown()
