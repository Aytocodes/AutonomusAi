# =============================================================================
# trade_manager.py -- Smart Trade Manager (8 Improvements)
#
# 1. Drawdown Circuit Breaker  -- stops trading if daily loss > 5%
# 2. Trailing Stop Loss        -- moves SL to breakeven at 1.5R profit
# 3. Losing Streak Protection  -- drops risk to 1% after 3 consecutive losses
# 4. Partial Take Profit       -- takes 50% at 1.5R, lets rest run
# 5. Session Risk Control      -- higher risk during London/NY overlap
# 6. Symbol Performance Track  -- auto-pauses symbols below 30% WR
# 7. Remove USOILm             -- confirmed losing symbol
# 8. Keep only proven symbols  -- XAUUSDm, US30m, XAGUSDm, EURUSDm
# =============================================================================

from datetime import datetime, timezone, time
from typing   import Optional
import pytz

NY_TZ  = pytz.timezone("America/New_York")
UTC_TZ = pytz.utc

# Proven symbols only
APPROVED_SYMBOLS = ["XAUUSDm", "US30m", "XAGUSDm", "EURUSDm"]

# Session risk multipliers
SESSION_RISK = {
    "london_ny_overlap": 1.0,   # 13:00-17:00 UTC -- full risk
    "ny_open":           0.8,   # 12:00-13:00 UTC -- 80% risk
    "london":            0.7,   # 07:00-12:00 UTC -- 70% risk
    "asian":             0.5,   # 00:00-07:00 UTC -- 50% risk
    "dead":              0.0,   # weekend/closed  -- no trading
}


class TradeManager:
    """
    Wraps the strategy engines with smart risk management.
    Tracks performance per symbol and applies all 8 improvements.
    """

    def __init__(self, base_risk: float = 0.03, initial_balance: float = 10_000.0):
        self.base_risk       = base_risk
        self.balance         = initial_balance
        self.daily_start_bal = initial_balance

        # Per-symbol performance tracking
        self._symbol_stats: dict = {}   # sym -> {wins, losses, consecutive_losses}
        self._daily_loss_pct     = 0.0
        self._circuit_broken     = False
        self._open_trades: dict  = {}   # sym -> trade dict with partial TP tracking

    # ------------------------------------------------------------------
    # 1. Circuit Breaker
    # ------------------------------------------------------------------

    def check_circuit_breaker(self) -> bool:
        """Returns True if trading should be halted for the day."""
        loss_pct = (self.daily_start_bal - self.balance) / self.daily_start_bal
        if loss_pct >= 0.05:   # 5% daily loss limit
            self._circuit_broken = True
        return self._circuit_broken

    def reset_daily(self):
        """Call at start of each trading day."""
        self.daily_start_bal = self.balance
        self._circuit_broken = False

    # ------------------------------------------------------------------
    # 2. Trailing Stop Loss
    # ------------------------------------------------------------------

    def update_trailing_sl(self, trade: dict, current_price: float) -> dict:
        """
        Moves SL to breakeven once trade reaches 1.5R profit.
        Returns updated trade dict.
        """
        entry = trade["entry"]
        sl    = trade["sl"]
        tp    = trade["tp"]
        risk  = abs(entry - sl)

        if risk == 0:
            return trade

        profit_r = abs(current_price - entry) / risk

        if profit_r >= 1.5 and not trade.get("be_moved", False):
            # Move SL to breakeven + small buffer
            buf = risk * 0.1
            if trade["direction"] == "bullish":
                trade["sl"]      = round(entry + buf, 5)
            else:
                trade["sl"]      = round(entry - buf, 5)
            trade["be_moved"] = True

        return trade

    # ------------------------------------------------------------------
    # 3. Losing Streak Protection
    # ------------------------------------------------------------------

    def get_current_risk(self, symbol: str) -> float:
        """
        Returns adjusted risk based on consecutive losses.
        After 3 losses in a row -> drop to 1% until a win.
        """
        stats = self._symbol_stats.get(symbol, {"consecutive_losses": 0})
        if stats["consecutive_losses"] >= 3:
            return 0.01   # 1% risk during losing streak
        return self.base_risk

    # ------------------------------------------------------------------
    # 4. Partial Take Profit
    # ------------------------------------------------------------------

    def check_partial_tp(self, trade: dict, current_price: float) -> Optional[float]:
        """
        Returns partial close price if trade hits 1.5R and partial
        TP hasn't been taken yet. Returns None otherwise.
        """
        if trade.get("partial_taken", False):
            return None

        entry  = trade["entry"]
        sl     = trade["sl"]
        risk   = abs(entry - sl)
        if risk == 0:
            return None

        profit_r = abs(current_price - entry) / risk
        direction = trade["direction"]

        if profit_r >= 1.5:
            if direction == "bullish" and current_price > entry:
                return current_price
            if direction == "bearish" and current_price < entry:
                return current_price
        return None

    # ------------------------------------------------------------------
    # 5. Session Risk Multiplier
    # ------------------------------------------------------------------

    def get_session_multiplier(self) -> float:
        """Returns risk multiplier based on current trading session."""
        now_utc  = datetime.now(UTC_TZ)
        wday     = now_utc.weekday()
        hour_utc = now_utc.hour

        # Weekend
        if wday == 5 or (wday == 6 and hour_utc < 22):
            return SESSION_RISK["dead"]

        # London/NY overlap: 13:00-17:00 UTC
        if 13 <= hour_utc < 17:
            return SESSION_RISK["london_ny_overlap"]
        # NY open: 12:00-13:00 UTC
        if 12 <= hour_utc < 13:
            return SESSION_RISK["ny_open"]
        # London: 07:00-12:00 UTC
        if 7 <= hour_utc < 12:
            return SESSION_RISK["london"]
        # Asian: 00:00-07:00 UTC
        return SESSION_RISK["asian"]

    # ------------------------------------------------------------------
    # 6. Symbol Performance Tracker
    # ------------------------------------------------------------------

    def record_trade_result(self, symbol: str, result: str):
        """Call after each trade closes with result='WIN' or 'LOSS'."""
        if symbol not in self._symbol_stats:
            self._symbol_stats[symbol] = {"wins": 0, "losses": 0,
                                           "consecutive_losses": 0, "paused": False}
        s = self._symbol_stats[symbol]

        if result == "WIN":
            s["wins"]               += 1
            s["consecutive_losses"]  = 0
        else:
            s["losses"]             += 1
            s["consecutive_losses"] += 1
            self.balance            -= 0   # balance updated externally

        # Auto-pause if win rate drops below 30% after 10+ trades
        total = s["wins"] + s["losses"]
        if total >= 10:
            wr = s["wins"] / total
            s["paused"] = wr < 0.30

    def is_symbol_paused(self, symbol: str) -> bool:
        """Returns True if symbol is auto-paused due to poor performance."""
        # Always block removed symbols
        if symbol not in APPROVED_SYMBOLS:
            return True
        return self._symbol_stats.get(symbol, {}).get("paused", False)

    def get_symbol_stats(self, symbol: str) -> dict:
        return self._symbol_stats.get(symbol, {"wins": 0, "losses": 0,
                                                "consecutive_losses": 0})

    # ------------------------------------------------------------------
    # Combined Risk Calculation
    # ------------------------------------------------------------------

    def calculate_risk(self, symbol: str) -> float:
        """
        Returns final risk % combining all adjustments:
        base_risk * session_multiplier * streak_adjustment
        """
        if self.check_circuit_breaker():
            return 0.0
        if self.is_symbol_paused(symbol):
            return 0.0

        streak_risk  = self.get_current_risk(symbol)
        session_mult = self.get_session_multiplier()
        return round(streak_risk * session_mult, 4)
