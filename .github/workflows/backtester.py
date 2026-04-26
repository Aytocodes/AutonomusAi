# =============================================================================
# backtester.py — Backtesting Engine
# Simulates the SMC/CRT strategy on historical data using a rolling window.
# Produces trade log, equity curve, and performance metrics.
# =============================================================================

import pandas as pd
import numpy as np
from typing import List, Dict
from dataclasses import dataclass, field

from strategy_engine import StrategyEngine, TradeSignal
from config import BACKTEST_INITIAL_BALANCE, BACKTEST_COMMISSION_PCT


@dataclass
class BacktestTrade:
    """Records a single simulated trade."""
    direction:   str
    entry:       float
    sl:          float
    tp:          float
    lot:         float
    entry_index: int
    exit_index:  int  = -1
    exit_price:  float = 0.0
    pnl:         float = 0.0
    outcome:     str   = "open"   # 'win', 'loss', 'open'


class Backtester:
    """
    Event-driven backtester that walks forward through M5 data,
    slicing H1 and M15 windows at each step to simulate real-time conditions.

    Assumptions:
      - Fills at close of signal candle (conservative)
      - Commission deducted on entry
      - SL/TP checked on each subsequent candle's high/low
      - Only one trade open at a time
    """

    def __init__(
        self,
        df_h1:   pd.DataFrame,
        df_m15:  pd.DataFrame,
        df_m5:   pd.DataFrame,
        balance: float = BACKTEST_INITIAL_BALANCE,
        risk_pct: float = 0.01,
    ):
        self.df_h1    = df_h1.copy()
        self.df_m15   = df_m15.copy()
        self.df_m5    = df_m5.copy()
        self.balance  = balance
        self.risk_pct = risk_pct

        self.trades:  List[BacktestTrade] = []
        self.equity:  List[float]         = [balance]
        self._engine  = StrategyEngine(balance=balance, risk_pct=risk_pct)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, start_bar: int = 100) -> "Backtester":
        """
        Walks forward from `start_bar` to end of df_m5.
        Returns self for chaining.
        """
        open_trade: BacktestTrade | None = None

        for i in range(start_bar, len(self.df_m5)):
            # Slice data up to current bar (no lookahead)
            m5_slice  = self.df_m5.iloc[:i + 1]
            m15_slice = self._align_slice(self.df_m15, m5_slice.index[-1])
            h1_slice  = self._align_slice(self.df_h1,  m5_slice.index[-1])

            current_bar = self.df_m5.iloc[i]

            # --- Manage open trade ---
            if open_trade is not None:
                open_trade = self._check_exit(open_trade, current_bar, i)
                if open_trade.outcome != "open":
                    self.trades.append(open_trade)
                    self.balance += open_trade.pnl
                    open_trade = None
                self.equity.append(self.balance)
                continue

            # --- Look for new signal ---
            if len(h1_slice) < 60 or len(m15_slice) < 25:
                self.equity.append(self.balance)
                continue

            self._engine.balance = self.balance
            signal = self._engine.evaluate(h1_slice, m15_slice, m5_slice)

            if signal is not None:
                open_trade = BacktestTrade(
                    direction=signal.direction,
                    entry=signal.entry,
                    sl=signal.sl,
                    tp=signal.tp,
                    lot=signal.lot,
                    entry_index=i,
                )
                # Deduct commission on entry
                commission = self.balance * BACKTEST_COMMISSION_PCT
                self.balance -= commission

            self.equity.append(self.balance)

        # Close any remaining open trade at last price
        if open_trade is not None:
            last_price = self.df_m5["close"].iloc[-1]
            open_trade.exit_price = last_price
            open_trade.exit_index = len(self.df_m5) - 1
            open_trade.pnl        = self._calc_pnl(open_trade, last_price)
            open_trade.outcome    = "open"
            self.trades.append(open_trade)

        return self

    # ------------------------------------------------------------------
    # Exit Logic
    # ------------------------------------------------------------------

    def _check_exit(
        self, trade: BacktestTrade, bar: pd.Series, idx: int
    ) -> BacktestTrade:
        """Checks if SL or TP was hit on the current bar."""
        if trade.direction == "bullish":
            if bar["low"] <= trade.sl:
                trade.exit_price = trade.sl
                trade.outcome    = "loss"
                trade.exit_index = idx
                trade.pnl        = self._calc_pnl(trade, trade.sl)
            elif bar["high"] >= trade.tp:
                trade.exit_price = trade.tp
                trade.outcome    = "win"
                trade.exit_index = idx
                trade.pnl        = self._calc_pnl(trade, trade.tp)
        else:  # bearish
            if bar["high"] >= trade.sl:
                trade.exit_price = trade.sl
                trade.outcome    = "loss"
                trade.exit_index = idx
                trade.pnl        = self._calc_pnl(trade, trade.sl)
            elif bar["low"] <= trade.tp:
                trade.exit_price = trade.tp
                trade.outcome    = "win"
                trade.exit_index = idx
                trade.pnl        = self._calc_pnl(trade, trade.tp)
        return trade

    @staticmethod
    def _calc_pnl(trade: BacktestTrade, exit_price: float) -> float:
        """Calculates P&L in account currency (simplified for XAUUSD)."""
        pip_size  = 0.1
        pip_value = 1.0   # $1 per pip per 0.01 lot → $100 per pip per 1 lot
        pips = (exit_price - trade.entry) / pip_size
        if trade.direction == "bearish":
            pips = -pips
        return round(pips * pip_value * trade.lot, 2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _align_slice(df: pd.DataFrame, current_time) -> pd.DataFrame:
        """Returns all rows of df up to and including current_time."""
        return df[df.index <= current_time]

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def metrics(self) -> Dict:
        """Returns a summary of backtest performance."""
        closed = [t for t in self.trades if t.outcome in ("win", "loss")]
        if not closed:
            return {"message": "No closed trades."}

        wins   = [t for t in closed if t.outcome == "win"]
        losses = [t for t in closed if t.outcome == "loss"]
        pnls   = [t.pnl for t in closed]
        equity = np.array(self.equity)

        # Max drawdown
        peak     = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_dd   = drawdown.max()

        # Profit factor
        gross_profit = sum(t.pnl for t in wins)
        gross_loss   = abs(sum(t.pnl for t in losses))
        pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

        return {
            "initial_balance":  BACKTEST_INITIAL_BALANCE,
            "final_balance":    round(self.balance, 2),
            "net_pnl":          round(sum(pnls), 2),
            "total_trades":     len(closed),
            "wins":             len(wins),
            "losses":           len(losses),
            "win_rate":         round(len(wins) / len(closed) * 100, 1),
            "profit_factor":    pf,
            "max_drawdown_pct": round(max_dd * 100, 2),
            "avg_rr":           round(np.mean([abs(t.pnl / ((t.entry - t.sl) or 1)) for t in closed]), 2),
        }

    def trade_log(self) -> pd.DataFrame:
        """Returns all trades as a DataFrame."""
        if not self.trades:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "direction":   t.direction,
                "entry":       t.entry,
                "sl":          t.sl,
                "tp":          t.tp,
                "lot":         t.lot,
                "exit_price":  t.exit_price,
                "pnl":         t.pnl,
                "outcome":     t.outcome,
                "entry_bar":   t.entry_index,
                "exit_bar":    t.exit_index,
            }
            for t in self.trades
        ])

    def equity_curve(self) -> pd.Series:
        """Returns the equity curve as a pandas Series."""
        return pd.Series(self.equity, name="equity")
