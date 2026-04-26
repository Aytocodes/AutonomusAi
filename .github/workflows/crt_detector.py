# =============================================================================
# crt_detector.py — CRTDetector (Candle Range Theory)
# Detects M15 consolidation zones, CRT high/low, and liquidity pools.
# =============================================================================

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from config import CRT_LOOKBACK, CRT_VOLATILITY_PCT


@dataclass
class CRTZone:
    """Represents a detected CRT consolidation zone."""
    high:        float
    low:         float
    start_index: int
    end_index:   int
    midpoint:    float = field(init=False)
    valid:       bool  = True

    def __post_init__(self):
        self.midpoint = (self.high + self.low) / 2

    @property
    def range_size(self) -> float:
        return self.high - self.low

    def price_inside(self, price: float) -> bool:
        return self.low <= price <= self.high


class CRTDetector:
    """
    Candle Range Theory detector.

    Scans M15 data for a consolidation range (low ATR / tight price action),
    marks the CRT high and CRT low as liquidity targets, and validates
    whether the zone is still active (price hasn't broken out yet).
    """

    def __init__(
        self,
        lookback: int = CRT_LOOKBACK,
        volatility_pct: float = CRT_VOLATILITY_PCT,
    ):
        self.lookback       = lookback
        self.volatility_pct = volatility_pct

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, df: pd.DataFrame) -> Optional[CRTZone]:
        """
        Scans the last `lookback` candles for a consolidation zone.

        Returns a CRTZone if found, else None.
        """
        if len(df) < self.lookback:
            return None

        window = df.iloc[-self.lookback:]
        zone_high = window["high"].max()
        zone_low  = window["low"].min()
        mid_price = (zone_high + zone_low) / 2

        # Consolidation criterion: range is small relative to price
        range_ratio = (zone_high - zone_low) / mid_price
        if range_ratio > self.volatility_pct:
            return None

        # Confirm at least 60% of candles stay inside the range
        inside = window.apply(
            lambda r: zone_low <= r["close"] <= zone_high, axis=1
        )
        if inside.mean() < 0.60:
            return None

        start_idx = len(df) - self.lookback
        end_idx   = len(df) - 1

        return CRTZone(
            high=zone_high,
            low=zone_low,
            start_index=start_idx,
            end_index=end_idx,
        )

    def is_zone_broken(self, zone: CRTZone, df: pd.DataFrame) -> bool:
        """
        Returns True if price has closed outside the CRT zone,
        invalidating it as a consolidation reference.
        """
        if zone is None:
            return True
        last_close = df["close"].iloc[-1]
        return last_close > zone.high or last_close < zone.low

    def liquidity_targets(self, zone: CRTZone) -> dict:
        """
        Returns the buy-side and sell-side liquidity levels derived from the zone.
        Buy-side liquidity sits above the CRT high (target for shorts).
        Sell-side liquidity sits below the CRT low (target for longs).
        """
        if zone is None:
            return {}
        return {
            "buy_side_liquidity":  zone.high,   # Resting orders above range
            "sell_side_liquidity": zone.low,     # Resting orders below range
        }
