# =============================================================================
# run_full_backtest.py -- Full Strategy Backtest (1 Week + 1 Month)
# Tests both SMC+CRT strategy and Scalping strategy on real historical data
# across all symbols with M15/M5/M1 cascade
# =============================================================================

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import sys
from datetime import datetime, timedelta

MT5_PATH = "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
TF_MAP   = {"M1": 1, "M5": 5, "M15": 15, "H1": 16385}

SYMBOLS  = ["XAUUSDm", "EURUSDm", "US30m", "XAGUSDm"]  # USOILm removed (-49% monthly)
BALANCE  = 10_000.0
RISK_PCT = 0.03

# =============================================================================
# Data Fetcher
# =============================================================================

def fetch(symbol, tf, bars):
    rates = mt5.copy_rates_from_pos(symbol, TF_MAP[tf], 0, bars)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    return df[["open","high","low","close","tick_volume"]].rename(
        columns={"tick_volume": "volume"}
    )

def resample(df, rule):
    if df.empty:
        return df
    return df.resample(rule).agg({
        "open": "first", "high": "max",
        "low": "min", "close": "last", "volume": "sum"
    }).dropna()

# =============================================================================
# Simple Walk-Forward Backtest Engine
# =============================================================================

def run_symbol_backtest(symbol, df_h1, df_m15, df_m5, df_m1, period_label):
    from strategy_engine   import StrategyEngine
    from scalping_strategy import ScalpingStrategy
    from risk_manager      import RiskManager
    import pytz

    NY_TZ  = pytz.timezone("America/New_York")
    engine = StrategyEngine(balance=BALANCE, risk_pct=RISK_PCT, symbol=symbol)
    scalper = ScalpingStrategy(risk_pct=RISK_PCT, symbol=symbol)
    rm     = RiskManager(risk_pct=RISK_PCT)

    trades     = []
    balance    = BALANCE
    equity     = [BALANCE]
    open_trade = None
    bars       = df_m5.index

    for i in range(100, len(bars)):
        current_time = bars[i]
        bar          = df_m5.iloc[i]

        # --- Manage open trade ---
        if open_trade:
            d = open_trade["direction"]
            if d == "bullish":
                if bar["low"] <= open_trade["sl"]:
                    pnl = _calc_pnl(open_trade, open_trade["sl"])
                    open_trade.update({"exit": open_trade["sl"], "pnl": pnl, "result": "LOSS"})
                    trades.append(open_trade); balance += pnl; open_trade = None
                elif bar["high"] >= open_trade["tp"]:
                    pnl = _calc_pnl(open_trade, open_trade["tp"])
                    open_trade.update({"exit": open_trade["tp"], "pnl": pnl, "result": "WIN"})
                    trades.append(open_trade); balance += pnl; open_trade = None
            else:
                if bar["high"] >= open_trade["sl"]:
                    pnl = _calc_pnl(open_trade, open_trade["sl"])
                    open_trade.update({"exit": open_trade["sl"], "pnl": pnl, "result": "LOSS"})
                    trades.append(open_trade); balance += pnl; open_trade = None
                elif bar["low"] <= open_trade["tp"]:
                    pnl = _calc_pnl(open_trade, open_trade["tp"])
                    open_trade.update({"exit": open_trade["tp"], "pnl": pnl, "result": "WIN"})
                    trades.append(open_trade); balance += pnl; open_trade = None

            equity.append(balance)
            continue

        # --- Slice data up to current bar (no lookahead) ---
        m5_slice  = df_m5.iloc[:i+1]
        m15_slice = df_m15[df_m15.index <= current_time]
        h1_slice  = df_h1[df_h1.index  <= current_time]
        m1_slice  = df_m1[df_m1.index  <= current_time] if not df_m1.empty else pd.DataFrame()

        if len(h1_slice) < 60 or len(m15_slice) < 25:
            equity.append(balance)
            continue

        engine.balance  = balance
        signal          = None
        strategy_tag    = ""

        # --- Strategy 1: SMC + CRT with M15->M5->M1 cascade ---
        smc = engine.evaluate(h1_slice, m15_slice, m5_slice,
                              m1_slice if len(m1_slice) >= 30 else None)
        if smc and smc.rr >= 1.5:
            signal       = smc
            strategy_tag = f"SMC-{getattr(smc, 'timeframe', 'M15')}"

        # --- Strategy 2: Scalping (8:30-11:00 NY) ---
        # Check if current bar falls in NY session window using historical timestamps
        if signal is None and len(m15_slice) >= 25:
            try:
                bar_ny = current_time.tz_localize("UTC").tz_convert(NY_TZ) \
                         if current_time.tzinfo is None \
                         else current_time.tz_convert(NY_TZ)
                bar_hour   = bar_ny.hour
                bar_minute = bar_ny.minute
                in_session = (bar_hour == 8 and bar_minute >= 30) or \
                             (9 <= bar_hour <= 10) or \
                             (bar_hour == 11 and bar_minute == 0)
                if in_session:
                    # Localize slices for scalper timezone detection
                    def localize(df):
                        if df.empty: return df
                        d = df.copy()
                        if d.index.tzinfo is None:
                            d.index = d.index.tz_localize("UTC")
                        return d
                    scalp = scalper.evaluate(
                        localize(m15_slice), localize(m5_slice),
                        localize(m1_slice) if len(m1_slice) >= 30 else None,
                        balance=balance,
                        current_time=current_time   # pass historical bar time
                    )
                    if scalp and scalp.rr >= 2.0:
                        signal       = scalp
                        strategy_tag = "SCALP"
            except Exception:
                pass

        if signal:
            lot = getattr(signal, 'lot', None) or \
                  rm.lot_size(balance, signal.entry, signal.sl, symbol=symbol)
            open_trade = {
                "symbol":    symbol,
                "direction": signal.direction,
                "entry":     signal.entry,
                "sl":        signal.sl,
                "tp":        signal.tp,
                "lot":       lot,
                "rr":        signal.rr,
                "time":      current_time,
                "strategy":  strategy_tag,
            }

        equity.append(balance)

    # Close any open trade at last price
    if open_trade:
        last = df_m5["close"].iloc[-1]
        pnl  = _calc_pnl(open_trade, last)
        open_trade.update({"exit": last, "pnl": pnl, "result": "OPEN"})
        trades.append(open_trade)

    return trades, equity

def _calc_pnl(trade, exit_price):
    from config import SYMBOL_SPECS
    sym   = trade.get("symbol", "XAUUSDm")
    specs = SYMBOL_SPECS.get(sym, (0.1, 16.5, 0.01, 3))
    pip_size    = specs[0]
    pip_val_lot = specs[1]   # USD per pip per 1.0 lot
    pips = (exit_price - trade["entry"]) / pip_size
    if trade["direction"] == "bearish":
        pips = -pips
    return round(pips * pip_val_lot * trade["lot"], 2)

def _metrics(trades, equity, balance, period):
    closed = [t for t in trades if t["result"] in ("WIN","LOSS")]
    if not closed:
        return None
    wins   = [t for t in closed if t["result"] == "WIN"]
    losses = [t for t in closed if t["result"] == "LOSS"]
    pnls   = [t["pnl"] for t in closed]
    eq     = np.array(equity)
    peak   = np.maximum.accumulate(eq)
    dd     = ((peak - eq) / peak).max() * 100
    gp     = sum(t["pnl"] for t in wins)
    gl     = abs(sum(t["pnl"] for t in losses))
    pf     = round(gp / gl, 2) if gl > 0 else float("inf")
    return {
        "period":       period,
        "trades":       len(closed),
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(len(wins)/len(closed)*100, 1),
        "net_pnl":      round(sum(pnls), 2),
        "profit_factor":pf,
        "max_dd_pct":   round(dd, 2),
        "final_balance":round(balance, 2),
        "return_pct":   round((balance - BALANCE) / BALANCE * 100, 2),
    }

# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*65)
    print("  AutonomusAI -- FULL HISTORICAL BACKTEST")
    print("  Testing: SMC+CRT + Scalping | Cascade: M15->M5->M1")
    print("="*65)

    if not mt5.initialize(path=MT5_PATH):
        print("MT5 failed:", mt5.last_error())
        sys.exit(1)

    a = mt5.account_info()
    print(f"  Account: {a.login} | {a.company}\n")

    all_results = []

    for sym in SYMBOLS:
        print(f"Fetching data for {sym}...")

        # Fetch enough bars for 1 month
        df_h1  = fetch(sym, "H1",  750)   # ~1 month H1
        df_m15 = fetch(sym, "M15", 3000)  # ~1 month M15
        df_m5  = fetch(sym, "M5",  9000)  # ~1 month M5
        df_m1  = fetch(sym, "M1",  43200) # ~1 month M1

        if df_m5.empty or len(df_m5) < 200:
            print(f"  [{sym}] Insufficient data -- skipping")
            continue

        total_days = (df_m5.index[-1] - df_m5.index[0]).days
        print(f"  [{sym}] H1:{len(df_h1)} M15:{len(df_m15)} M5:{len(df_m5)} "
              f"M1:{len(df_m1)} bars | {total_days} days")

        # --- 1 WEEK backtest (last 7 days) ---
        cutoff_week  = df_m5.index[-1] - pd.Timedelta(days=7)
        df_m5_week   = df_m5[df_m5.index >= cutoff_week]
        df_m15_week  = df_m15[df_m15.index >= cutoff_week]
        df_h1_week   = df_h1[df_h1.index >= cutoff_week - pd.Timedelta(days=7)]
        df_m1_week   = df_m1[df_m1.index >= cutoff_week]

        if len(df_m5_week) >= 100:
            trades_w, equity_w = run_symbol_backtest(
                sym, df_h1_week, df_m15_week, df_m5_week, df_m1_week, "1 Week"
            )
            m_week = _metrics(trades_w, equity_w,
                              BALANCE + sum(t.get("pnl",0) for t in trades_w if "pnl" in t),
                              "1 Week")
            if m_week:
                m_week["symbol"] = sym
                all_results.append(m_week)
                print(f"  [1W] Trades:{m_week['trades']} WR:{m_week['win_rate']}% "
                      f"PnL:${m_week['net_pnl']} PF:{m_week['profit_factor']} "
                      f"DD:{m_week['max_dd_pct']}% Return:{m_week['return_pct']}%")

        # --- 1 MONTH backtest (all data) ---
        trades_m, equity_m = run_symbol_backtest(
            sym, df_h1, df_m15, df_m5, df_m1, "1 Month"
        )
        m_month = _metrics(trades_m, equity_m,
                           BALANCE + sum(t.get("pnl",0) for t in trades_m if "pnl" in t),
                           "1 Month")
        if m_month:
            m_month["symbol"] = sym
            all_results.append(m_month)
            print(f"  [1M] Trades:{m_month['trades']} WR:{m_month['win_rate']}% "
                  f"PnL:${m_month['net_pnl']} PF:{m_month['profit_factor']} "
                  f"DD:{m_month['max_dd_pct']}% Return:{m_month['return_pct']}%")

        print()

    mt5.shutdown()

    # ==========================================================================
    # FINAL SUMMARY TABLE
    # ==========================================================================
    if not all_results:
        print("No results generated.")
        sys.exit(0)

    df_res = pd.DataFrame(all_results)

    print("\n" + "="*85)
    print("  FULL BACKTEST RESULTS SUMMARY")
    print("="*85)
    print(f"  {'SYMBOL':<14} {'PERIOD':<10} {'TRADES':>7} {'WIN%':>7} {'NET PNL':>10} "
          f"{'PF':>6} {'MAX DD%':>8} {'RETURN%':>9}")
    print("-"*85)

    for _, row in df_res.iterrows():
        print(f"  {row['symbol']:<14} {row['period']:<10} {row['trades']:>7} "
              f"{row['win_rate']:>6}% {row['net_pnl']:>10} "
              f"{row['profit_factor']:>6} {row['max_dd_pct']:>7}% {row['return_pct']:>8}%")

    print("="*85)

    # Combined stats
    week_res  = df_res[df_res["period"] == "1 Week"]
    month_res = df_res[df_res["period"] == "1 Month"]

    if not week_res.empty:
        print(f"\n  1 WEEK  COMBINED | Total trades: {week_res['trades'].sum()} | "
              f"Avg WR: {week_res['win_rate'].mean():.1f}% | "
              f"Total PnL: ${week_res['net_pnl'].sum():.2f} | "
              f"Avg Return: {week_res['return_pct'].mean():.2f}%")

    if not month_res.empty:
        print(f"  1 MONTH COMBINED | Total trades: {month_res['trades'].sum()} | "
              f"Avg WR: {month_res['win_rate'].mean():.1f}% | "
              f"Total PnL: ${month_res['net_pnl'].sum():.2f} | "
              f"Avg Return: {month_res['return_pct'].mean():.2f}%")

    print("="*85)

    # Save results
    df_res.to_csv("full_backtest_results.csv", index=False)
    print("\n  Results saved -> full_backtest_results.csv")
