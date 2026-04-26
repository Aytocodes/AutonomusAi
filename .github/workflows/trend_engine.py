# =============================================================================
# trend_engine.py — TrendEngine
# Determines H1 market bias using EMA and market structure (HH/HL or LH/LL).
# =============================================================================

import pandas as pd
import numpy as np
from config import EMA_PERIOD


class TrendEngine:
    """
    Analyses H1 candles to produce a directional bias: 'bullish', 'bearish', or 'neutral'.

    Two methods are combined:
      1. EMA slope — price above/below EMA(50)
      2. Market structure — sequence of Higher Highs/Higher Lows or Lower Highs/Lower Lows
    Both must agree for a confirmed bias; otherwise 'neutral' is returned.
    """

    def __init__(self, ema_period: int = EMA_PERIOD):
        self.ema_period = ema_period

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_bias(self, df: pd.DataFrame) -> str:
        """
        Returns 'bullish', 'bearish', or 'neutral' based on the latest H1 candles.

        Parameters
        ----------
        df : pd.DataFrame
            H1 OHLCV data with columns open, high, low, close.
        """
        if len(df) < self.ema_period + 5:
            return "neutral"

        ema_bias       = self._ema_bias(df)
        structure_bias = self._structure_bias(df)

        if ema_bias == structure_bias:
            return ema_bias
        return "neutral"

    def get_ema(self, df: pd.DataFrame) -> pd.Series:
        """Returns the EMA series for charting / debugging."""
        return df["close"].ewm(span=self.ema_period, adjust=False).mean()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ema_bias(self, df: pd.DataFrame) -> str:
        ema   = self.get_ema(df)
        price = df["close"].iloc[-1]
        slope = ema.iloc[-1] - ema.iloc[-5]   # 5-bar slope

        if price > ema.iloc[-1] and slope > 0:
            return "bullish"
        if price < ema.iloc[-1] and slope < 0:
            return "bearish"
        return "neutral"

    def _structure_bias(self, df: pd.DataFrame, swing_lookback: int = 5) -> str:
        """
        Identifies the last two swing highs and swing lows.
        HH + HL → bullish; LH + LL → bearish.
        """
        highs = self._swing_highs(df, swing_lookback)
        lows  = self._swing_lows(df, swing_lookback)

        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1] > highs[-2]   # Higher High
            hl = lows[-1]  > lows[-2]    # Higher Low
            lh = highs[-1] < highs[-2]   # Lower High
            ll = lows[-1]  < lows[-2]    # Lower Low

            if hh and hl:
                return "bullish"
            if lh and ll:
                return "bearish"

        return "neutral"

    @staticmethod
    def _swing_highs(df: pd.DataFrame, n: int) -> list:
        """Returns a list of swing high prices (local maxima with n-bar lookback)."""
        highs = []
        for i in range(n, len(df) - n):
            window = df["high"].iloc[i - n: i + n + 1]
            if df["high"].iloc[i] == window.max():
                highs.append(df["high"].iloc[i])
        return highs

    @staticmethod
    def _swing_lows(df: pd.DataFrame, n: int) -> list:
        """Returns a list of swing low prices (local minima with n-bar lookback)."""
        lows = []
        for i in range(n, len(df) - n):
            window = df["low"].iloc[i - n: i + n + 1]
            if df["low"].iloc[i] == window.min():
                lows.append(df["low"].iloc[i])
        return lows
