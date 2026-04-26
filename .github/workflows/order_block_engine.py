# =============================================================================
# order_block_engine.py — OrderBlockEngine + FVG Detection
# Identifies bullish/bearish order blocks and Fair Value Gaps (imbalances).
# =============================================================================

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional, List
from config import OB_LOOKBACK, IMPULSE_MULTIPLIER, USE_FVG_FILTER


@dataclass
class OrderBlock:
    """Represents a detected order block zone."""
    direction:  str    # 'bullish' or 'bearish'
    ob_high:    float  # Top of the order block candle
    ob_low:     float  # Bottom of the order block candle
    ob_index:   int    # Bar index of the order block candle
    mitigated:  bool = False  # True once price has traded through it

    def price_inside(self, price: float) -> bool:
        return self.ob_low <= price <= self.ob_high

    @property
    def midpoint(self) -> float:
        return (self.ob_high + self.ob_low) / 2


@dataclass
class FairValueGap:
    """Represents a Fair Value Gap (3-candle imbalance)."""
    direction: str    # 'bullish' or 'bearish'
    gap_high:  float
    gap_low:   float
    gap_index: int    # Index of the middle candle

    def price_inside(self, price: float) -> bool:
        return self.gap_low <= price <= self.gap_high


class OrderBlockEngine:
    """
    Detects order blocks and Fair Value Gaps on M5 or M1 data.

    Order Block logic:
      - Bullish OB: last bearish candle before a strong bullish impulse move.
      - Bearish OB: last bullish candle before a strong bearish impulse move.

    FVG logic (3-candle pattern):
      - Bullish FVG: candle[i+1].low > candle[i-1].high  (gap up)
      - Bearish FVG: candle[i+1].high < candle[i-1].low  (gap down)
    """

    def __init__(
        self,
        lookback: int = OB_LOOKBACK,
        impulse_mult: float = IMPULSE_MULTIPLIER,
        use_fvg: bool = USE_FVG_FILTER,
    ):
        self.lookback     = lookback
        self.impulse_mult = impulse_mult
        self.use_fvg      = use_fvg

    # ------------------------------------------------------------------
    # Order Block Detection
    # ------------------------------------------------------------------

    def detect_order_blocks(self, df: pd.DataFrame) -> List[OrderBlock]:
        """
        Scans the last `lookback` candles and returns all valid order blocks.
        Most recent OBs are at the end of the list.
        """
        if len(df) < self.lookback + 2:
            return []

        window   = df.iloc[-self.lookback:]
        avg_range = (window["high"] - window["low"]).mean()
        blocks   = []

        for i in range(1, len(window) - 1):
            prev = window.iloc[i - 1]
            curr = window.iloc[i]
            nxt  = window.iloc[i + 1]

            curr_range = curr["high"] - curr["low"]
            nxt_range  = nxt["high"]  - nxt["low"]

            # Bullish OB: bearish candle followed by strong bullish impulse
            if (prev["close"] < prev["open"] and          # prev is bearish
                    nxt["close"] > nxt["open"] and         # next is bullish
                    nxt_range > avg_range * self.impulse_mult):
                blocks.append(OrderBlock(
                    direction="bullish",
                    ob_high=prev["high"],
                    ob_low=prev["low"],
                    ob_index=len(df) - self.lookback + (i - 1),
                ))

            # Bearish OB: bullish candle followed by strong bearish impulse
            elif (prev["close"] > prev["open"] and         # prev is bullish
                      nxt["close"] < nxt["open"] and       # next is bearish
                      nxt_range > avg_range * self.impulse_mult):
                blocks.append(OrderBlock(
                    direction="bearish",
                    ob_high=prev["high"],
                    ob_low=prev["low"],
                    ob_index=len(df) - self.lookback + (i - 1),
                ))

        return blocks

    def get_nearest_ob(self, df: pd.DataFrame, direction: str) -> Optional[OrderBlock]:
        """
        Returns the most recent unmitigated order block matching `direction`.
        Marks OBs as mitigated if price has already closed through them.
        """
        blocks    = self.detect_order_blocks(df)
        last_close = df["close"].iloc[-1]
        candidates = []

        for ob in blocks:
            if ob.direction != direction:
                continue
            # Mitigate if price has closed beyond the OB
            if direction == "bullish" and last_close < ob.ob_low:
                ob.mitigated = True
            elif direction == "bearish" and last_close > ob.ob_high:
                ob.mitigated = True

            if not ob.mitigated:
                candidates.append(ob)

        return candidates[-1] if candidates else None

    # ------------------------------------------------------------------
    # Fair Value Gap Detection
    # ------------------------------------------------------------------

    def detect_fvg(self, df: pd.DataFrame) -> List[FairValueGap]:
        """
        Scans for Fair Value Gaps in the last `lookback` candles.
        Returns all detected FVGs (bullish and bearish).
        """
        if len(df) < self.lookback + 2:
            return []

        window = df.iloc[-self.lookback:]
        gaps   = []

        for i in range(1, len(window) - 1):
            c1 = window.iloc[i - 1]
            c3 = window.iloc[i + 1]

            # Bullish FVG: gap between c1 high and c3 low (price jumped up)
            if c3["low"] > c1["high"]:
                gaps.append(FairValueGap(
                    direction="bullish",
                    gap_high=c3["low"],
                    gap_low=c1["high"],
                    gap_index=len(df) - self.lookback + i,
                ))

            # Bearish FVG: gap between c3 high and c1 low (price dropped)
            elif c3["high"] < c1["low"]:
                gaps.append(FairValueGap(
                    direction="bearish",
                    gap_high=c1["low"],
                    gap_low=c3["high"],
                    gap_index=len(df) - self.lookback + i,
                ))

        return gaps

    def price_in_fvg(self, df: pd.DataFrame, direction: str) -> bool:
        """
        Returns True if the current price is inside a matching FVG.
        Used as an optional entry confirmation filter.
        """
        if not self.use_fvg:
            return True   # FVG filter disabled — always pass

        fvgs       = self.detect_fvg(df)
        last_close = df["close"].iloc[-1]

        for fvg in fvgs:
            if fvg.direction == direction and fvg.price_inside(last_close):
                return True

        return False
