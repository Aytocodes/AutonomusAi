# =============================================================================
# strategy_engine.py -- StrategyEngine with Timeframe Cascade
#
# Timeframe cascade logic:
#   1. Try M15 for CRT zone + liquidity sweep
#   2. If nothing on M15 -> try M5 for CRT zone + liquidity sweep
#   3. If nothing on M5  -> try M1 for CRT zone + liquidity sweep
#   4. Order block + FVG always checked on the lowest active timeframe
#
# This means the bot finds MORE setups without lowering quality standards.
# =============================================================================

from dataclasses import dataclass
from typing import Optional, Tuple
import pandas as pd

from trend_engine       import TrendEngine
from crt_detector       import CRTDetector, CRTZone
from liquidity_engine   import LiquidityEngine, LiquiditySweep
from order_block_engine import OrderBlockEngine, OrderBlock
from risk_manager       import RiskManager
from config             import RISK_PCT, MIN_RR, MAX_REENTRIES


@dataclass
class TradeSignal:
    direction:  str
    entry:      float
    sl:         float
    tp:         float
    lot:        float
    rr:         float
    reason:     str
    symbol:     str  = ""
    reentry:    bool = False
    timeframe:  str  = "M15"   # which TF the signal was found on


class StrategyEngine:
    """
    SMC + CRT strategy with automatic timeframe cascade.

    Cascade order: M15 -> M5 -> M1
    Each level uses the same entry rules but on a smaller timeframe.
    H1 trend bias is always required regardless of entry timeframe.
    """

    def __init__(self, balance: float = 10_000.0, risk_pct: float = RISK_PCT,
                 symbol: str = "EURUSDm"):
        self.symbol        = symbol
        self.trend_engine  = TrendEngine()
        self.crt_detector  = CRTDetector()
        self.liq_engine    = LiquidityEngine()
        self.ob_engine     = OrderBlockEngine()
        self.risk_manager  = RiskManager(risk_pct=risk_pct)
        self.balance       = balance
        self._reentry_count: dict = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        df_h1:  pd.DataFrame,
        df_m15: pd.DataFrame,
        df_m5:  pd.DataFrame,
        df_m1:  pd.DataFrame = None,
    ) -> Optional[TradeSignal]:
        """
        Evaluates all timeframes in cascade order.
        Returns the first valid signal found, or None.
        """
        # H1 trend is always required -- no trend = no trade
        bias = self.trend_engine.get_bias(df_h1)
        if bias == "neutral":
            return None

        # --- Cascade: M15 -> M5 -> M1 ---

        # Level 1: M15 CRT + sweep, M5 OB entry
        signal = self._evaluate_level(
            bias=bias,
            df_context=df_m15,   # CRT + sweep on M15
            df_entry=df_m5,      # OB on M5
            tf_label="M15",
        )
        if signal:
            return signal

        # Level 2: M5 CRT + sweep, M5 OB entry
        signal = self._evaluate_level(
            bias=bias,
            df_context=df_m5,
            df_entry=df_m5,
            tf_label="M5",
        )
        if signal:
            return signal

        # Level 3: M1 CRT + sweep, M1 OB entry (only if M1 data provided)
        if df_m1 is not None and len(df_m1) >= 30:
            signal = self._evaluate_level(
                bias=bias,
                df_context=df_m1,
                df_entry=df_m1,
                tf_label="M1",
            )
            if signal:
                return signal

        return None

    def reset_reentries(self, ob_index: int):
        self._reentry_count.pop(ob_index, None)

    # ------------------------------------------------------------------
    # Single Timeframe Evaluation
    # ------------------------------------------------------------------

    def _evaluate_level(
        self,
        bias:       str,
        df_context: pd.DataFrame,   # timeframe for CRT + sweep
        df_entry:   pd.DataFrame,   # timeframe for OB + FVG
        tf_label:   str,
    ) -> Optional[TradeSignal]:
        """Runs the full SMC checklist on a specific timeframe pair."""

        if len(df_context) < 25 or len(df_entry) < 15:
            return None

        # 1. CRT zone
        crt_zone = self.crt_detector.detect(df_context)
        if crt_zone is None or self.crt_detector.is_zone_broken(crt_zone, df_context):
            return None

        # 2. Liquidity sweep aligned with bias
        sweep = self.liq_engine.detect_sweep(df_context)
        if sweep is None:
            return None
        if bias == "bullish" and sweep.direction != "bullish_sweep":
            return None
        if bias == "bearish" and sweep.direction != "bearish_sweep":
            return None

        # 3. Order block on entry timeframe
        ob = self.ob_engine.get_nearest_ob(df_entry, direction=bias)
        if ob is None:
            return None

        # 4. Price inside OB
        last_price = df_entry["close"].iloc[-1]
        if not ob.price_inside(last_price):
            return None

        # 5. FVG filter
        if not self.ob_engine.price_in_fvg(df_entry, direction=bias):
            return None

        # 6. Build signal
        signal = self._build_signal(bias, last_price, ob, crt_zone, df_entry, tf_label)
        if signal.rr < MIN_RR:
            return None

        # 7. Re-entry check
        # Use the timestamp of the OB candle as a unique key instead of relative index
        ob_key = str(df_entry.index[ob.ob_index]) 
        count  = self._reentry_count.get(ob_key, 0)
        if count >= MAX_REENTRIES + 1:
            return None
        if count > 0:
            signal.reentry = True
        self._reentry_count[ob_key] = count + 1

        return signal

    # ------------------------------------------------------------------
    # Signal Builder
    # ------------------------------------------------------------------

    def _build_signal(
        self,
        direction: str,
        entry:     float,
        ob:        OrderBlock,
        crt:       CRTZone,
        df_entry:  pd.DataFrame,
        tf_label:  str,
    ) -> TradeSignal:
        levels     = self.liq_engine.get_swing_levels(df_entry)
        swing_low  = levels.get("swing_low")
        swing_high = levels.get("swing_high")

        sl  = self.risk_manager.stop_loss(
            direction, ob.ob_high, ob.ob_low,
            symbol=self.symbol, swing_low=swing_low, swing_high=swing_high
        )
        tp  = self.risk_manager.take_profit(
            direction, entry, crt.high, crt.low, symbol=self.symbol
        )
        lot = self.risk_manager.lot_size(self.balance, entry, sl, symbol=self.symbol)
        rr  = self.risk_manager.risk_reward(entry, sl, tp)

        reason = (
            f"{direction.upper()} [{tf_label}] | "
            f"OB [{ob.ob_low:.5g}-{ob.ob_high:.5g}] | "
            f"CRT [{crt.low:.5g}-{crt.high:.5g}] | "
            f"SL={sl} TP={tp} RR={rr}"
        )

        return TradeSignal(
            direction=direction, entry=entry, sl=sl, tp=tp,
            lot=lot, rr=rr, reason=reason,
            symbol=self.symbol, timeframe=tf_label
        )
