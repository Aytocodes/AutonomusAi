# =============================================================================
# scalping_strategy.py -- Combined First Candle + Stupid Simple Scalping
# Works in BOTH live trading and historical backtesting.
#
# Key fix: accepts current_time parameter so backtesting can pass
# historical bar timestamps instead of datetime.now()
# =============================================================================

import pandas as pd
from dataclasses import dataclass
from typing      import Optional
from datetime    import datetime, time
import pytz

from order_block_engine import OrderBlockEngine
from risk_manager       import RiskManager
from config             import RISK_PCT, SL_BUFFER_PIPS

NY_TZ         = pytz.timezone("America/New_York")
SESSION_START = time(8, 30)
SESSION_END   = time(11, 0)
MIN_SCALP_RR  = 2.0

# Symbols optimised for 8:30 NY open scalping
# Chosen for high volatility at NY open -- different from SMC symbol list
SCALP_SYMBOLS = [
    "XAUUSDm",   # Gold    -- biggest NY open moves
    "US30m",     # Dow     -- pre-market flow starts at 8:30
    "XAGUSDm",   # Silver  -- follows gold at NY open
    "EURUSDm",   # Fiber   -- most liquid, clean sweeps
    "GBPUSDm",   # Cable   -- strongest London/NY overlap moves
    "USTECm",    # Nasdaq  -- explosive NY open (short trades only)
    "GBPJPYm",   # Beast   -- biggest pip moves at NY open
    "US500m",    # S&P500  -- institutional flow at open
]

def _to_ny(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    if d.index.tzinfo is None:
        d.index = d.index.tz_localize("UTC")
    return d.tz_convert(NY_TZ) if hasattr(d, "tz_convert") else d


@dataclass
class ScalpSignal:
    direction:         str
    entry:             float
    sl:                float
    tp:                float
    rr:                float
    first_candle_high: float
    first_candle_low:  float
    reason:            str


class ScalpingStrategy:
    """
    Combined First Candle + Stupid Simple Scalping.

    Pass current_time (bar timestamp) for backtesting.
    Leave current_time=None for live trading (uses datetime.now).
    """

    def __init__(self, risk_pct: float = RISK_PCT, symbol: str = "XAUUSDm"):
        self.ob_engine    = OrderBlockEngine()
        self.risk_manager = RiskManager(risk_pct=risk_pct)
        self.symbol       = symbol

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_time(self, current_time=None):
        """Returns (bar_time, ref_date) in NY timezone."""
        if current_time is not None:
            try:
                if isinstance(current_time, pd.Timestamp):
                    ct = current_time
                    if ct.tzinfo is None:
                        ct = ct.tz_localize("UTC")
                    ct = ct.tz_convert(NY_TZ)
                else:
                    ct = pd.Timestamp(current_time)
                    if ct.tzinfo is None:
                        ct = ct.tz_localize("UTC")
                    ct = ct.tz_convert(NY_TZ)
                return ct.time(), ct.date()
            except Exception:
                return None, None
        else:
            now = datetime.now(NY_TZ)
            return now.time(), now.date()

    def _localize(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        d = df.copy()
        if d.index.tzinfo is None:
            d.index = d.index.tz_localize("UTC")
        d.index = d.index.tz_convert(NY_TZ)
        return d

    # ------------------------------------------------------------------
    # First Candle Detection
    # ------------------------------------------------------------------

    def capture_first_candle(self, df_m15: pd.DataFrame,
                              ref_date) -> Optional[dict]:
        if df_m15.empty:
            return None
        df   = self._localize(df_m15)
        mask = (
            (df.index.date == ref_date) &
            (df.index.hour == 8) &
            (df.index.minute == 30)
        )
        candles = df[mask]
        if candles.empty:
            return None
        c = candles.iloc[0]
        return {
            "open":      c["open"],
            "high":      c["high"],
            "low":       c["low"],
            "close":     c["close"],
            "direction": "bullish" if c["close"] > c["open"] else "bearish",
            "date":      ref_date,
        }

    # ------------------------------------------------------------------
    # Sweep Detection
    # ------------------------------------------------------------------

    def detect_sweep(self, df: pd.DataFrame,
                     first_candle: dict) -> Optional[str]:
        if df.empty or first_candle is None:
            return None
        d        = self._localize(df)
        ref_date = first_candle["date"]
        post     = d[
            (d.index.date == ref_date) &
            (d.index.time() > time(8, 30))
        ]
        if post.empty:
            return None

        pip_size = self.risk_manager.get_pip_info(self.symbol)[0]
        buf      = SL_BUFFER_PIPS * pip_size
        fc_high  = first_candle["high"]
        fc_low   = first_candle["low"]

        for _, bar in post.iterrows():
            if bar["high"] > fc_high + buf and bar["close"] < fc_high:
                return "bearish_sweep"
            if bar["low"]  < fc_low  - buf and bar["close"] > fc_low:
                return "bullish_sweep"
        return None

    # ------------------------------------------------------------------
    # Session Levels (TP target)
    # ------------------------------------------------------------------

    def get_session_levels(self, df_m15: pd.DataFrame,
                           ref_date) -> dict:
        if df_m15.empty:
            return {}
        df  = self._localize(df_m15)
        pre = df[
            (df.index.date == ref_date) &
            (df.index.time() < time(8, 30))
        ]
        if pre.empty:
            pre = df.iloc[-20:]
        return {
            "session_high": pre["high"].max(),
            "session_low":  pre["low"].min(),
        }

    # ------------------------------------------------------------------
    # Main Evaluate
    # ------------------------------------------------------------------

    def evaluate(
        self,
        df_m15:       pd.DataFrame,
        df_m5:        pd.DataFrame,
        df_m1:        pd.DataFrame = None,
        balance:      float        = 10_000.0,
        current_time               = None,
    ) -> Optional[ScalpSignal]:

        # 1. Resolve time reference
        bar_time, ref_date = self._resolve_time(current_time)
        if bar_time is None:
            return None

        # 2. Session filter 8:30-11:00 NY
        if not (SESSION_START <= bar_time <= SESSION_END):
            return None

        # 3. First candle at 8:30
        first_candle = self.capture_first_candle(df_m15, ref_date)
        if first_candle is None:
            return None

        # 4. Sweep cascade M15 -> M5 -> M1
        sweep    = self.detect_sweep(df_m15, first_candle)
        sweep_tf = "M15"
        if sweep is None and not df_m5.empty:
            sweep    = self.detect_sweep(df_m5, first_candle)
            sweep_tf = "M5"
        if sweep is None and df_m1 is not None and not df_m1.empty:
            sweep    = self.detect_sweep(df_m1, first_candle)
            sweep_tf = "M1"
        if sweep is None:
            return None

        direction = "bullish" if sweep == "bullish_sweep" else "bearish"

        # 5. OB/FVG cascade M5 -> M1
        ob         = self.ob_engine.get_nearest_ob(df_m5, direction=direction)
        last_price = df_m5["close"].iloc[-1]
        entry_tf   = "M5"

        if (ob is None or not ob.price_inside(last_price)) and \
                df_m1 is not None and not df_m1.empty:
            ob_m1 = self.ob_engine.get_nearest_ob(df_m1, direction=direction)
            lp_m1 = df_m1["close"].iloc[-1]
            if ob_m1 and ob_m1.price_inside(lp_m1):
                ob, last_price, entry_tf = ob_m1, lp_m1, "M1"

        if ob is not None and ob.price_inside(last_price):
            entry, ob_high, ob_low = last_price, ob.ob_high, ob.ob_low
            zone_tag = f"OB-{entry_tf}"
        else:
            fvgs = self.ob_engine.detect_fvg(df_m5)
            fvg  = next((f for f in fvgs
                         if f.direction == direction
                         and f.price_inside(last_price)), None)
            if fvg is None and df_m1 is not None and not df_m1.empty:
                lp_m1 = df_m1["close"].iloc[-1]
                fvgs1 = self.ob_engine.detect_fvg(df_m1)
                fvg   = next((f for f in fvgs1
                              if f.direction == direction
                              and f.price_inside(lp_m1)), None)
                if fvg:
                    last_price, entry_tf = lp_m1, "M1"
            if fvg is None:
                return None
            entry, ob_high, ob_low = last_price, fvg.gap_high, fvg.gap_low
            zone_tag = f"FVG-{entry_tf}"

        # 6. SL beyond first candle extreme
        pip_size = self.risk_manager.get_pip_info(self.symbol)[0]
        buf      = SL_BUFFER_PIPS * pip_size
        sl = round(first_candle["low"]  - buf, 5) if direction == "bullish" \
             else round(first_candle["high"] + buf, 5)

        # 7. TP at opposite session level
        levels = self.get_session_levels(df_m15, ref_date)
        tp = round(levels.get("session_high", entry + abs(entry - sl) * 3), 5) \
             if direction == "bullish" \
             else round(levels.get("session_low",  entry - abs(entry - sl) * 3), 5)

        # 8. RR check
        rr = self.risk_manager.risk_reward(entry, sl, tp)
        if rr < MIN_SCALP_RR:
            return None

        return ScalpSignal(
            direction=direction, entry=entry, sl=sl, tp=tp, rr=rr,
            first_candle_high=first_candle["high"],
            first_candle_low=first_candle["low"],
            reason=(
                f"SCALP {direction.upper()} [{sweep_tf}] | {zone_tag} | "
                f"FC [{first_candle['low']:.5g}-{first_candle['high']:.5g}] | "
                f"SL={sl} TP={tp} RR={rr}"
            ),
        )
