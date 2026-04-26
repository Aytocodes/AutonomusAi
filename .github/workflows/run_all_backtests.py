# =============================================================================
# run_all_backtests.py -- Runs backtest on all 10 symbols and prints summary
# =============================================================================

import subprocess, sys, os

SYMBOLS = [
    ("XAUUSDm", "xauusd_m15.csv"),
    ("GBPUSDm", "gbpusd_m15.csv"),
    ("EURUSDm", "eurusd_m15.csv"),
    ("USDJPYm", "usdjpy_m15.csv"),
    ("GBPJPYm", "gbpjpy_m15.csv"),
    ("US30m",   "us30_m15.csv"),
    ("USTECm",  "ustec_m15.csv"),
    ("US500m",  "us500_m15.csv"),
    ("USOILm",  "usoil_m15.csv"),
    ("XAGUSDm", "xagusd_m15.csv"),
]

results = []

for sym, csv in SYMBOLS:
    if not os.path.exists(csv):
        print(f"[{sym}] CSV not found -- skipping")
        results.append((sym, "N/A", "N/A", "N/A", "N/A", "N/A"))
        continue

    r = subprocess.run(
        [sys.executable, "AutonomusAI.py", "--mode", "backtest", "--csv", csv],
        capture_output=True, text=True
    )
    output = r.stdout

    pnl = wr = pf = dd = monthly = "N/A"
    for line in output.split("\n"):
        l = line.strip()
        if "Net Pnl" in l:            pnl     = l.split()[-1]
        if "Win Rate" in l:           wr      = l.split()[-1] + "%"
        if "Profit Factor" in l:      pf      = l.split()[-1]
        if "Max Drawdown Pct" in l:   dd      = l.split()[-1] + "%"
        if "Est. Monthly Return" in l: monthly = l.split()[-1]
        if "No closed trades" in l:
            pnl = wr = pf = dd = monthly = "No trades"

    results.append((sym, pnl, wr, pf, dd, monthly))
    print(f"[{sym}] Done -- PnL: {pnl} | WR: {wr} | PF: {pf} | DD: {dd} | Monthly: {monthly}")

print()
print("=" * 78)
print(f"  {'SYMBOL':<12} {'NET P&L':>10} {'WIN%':>9} {'PF':>6} {'MAX DD':>9} {'MONTHLY%':>10}")
print("=" * 78)

total_pnl = 0.0
for sym, pnl, wr, pf, dd, monthly in results:
    print(f"  {sym:<12} {pnl:>10} {wr:>9} {pf:>6} {dd:>9} {monthly:>10}")
    try:
        total_pnl += float(pnl)
    except Exception:
        pass

print("=" * 78)
print(f"  {'COMBINED P&L (10k each)':<30} ${total_pnl:,.2f}")
print(f"  {'COMBINED MONTHLY EST':<30} {total_pnl / (10000 * len(SYMBOLS)) * 100:.1f}% per symbol avg")
print("=" * 78)
