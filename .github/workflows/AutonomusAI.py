# =============================================================================
# AutonomusAI.py -- Production Bot with Auto Symbol Scanning
# Automatically discovers and trades ALL compatible symbols from Market Watch.
# No manual symbol list needed.
# =============================================================================

import argparse
import os
import sys
import time
import signal
import pandas as pd
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

from logger            import log
from config            import SYMBOL, RISK_PCT, BACKTEST_INITIAL_BALANCE, TF_H1, TF_M15, TF_M5, TF_M1, MAX_SPREAD_PIPS

# Safety assignments to ensure these are always available in the local scope
_TF_H1, _TF_M15, _TF_M5, _TF_M1 = TF_H1, TF_M15, TF_M5, TF_M1

from market_data       import MarketDataHandler
from strategy_engine   import StrategyEngine
from execution_engine  import ExecutionEngine
from backtester        import Backtester
from symbol_scanner    import scan_symbols, get_pip_info
from news_bot          import A2_NewsBot, NewsFetcher
from scalping_strategy import ScalpingStrategy, SCALP_SYMBOLS

# Define multiple MT5 accounts here or load from a separate config file
# For demonstration, hardcoding a list of accounts.
# In a real application, consider loading this from a secure JSON/YAML file
# or a database.
MT5_ACCOUNTS = [
    {
        "name": "Account 1 (Real)",
        "login": os.getenv("MT5_LOGIN_1"),
        "password": os.getenv("MT5_PASSWORD_1"),
        "server": os.getenv("MT5_SERVER_1"),
        "path": os.getenv("MT5_PATH_1", "C:\\Program Files\\MetaTrader 5\\terminal64.exe")
    },
    {
        "name": "Account 2 (Demo)",
        "login": os.getenv("MT5_LOGIN_2"),
        "password": os.getenv("MT5_PASSWORD_2"),
        "server": os.getenv("MT5_SERVER_2"),
        "path": os.getenv("MT5_PATH_2", "C:\\Program Files\\MetaTrader 5\\terminal64.exe")
    }
    # Add more accounts as needed
]
_shutdown = False


# =============================================================================
# Signal Handlers
# =============================================================================

def _handle_signal(signum, frame):
    global _shutdown
    log.info(f"Shutdown signal received -- stopping bot gracefully...")
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT,  _handle_signal)


# =============================================================================
# Telegram Alerts
# =============================================================================

def send_telegram(message: str):
    token   = os.getenv("TELEGRAM_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        import urllib.request, urllib.parse
        url  = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
        urllib.request.urlopen(url, data, timeout=5)
    except Exception as e:
        log.warning(f"Telegram alert failed: {e}")


# =============================================================================
# MT5 Connection
# =============================================================================

def connect_mt5(login: str, password: str, server: str, path: str, max_retries: int = 10) -> bool:
    try:
        import MetaTrader5 as mt5
    except ImportError:
        log.error("MetaTrader5 not installed. Run: pip install MetaTrader5")
        return False

    if not all([login, password, server, path]):
        log.error("Incomplete MT5 credentials provided for connection.")
        return False

    try:
        login_int = int(login)
    except ValueError:
        log.error(f"MT5_LOGIN must be a numeric account number, but found: '{login}'")
        return False

    for attempt in range(1, max_retries + 1):
        try:
            # Ensure any previous connection is shut down before initializing a new one
            if mt5.is_connected():
                mt5.shutdown()
                time.sleep(1) # Give it a moment to shut down

            if mt5.initialize(path=path, login=login_int, password=password, server=server):
                info = mt5.account_info()
                if info:
                    log.info(f"MT5 connected -- Account: {info.login} | "
                             f"Balance: {info.currency} {info.balance:,.2f} | "
                             f"Leverage: 1:{info.leverage}")
                    return True

            last_error = mt5.last_error()
            log.warning(f"MT5 init attempt {attempt}/{max_retries} for account {login}: {last_error}")
            # If we get authorization failed, stop immediately to prevent lockout
            if last_error and last_error[0] == -6:
                log.error(f"CRITICAL: Authorization failed for account {login}. Check credentials.")
                return False
        except Exception as e:
            log.warning(f"MT5 connect error (attempt {attempt}) for account {login}: {e}")

        delay = min(10 * attempt, 300) # Slower retry backoff
        log.info(f"Retrying in {delay:.0f}s...")
        time.sleep(delay)

    log.error(f"MT5 connection failed for account {login} after all retries.")
    return False


def is_mt5_connected() -> bool:
    try:
        import MetaTrader5 as mt5
        return mt5.terminal_info() is not None
    except Exception:
        return False


# =============================================================================
# Trading Session Filter
# =============================================================================

def is_trading_session() -> bool:
    now  = datetime.now(timezone.utc)
    wday = now.weekday()
    hour = now.hour
    if wday == 6 and hour < 22:   # Sunday before open
        return False
    if wday == 4 and hour >= 22:  # Friday after close
        return False
    if wday == 5:                  # Saturday
        return False
    return True


# =============================================================================
# LIVE TRADING -- Fully Automatic Symbol Scanning
# =============================================================================

def run_live(risk_pct: float = RISK_PCT):
    log.info("=" * 60)
    log.info("  AutonomusAI -- LIVE MODE (Auto Symbol Scan)")
    log.info("=" * 60)

    send_telegram("AutonomusAI started -- scanning symbols automatically.")

    if not connect_mt5():
        log.error("Could not connect to MT5. Exiting.")
        sys.exit(1)

    import MetaTrader5 as mt5

    account = mt5.account_info()
    balance  = account.balance if account else BACKTEST_INITIAL_BALANCE
    currency = account.currency if account else "USD"

    # ---------------------------------------------------------------
    # AUTO SCAN -- discover all compatible symbols from Market Watch
    # ---------------------------------------------------------------
    log.info("Running automatic symbol scan...")
    symbols = scan_symbols(account_currency=currency)

    if not symbols:
        log.error("No compatible symbols found in Market Watch. "
                  "Add symbols to Market Watch in MT5 and restart.")
        sys.exit(1)

    log.info(f"Trading {len(symbols)} symbols: {', '.join(symbols)}")
    send_telegram(f"AutonomusAI scanning {len(symbols)} symbols: {', '.join(symbols)}")

    # Add scalp-only symbols not already in SMC list
    scalp_only = [s for s in SCALP_SYMBOLS if s not in symbols]
    all_symbols = symbols + scalp_only
    log.info(f"Scalping also covers: {', '.join(scalp_only)}")
    send_telegram(f"Scalping bot adds: {', '.join(scalp_only)}")

    # Initialise per-symbol objects
    handlers   = {}
    strategies = {}   # SMC only -- for symbols in main scan
    executions = {}
    scalp_handlers = {}  # extra handlers for scalp-only symbols

    for sym in all_symbols:
        try:
            handlers[sym]  = MarketDataHandler(symbol=sym, live=True)
            executions[sym] = ExecutionEngine(symbol=sym, live=True)
            if sym in symbols:  # SMC strategy only for scanned symbols
                strategies[sym] = StrategyEngine(balance=balance, risk_pct=risk_pct, symbol=sym)
            log.info(f"  [{sym}] Ready {'(SMC+Scalp)' if sym in symbols else '(Scalp only)'}")
        except Exception as e:
            log.warning(f"  [{sym}] Skipped -- {e}")

    if not handlers:
        log.error("No symbols could be initialised. Exiting.")
        sys.exit(1)

    consecutive_errors = 0
    scan_interval      = 3600   # Re-scan Market Watch every 1 hour
    last_scan_time     = time.time()

    try:
        while not _shutdown:

            # --- Session filter ---
            if not is_trading_session():
                log.info("Outside trading session -- sleeping 15 min...")
                time.sleep(900)
                continue

            # --- Connection watchdog ---
            if not is_mt5_connected():
                log.warning("MT5 disconnected -- reconnecting...")
                send_telegram("AutonomusAI: MT5 disconnected. Reconnecting...")
                if not connect_mt5():
                    time.sleep(60)
                    continue
                send_telegram("AutonomusAI: MT5 reconnected.")

            # --- Refresh balance ---
            # --- Refresh Web Settings & Balance ---
            try:
                web_settings = NewsFetcher.get_web_settings()
                info = mt5.account_info()
                if info:
                    balance = info.balance
                    for sym in strategies:
                        strategies[sym].balance = balance
                        # Update SMC risk dynamicaPORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        PORT=8000
                        EMAIL_USER=your-email@gmail.com
                        EMAIL_PASS=your-app-password
                        lly from web
                        strategies[sym].risk_manager.risk_pct = web_settings.get("smc_risk", risk_pct)
            except Exception as e:
                log.warning(f"Balance refresh failed: {e}")
                log.warning(f"Settings/Balance refresh failed: {e}")
                web_settings = {"smc_risk": risk_pct, "scalp_risk": risk_pct, "news_risk": None}

            # --- Periodic re-scan (picks up new symbols added to Market Watch) ---
            if time.time() - last_scan_time > scan_interval:
                log.info("Re-scanning Market Watch for new symbols...")
                new_symbols = scan_symbols(account_currency=currency)
                for sym in new_symbols:
                    if sym not in handlers:
                        try:
                            handlers[sym]   = MarketDataHandler(symbol=sym, live=True)
                            strategies[sym] = StrategyEngine(balance=balance,
                                                             risk_pct=risk_pct, symbol=sym)
                            executions[sym] = ExecutionEngine(symbol=sym, live=True)
                            log.info(f"  [{sym}] New symbol added to scanner")
                        except Exception as e:
                            log.warning(f"  [{sym}] Could not add: {e}")
                last_scan_time = time.time()

            # --- Evaluate each symbol ---
            for sym in list(handlers.keys()):
                if _shutdown:
                    break

                try:
                    # --- A2_NewsBot Evaluation (Priority) ---
                    # We check for active news events globally
                    active_event = NewsFetcher.get_active_event()
                    if active_event:
                        # Prioritize Gold for News Tier 1
                        news_sym = "XAUUSDm" if sym == "XAUUSDm" else sym
                        news_bot = A2_NewsBot(symbol=news_sym, balance=balance)
                        news_bot = A2_NewsBot(symbol=news_sym, balance=balance, risk_config=web_settings.get("news_risk"))
                        news_sig = news_bot.evaluate_news_setup(active_event, handlers[news_sym].get_ohlc(_TF_M1, count=50))
                        
                        if news_sig and not executions[news_sym].has_open_trade():
                            res = executions[news_sym].place_order(
                                direction=news_sig['direction'],
                                lot=news_sig['lot'],
                                sl=news_sig['sl'],
                                tp=news_sig['tp']
                            )
                            if res["success"]:
                                msg = f"🚨 NEWS TRADE: {news_sig['reason']} | Ticket: {res['ticket']}"
                                log.info(msg)
                                send_telegram(msg)
                                NewsFetcher.log_to_website(news_sig)
                                continue # News trade takes precedence

                    # Skip if already in a trade
                    if executions[sym].has_open_trade():
                        pos = executions[sym].get_open_positions()
                        if pos:
                            p = pos[0]
                            log.info(f"[{sym}] Open: {p['direction']} "
                                     f"lot={p['volume']} profit={currency}{p['profit']:.2f}")
                        continue

                    # Fetch data -- all 4 timeframes using the safe local variables
                    df_h1  = handlers[sym].get_ohlc(_TF_H1,  count=200)
                    df_m15 = handlers[sym].get_ohlc(_TF_M15, count=100)
                    df_m5  = handlers[sym].get_ohlc(_TF_M5,  count=100)
                    df_m1  = handlers[sym].get_ohlc(_TF_M1,  count=100)

                    if df_h1 is None or df_m15 is None or df_m5 is None:
                        log.debug(f"[{sym}] Skipping -- waiting for data synchronization.")
                        continue

                    signal     = None
                    signal_tag = "SIGNAL"

                    # --- Strategy 1: SMC + CRT (only for SMC symbols) ---
                    if sym in strategies:
                        smc_signal = strategies[sym].evaluate(df_h1, df_m15, df_m5, df_m1)
                        if smc_signal:
                            signal     = smc_signal
                            signal_tag = f"RE-ENTRY" if smc_signal.reentry else f"SMC-{smc_signal.timeframe}"

                    # --- Strategy 2: Scalping 8:30-11:00 NY (all SCALP_SYMBOLS) ---
                    if signal is None and sym in SCALP_SYMBOLS:
                        scalper   = ScalpingStrategy(risk_pct=RISK_PCT, symbol=sym)
                        current_scalp_risk = web_settings.get("scalp_risk", risk_pct)
                        scalper   = ScalpingStrategy(risk_pct=current_scalp_risk, symbol=sym)
                        # Ensure we have data for all timeframes before evaluating
                        scalp_sig = None
                        if not df_m15.empty and not df_m5.empty and df_m1 is not None:
                            scalp_sig = scalper.evaluate(df_m15, df_m5, df_m1, balance=balance, current_time=datetime.now(timezone.utc))
                        if scalp_sig:
                            signal     = scalp_sig
                            signal_tag = "SCALP"

                    if signal:
                        log.info(f"[{sym}] [{signal_tag}] {signal.reason}")
                        lot = getattr(signal, 'lot', None)
                        if lot is None:
                            from risk_manager import RiskManager
                            rm  = RiskManager(risk_pct=risk_pct)
                            lot = rm.lot_size(balance, signal.entry, signal.sl, symbol=sym)
                        result = executions[sym].place_order(
                            direction=signal.direction,
                            lot=lot,
                            sl=signal.sl,
                            tp=signal.tp,
                        )
                        if result["success"]:
                            msg = (f"[{signal_tag}] {sym} {signal.direction.upper()} "
                                   f"lot={lot} SL={signal.sl} TP={signal.tp} "
                                   f"RR={signal.rr} ticket={result['ticket']}")
                            log.info(f"[{sym}] Trade placed -- ticket: {result['ticket']}")
                            send_telegram(msg)
                        else:
                            log.warning(f"[{sym}] Rejected -- {result['message']}")
                    else:
                        log.debug(f"[{sym}] No signal")

                    consecutive_errors = 0

                except Exception as e:
                    consecutive_errors += 1
                    log.error(f"[{sym}] Error: {e}", exc_info=True)
                    if consecutive_errors >= 10:
                        log.critical("10 consecutive errors -- reconnecting MT5...")
                        send_telegram("AutonomusAI WARNING: 10 errors. Reconnecting...")
                        try:
                            mt5.shutdown()
                        except Exception:
                            pass
                        time.sleep(10)
                        connect_mt5()
                        consecutive_errors = 0

            log.debug(f"Cycle complete -- {len(handlers)} symbols scanned. Sleeping 60s...")
            time.sleep(60)

    finally:
        log.info("AutonomusAI shutting down...")
        send_telegram("AutonomusAI stopped.")
        try:
            mt5.shutdown()
        except Exception:
            pass


# =============================================================================
# BACKTEST
# =============================================================================

def run_backtest(csv_path: str = None, risk_pct: float = RISK_PCT):
    log.info("AutonomusAI -- BACKTEST MODE")

    if csv_path:
        log.info(f"Loading: {csv_path}")
        df_raw = MarketDataHandler.load_csv(csv_path)
    else:
        log.info("No CSV -- using synthetic data")
        df_raw = MarketDataHandler.generate_synthetic(n=5000)

    df_m15 = df_raw.copy()
    df_h1  = _resample(df_raw, "h")
    df_m5  = _resample(df_raw, "5min")

    log.info(f"H1: {len(df_h1)} | M15: {len(df_m15)} | M5: {len(df_m5)}")

    bt = Backtester(df_h1=df_h1, df_m15=df_m15, df_m5=df_m5,
                    balance=BACKTEST_INITIAL_BALANCE, risk_pct=risk_pct)
    bt.run(start_bar=100)

    metrics = bt.metrics()
    log.info("=" * 55)
    log.info("BACKTEST RESULTS")
    for k, v in metrics.items():
        log.info(f"  {k.replace('_',' ').title():<25} {v}")

    if "net_pnl" in metrics and isinstance(metrics["net_pnl"], float):
        days    = (df_raw.index[-1] - df_raw.index[0]).days or 1
        monthly = (metrics["net_pnl"] / BACKTEST_INITIAL_BALANCE) / days * 30 * 100
        log.info(f"  {'Est. Monthly Return':<25} {monthly:.1f}%")
        log.info(f"  {'Est. Annual Return':<25} {monthly * 12:.1f}%")

    log.info("=" * 55)

    log_df = bt.trade_log()
    if not log_df.empty:
        log_df.to_csv("backtest_trades.csv", index=False)
        log.info("Trade log -> backtest_trades.csv")

    bt.equity_curve().to_csv("backtest_equity.csv", index=False)
    log.info("Equity curve -> backtest_equity.csv")
    return bt



# Helpers


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    return df.resample(rule).agg({
        "open": "first", "high": "max",
        "low": "min", "close": "last", "volume": "sum",
    }).dropna()



# CLI


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutonomusAI Trading System")
    parser.add_argument("--mode",   choices=["live", "backtest"], default="backtest")
    parser.add_argument("--risk",   type=float, default=RISK_PCT)
    parser.add_argument("--csv",    default=None)
    parser.add_argument("--account", type=str, default=None, help="Specify an account name from MT5_ACCOUNTS to run live mode for a single account. If omitted, all configured accounts will be processed sequentially.")
    args = parser.parse_args()

    if args.mode == "live":
        run_live(risk_pct=args.risk)
    else:
        run_backtest(csv_path=args.csv, risk_pct=args.risk)
