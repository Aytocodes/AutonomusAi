# =============================================================================
# execution_engine.py — ExecutionEngine
# Handles all trade execution via MetaTrader 5 API.
# Includes spread filtering, slippage control, and duplicate trade prevention.
# =============================================================================

from config import (
    SYMBOL, MAGIC_NUMBER, TRADE_COMMENT,
    MAX_SPREAD_PIPS, SLIPPAGE_PIPS,
)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


class ExecutionEngine:
    """
    Wraps MetaTrader 5 order operations.

    Responsibilities:
      - Spread check before entry
      - Send market orders with SL/TP
      - Prevent duplicate trades on the same symbol
      - Close open positions
    """

    def __init__(self, symbol: str = SYMBOL, live: bool = False):
        self.symbol     = symbol
        self.live       = live

    # ------------------------------------------------------------------
    # Spread Guard
    # ------------------------------------------------------------------

    def _spread_ok(self) -> bool:
        """Returns False if current spread exceeds MAX_SPREAD_PIPS."""
        if not self.live or not MT5_AVAILABLE:
            return True
        tick = mt5.symbol_info_tick(self.symbol)
        info = mt5.symbol_info(self.symbol)
        if tick is None or info is None:
            return False
        
        # Asset-specific pip definitions
        if "XAU" in self.symbol or "XAG" in self.symbol: # Metals
            pip_size = 0.1 # 1 pip = 0.10c movement
        elif info.digits in (3, 5): # Standard 5-digit Forex
            pip_size = info.point * 10
        else: # Indices/Crypto
            pip_size = info.point
            
        spread_pips = (tick.ask - tick.bid) / pip_size
        if spread_pips > MAX_SPREAD_PIPS:
            print(f"[Execution] {self.symbol} Spread too high: {spread_pips:.1f} pips (Limit: {MAX_SPREAD_PIPS})")
            return False
        return True

    # ------------------------------------------------------------------
    # Duplicate Trade Guard
    # ------------------------------------------------------------------

    def has_open_trade(self) -> bool:
        """Returns True if there is already an open position for this symbol."""
        if not self.live or not MT5_AVAILABLE:
            return False
        positions = mt5.positions_get(symbol=self.symbol)
        return positions is not None and len(positions) > 0

    # ------------------------------------------------------------------
    # Order Placement
    # ------------------------------------------------------------------

    def place_order(
        self,
        direction: str,
        lot: float,
        sl: float,
        tp: float,
    ) -> dict:
        """
        Places a market order.

        Parameters
        ----------
        direction : 'bullish' (buy) or 'bearish' (sell)
        lot       : position size in lots
        sl        : stop loss price
        tp        : take profit price

        Returns a result dict with keys: success, ticket, message.
        """
        if not self.live:
            # Backtest / paper mode — simulate fill
            return {"success": True, "ticket": -1, "message": "paper_trade"}

        if not MT5_AVAILABLE:
            return {"success": False, "ticket": None, "message": "MT5 not installed"}

        if self.has_open_trade():
            return {"success": False, "ticket": None, "message": "duplicate_trade"}

        if not self._spread_ok():
            return {"success": False, "ticket": None, "message": "spread_too_high"}

        tick      = mt5.symbol_info_tick(self.symbol)
        order_type = mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL
        price      = tick.ask if direction == "bullish" else tick.bid
        deviation  = int(SLIPPAGE_PIPS * 10)   # MT5 uses points

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       self.symbol,
            "volume":       lot,
            "type":         order_type,
            "price":        price,
            "sl":           sl,
            "tp":           tp,
            "deviation":    deviation,
            "magic":        MAGIC_NUMBER,
            "comment":      TRADE_COMMENT,
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)

        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[Execution] Order placed — ticket: {result.order}, "
                  f"direction: {direction}, lot: {lot}, SL: {sl}, TP: {tp}")
            return {"success": True, "ticket": result.order, "message": "ok"}

        print(f"[Execution] Order failed — retcode: {result.retcode}, comment: {result.comment}")
        return {"success": False, "ticket": None, "message": result.comment}

    # ------------------------------------------------------------------
    # Position Management
    # ------------------------------------------------------------------

    def close_all(self) -> bool:
        """Closes all open positions for this symbol."""
        if not self.live or not MT5_AVAILABLE:
            return True

        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return True

        for pos in positions:
            tick      = mt5.symbol_info_tick(self.symbol)
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price      = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

            request = {
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       self.symbol,
                "volume":       pos.volume,
                "type":         close_type,
                "position":     pos.ticket,
                "price":        price,
                "deviation":    30,
                "magic":        MAGIC_NUMBER,
                "comment":      "close",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            mt5.order_send(request)

        return True

    def get_open_positions(self) -> list:
        """Returns list of open position dicts for this symbol."""
        if not self.live or not MT5_AVAILABLE:
            return []
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return []
        return [
            {
                "ticket":    p.ticket,
                "direction": "bullish" if p.type == 0 else "bearish",
                "volume":    p.volume,
                "open_price": p.price_open,
                "sl":        p.sl,
                "tp":        p.tp,
                "profit":    p.profit,
            }
            for p in positions
        ]
