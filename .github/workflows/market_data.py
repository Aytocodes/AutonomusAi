# =============================================================================
# market_data.py — MarketDataHandler
# Fetches OHLC candle data from MetaTrader 5 or a CSV fallback.
# =============================================================================

import pandas as pd
import numpy as np
import os
from datetime import datetime
from config import SYMBOL, SYMBOL_FALLBACKS

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


# Maps string timeframe labels to MT5 constants
_TF_MAP = {
    "M1":  1,
    "M5":  5,
    "M15": 15,
    "H1":  16385,
    "H4":  16388,
    "D1":  16408,
}


class MarketDataHandler:
    """
    Fetches OHLC data from MetaTrader 5.
    Falls back to CSV or synthetic data when MT5 is unavailable (backtest mode).
    """

    def __init__(self, symbol: str = SYMBOL, live: bool = False):
        self.symbol = symbol
        self.live   = live
        self._connected = False # This will now be managed by the main bot

        if live:
            # In live mode, assume MT5 is already initialized by the main script.
            # Just resolve the symbol.
            self._resolve_symbol()

    # ------------------------------------------------------------------
    # Connection (simplified, assumes mt5.initialize is done externally)
    # ------------------------------------------------------------------

    def _resolve_symbol(self):
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 package not installed. Run: pip install MetaTrader5")
        if not mt5.is_connected(): # Check if MT5 is actually connected
            raise ConnectionError("MT5 is not connected. Initialize MT5 before creating MarketDataHandler in live mode.")

        # Resolve symbol with fallback suffixes
        for sym in [self.symbol] + SYMBOL_FALLBACKS:
            info = mt5.symbol_info(sym)
            if info and info.visible:
                self.symbol = sym
                break
        else:
            mt5.shutdown()
            raise ValueError(f"Symbol not found on broker. Tried: {[self.symbol] + SYMBOL_FALLBACKS}")

        self._connected = True
        print(f"[MT5] Connected — trading symbol: {self.symbol}")

    def disconnect(self):
        if MT5_AVAILABLE and self._connected:
            mt5.shutdown()
            self._connected = False
        # MarketDataHandler no longer manages mt5.shutdown()
        # This method can be removed or left as a placeholder if needed for other cleanup
        pass

    # ------------------------------------------------------------------
    # Data Fetching
    # ------------------------------------------------------------------

    def get_ohlc(self, timeframe: str, count: int = 500) -> pd.DataFrame:
        """
        Returns a DataFrame with columns: time, open, high, low, close, volume.
        Uses MT5 in live mode, otherwise raises (caller should use load_csv).
        """
        if not self.live:
            raise RuntimeError("Call load_csv() for backtest data, or set live=True.")
        if not MT5_AVAILABLE or not mt5.is_connected():
            raise ConnectionError("MT5 is not connected. Cannot fetch OHLC data.")
        if not self._connected: # Check if symbol was resolved
            raise RuntimeError(f"MarketDataHandler for {self.symbol} is not properly initialized (symbol not resolved).")

        tf_const = _TF_MAP.get(timeframe)
        if tf_const is None:
            raise ValueError(f"Unknown timeframe: {timeframe}")

        rates = mt5.copy_rates_from_pos(self.symbol, tf_const, 0, count)
        if rates is None or len(rates) == 0:
            # Log error from MT5 if no data
            last_error = mt5.last_error()
            if last_error and last_error[0] != 0: # Check if there's an actual MT5 error
                raise RuntimeError(f"No data returned for {self.symbol} {timeframe}: {last_error}")
            else: # No data, but no specific MT5 error, might be normal for new symbols/timeframes
                return pd.DataFrame() # Return empty DataFrame instead of raising generic error

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        return df[["open", "high", "low", "close", "tick_volume"]].rename(
            columns={"tick_volume": "volume"}
        )

    def get_tick(self) -> dict:
        """Returns latest bid/ask/spread for the symbol."""
        if not self.live or not MT5_AVAILABLE:
            return {}
        if not self._connected: # Check if symbol was resolved
            return {}
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return {}
        info = mt5.symbol_info(self.symbol)
        spread_pips = (tick.ask - tick.bid) / (info.point * 10) if info else 0
        return {"bid": tick.bid, "ask": tick.ask, "spread_pips": spread_pips}

    # ------------------------------------------------------------------
    # CSV / Backtest Loader
    # ------------------------------------------------------------------

    @staticmethod
    def load_csv(path: str) -> pd.DataFrame:
        """
        Load OHLCV data from a CSV file.
        Expected columns: time, open, high, low, close, volume
        """
        df = pd.read_csv(path, parse_dates=["time"])
        df.set_index("time", inplace=True)
        df.columns = [c.lower() for c in df.columns]
        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            raise ValueError(f"CSV must contain columns: {required}")
        if "volume" not in df.columns:
            df["volume"] = 1
        return df.sort_index()

    @staticmethod
    def generate_synthetic(n: int = 5000, seed: int = 42) -> pd.DataFrame:
        """
        Generates synthetic OHLCV data with realistic trending, consolidation,
        and impulsive moves to trigger SMC/CRT signals during backtesting.
        """
        rng   = np.random.default_rng(seed)
        dates = pd.date_range("2024-01-01", periods=n, freq="15min")

        # Build price with alternating trend + consolidation phases
        close = np.zeros(n)
        close[0] = 2000.0
        segment = 60  # bars per phase

        for i in range(1, n):
            phase = (i // segment) % 4
            if phase == 0:    # strong uptrend
                drift = rng.normal(0.8, 1.2)
            elif phase == 1:  # consolidation
                drift = rng.normal(0.0, 0.4)
            elif phase == 2:  # strong downtrend
                drift = rng.normal(-0.8, 1.2)
            else:             # consolidation
                drift = rng.normal(0.0, 0.4)
            close[i] = close[i - 1] + drift

        # Occasionally inject impulse spikes to create OBs and sweeps
        spike_idx = rng.choice(n - 5, size=n // 80, replace=False)
        for idx in spike_idx:
            direction = 1 if rng.random() > 0.5 else -1
            close[idx: idx + 3] += direction * rng.uniform(4, 10)

        noise = rng.uniform(0.8, 4.0, n)
        high  = close + noise + rng.uniform(0, 2, n)
        low   = close - noise - rng.uniform(0, 2, n)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        vol   = rng.integers(200, 2000, n)

        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
            index=dates,
        )
