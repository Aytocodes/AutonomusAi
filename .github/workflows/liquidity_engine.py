# =============================================================================
# liquidity_engine.py — LiquidityEngine
# Detects sweeps of swing highs (sell-side) and swing lows (buy-side).
# A sweep = price wicks beyond a key level then closes back inside.
# =============================================================================

import pandas as pd
from dataclasses import dataclass
from typing import Optional
from config import LIQUIDITY_LOOKBACK, SWEEP_BUFFER_PCT


@dataclass
class LiquiditySweep:
    """Describes a detected liquidity sweep event."""
    direction:   str    # 'bullish_sweep' (swept lows) or 'bearish_sweep' (swept highs)
    swept_level: float  # The price level that was swept
    sweep_index: int    # Bar index where sweep occurred
    close_price: float  # Close of the sweep candle


class LiquidityEngine:
    """
    Identifies liquidity sweeps on any timeframe.

    Bullish sweep  → price wicks below a prior swing low then closes above it.
                     Signals potential long entry (smart money grabbed sell stops).

    Bearish sweep  → price wicks above a prior swing high then closes below it.
                     Signals potential short entry (smart money grabbed buy stops).
    """

    def __init__(
        self,
        lookback: int = LIQUIDITY_LOOKBACK,
        buffer_pct: float = SWEEP_BUFFER_PCT,
    ):
        self.lookback   = lookback
        self.buffer_pct = buffer_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_sweep(self, df: pd.DataFrame) -> Optional[LiquiditySweep]:
        """
        Checks the most recent candle for a liquidity sweep.

        Returns a LiquiditySweep if one is detected, else None.
        """
        if len(df) < self.lookback + 2:
            return None

        # Reference window excludes the last candle (that's the sweep candle)
        ref    = df.iloc[-(self.lookback + 1):-1]
        latest = df.iloc[-1]

        swing_high = ref["high"].max()
        swing_low  = ref["low"].min()

        buffer_h = swing_high * self.buffer_pct
        buffer_l = swing_low  * self.buffer_pct

        # Bearish sweep: wick above swing high, close back below it
        if latest["high"] > swing_high + buffer_h and latest["close"] < swing_high:
            return LiquiditySweep(
                direction="bearish_sweep",
                swept_level=swing_high,
                sweep_index=len(df) - 1,
                close_price=latest["close"],
            )

        # Bullish sweep: wick below swing low, close back above it
        if latest["low"] < swing_low - buffer_l and latest["close"] > swing_low:
            return LiquiditySweep(
                direction="bullish_sweep",
                swept_level=swing_low,
                sweep_index=len(df) - 1,
                close_price=latest["close"],
            )

        return None

    def get_swing_levels(self, df: pd.DataFrame) -> dict:
        """Returns the current swing high and swing low from the lookback window."""
        if len(df) < self.lookback:
            return {}
        ref = df.iloc[-self.lookback:]
        return {
            "swing_high": ref["high"].max(),
            "swing_low":  ref["low"].min(),
        }
