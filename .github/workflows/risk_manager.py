# =============================================================================
# risk_manager.py -- RiskManager
# Fully dynamic: fetches live pip values from MT5, converts to account currency.
# Works for ZAR accounts, USD accounts, or any currency.
# Works for any deposit size including under $5 / R5.
# =============================================================================

from config import RISK_PCT, MAX_RISK_PCT, SL_BUFFER_PIPS, SYMBOL_SPECS

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


class RiskManager:
    """
    Calculates lot size using live MT5 tick values converted to account currency.

    Key fix: Exness ZAR accounts report tick_value in ZAR already.
    MT5 always returns trade_tick_value in the account currency -- so no
    manual conversion is needed. We just use it directly.
    """

    def __init__(self, risk_pct: float = RISK_PCT,
                 sl_buffer_pips: float = SL_BUFFER_PIPS):
        if risk_pct > MAX_RISK_PCT:
            raise ValueError(f"risk_pct {risk_pct} exceeds MAX_RISK_PCT {MAX_RISK_PCT}")
        if risk_pct > 0.03:
            print(f"[RiskManager] WARNING: risk_pct={risk_pct:.0%} is aggressive.")
        self.risk_pct       = risk_pct
        self.sl_buffer_pips = sl_buffer_pips

    # ------------------------------------------------------------------
    # Live Symbol Info from MT5
    # ------------------------------------------------------------------

    def get_symbol_info(self, symbol: str) -> dict:
        """
        Returns pip_size, pip_value (in account currency per 1.0 lot),
        min_lot, max_lot, volume_step for a symbol.
        Always fetches live from MT5 for accuracy.
        """
        if MT5_AVAILABLE:
            try:
                info = mt5.symbol_info(symbol)
                if info:
                    # pip_size: 5-digit brokers use point*10, 3-digit use point
                    if info.digits in (5, 4):
                        pip_size = info.point * 10
                    else:
                        pip_size = info.point

                    # MT5 trade_tick_value is already in account currency (ZAR for ZAR accounts)
                    tick_val  = info.trade_tick_value
                    tick_size = info.trade_tick_size
                    pip_value = (tick_val / tick_size) * pip_size if tick_size > 0 else tick_val

                    return {
                        "pip_size":    pip_size,
                        "pip_value":   pip_value,       # per 1.0 lot, in account currency
                        "min_lot":     info.volume_min,
                        "max_lot":     info.volume_max,
                        "vol_step":    info.volume_step,
                        "digits":      info.digits,
                    }
            except Exception as e:
                print(f"[RiskManager] MT5 info error for {symbol}: {e}")

        # Fallback from registry
        specs = SYMBOL_SPECS.get(symbol, (0.0001, 0.01, 5))
        return {
            "pip_size":  specs[0],
            "pip_value": 10.0,
            "min_lot":   specs[1],
            "max_lot":   100.0,
            "vol_step":  0.01,
            "digits":    specs[2],
        }

    # ------------------------------------------------------------------
    # Stop Loss
    # ------------------------------------------------------------------

    def stop_loss(self, direction: str, ob_high: float, ob_low: float,
                  symbol: str = "EURUSDm", swing_low: float = None,
                  swing_high: float = None) -> float:
        s      = self.get_symbol_info(symbol)
        buffer = self.sl_buffer_pips * s["pip_size"]
        ob_mid = (ob_high + ob_low) / 2

        if direction == "bullish":
            sl_ob    = ob_low - buffer
            sl_swing = (swing_low - buffer) if swing_low and swing_low < ob_low else sl_ob
            sl       = max(sl_ob, sl_swing)
            sl       = min(sl, ob_mid - buffer)
        else:
            sl_ob    = ob_high + buffer
            sl_swing = (swing_high + buffer) if swing_high and swing_high > ob_high else sl_ob
            sl       = min(sl_ob, sl_swing)
            sl       = max(sl, ob_mid + buffer)

        return round(sl, s["digits"])

    # ------------------------------------------------------------------
    # Lot Sizing -- works for any balance in any currency
    # ------------------------------------------------------------------

    def lot_size(self, balance: float, entry: float, stop_loss_price: float,
                 symbol: str = "EURUSDm") -> float:
        """
        Calculates correct lot size for any account currency and balance.

        Formula:
            risk_amount  = balance * risk_pct          (in account currency)
            pip_distance = |entry - sl| / pip_size
            lot          = risk_amount / (pip_distance * pip_value_per_lot)

        pip_value is already in account currency (MT5 handles conversion).
        So this works identically for ZAR, USD, EUR accounts.
        """
        s = self.get_symbol_info(symbol)

        risk_amount  = balance * self.risk_pct
        pip_distance = abs(entry - stop_loss_price) / s["pip_size"] if s["pip_size"] > 0 else 1

        if pip_distance == 0 or s["pip_value"] == 0:
            return s["min_lot"]

        raw_lot = risk_amount / (pip_distance * s["pip_value"])

        # Round to broker volume step
        step    = s["vol_step"] if s["vol_step"] > 0 else 0.01
        lot     = round(round(raw_lot / step) * step, 2)

        # Clamp to broker limits
        lot = max(s["min_lot"], min(lot, s["max_lot"]))
        return lot

    # ------------------------------------------------------------------
    # Take Profit
    # ------------------------------------------------------------------

    def take_profit(self, direction: str, entry: float,
                    crt_high: float, crt_low: float,
                    symbol: str = "EURUSDm") -> float:
        digits = self.get_symbol_info(symbol)["digits"]
        if direction == "bullish":
            return round(crt_high, digits)
        return round(crt_low, digits)

    def risk_reward(self, entry: float, sl: float, tp: float) -> float:
        risk   = abs(entry - sl)
        reward = abs(tp - entry)
        return round(reward / risk, 2) if risk > 0 else 0.0
