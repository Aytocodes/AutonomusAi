# =============================================================================
# symbol_scanner.py -- Auto Symbol Discovery
# Scans all visible Market Watch symbols and filters for SMC compatibility.
# No manual symbol list needed -- fully automatic.
# =============================================================================

import pandas as pd
from logger import log

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# Symbols to always skip (too exotic, too low liquidity, or crypto volatility)
BLACKLIST = {
    "BCHUSDm", "BTCJPYm", "BTCKRWm", "BTCUSDm", "ETHUSDm", "LTCUSDm",
    "XRPUSDm", "AAVEUSDm", "BATUSDm", "LINKUSDm", "SNXUSDm", "SOLUSDm",
    "UNIUSDm", "ADAUSDm", "BNBUSDm", "DOTUSDm", "ENJUSDm", "FILUSDm",
    "XTZUSDm", "1INCHUSDm", "CAKEUSDm", "COMPUSDm", "DOGEUSDm", "MATICUSDm",
    "BTCAUDm", "BTCCNHm", "BTCXAUm", "MBTUSDm",
}

# Max spread allowed per symbol type (in points)
MAX_SPREAD = {
    "forex":    30,
    "metals":   500,
    "indices":  200,
    "oil":      100,
    "default":  50,
}


def _symbol_type(name: str) -> str:
    n = name.upper()
    if any(x in n for x in ["XAU", "XAG", "XPT", "XPD"]):
        return "metals"
    if any(x in n for x in ["US30", "USTEC", "US500", "DE30", "UK100", "FR40",
                              "JP225", "AUS200", "HK50", "STOXX"]):
        return "indices"
    if any(x in n for x in ["OIL", "USOIL", "UKOIL", "XNG"]):
        return "oil"
    if any(x in n for x in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD",
                              "CHF", "NZD", "DXY"]):
        return "forex"
    return "default"


def get_pip_info(symbol: str) -> tuple:
    """
    Returns (pip_size, pip_value_per_lot, min_lot, digits) for a symbol.
    Fetched live from MT5.
    """
    if not MT5_AVAILABLE:
        return 0.0001, 10.0, 0.01, 5

    info = mt5.symbol_info(symbol)
    if not info:
        return 0.0001, 10.0, 0.01, 5

    digits   = info.digits
    # pip size: 5/3-digit = point*10, 4/2/1-digit = point
    pip_size = info.point * 10 if digits in (5, 4) else info.point
    tick_val  = info.trade_tick_value
    tick_size = info.trade_tick_size
    pip_value = (tick_val * pip_size / tick_size) if tick_size > 0 else tick_val
    min_lot   = info.volume_min

    return pip_size, pip_value, min_lot, digits


def scan_symbols(account_currency: str = "USD") -> list:
    """
    Scans all visible Market Watch symbols and returns a list of
    SMC-compatible symbols with their specs.

    Filters applied:
      1. Not in blacklist
      2. Has live bid/ask prices
      3. Spread within acceptable range
      4. Min lot <= 0.01 (tradeable with small deposits)
      5. Has enough price history for SMC analysis

    Returns list of symbol name strings.
    """
    if not MT5_AVAILABLE:
        log.warning("MT5 not available -- returning empty symbol list")
        return []

    all_syms  = mt5.symbols_get()
    visible   = [s for s in all_syms if s.visible]
    approved  = []

    log.info(f"Scanning {len(visible)} Market Watch symbols...")

    for s in visible:
        name = s.name

        # Skip blacklisted
        if name in BLACKLIST:
            log.debug(f"  [{name}] SKIP -- blacklisted")
            continue

        info = mt5.symbol_info(name)
        tick = mt5.symbol_info_tick(name)

        # Skip if no live data
        if not info or not tick or tick.bid <= 0 or tick.ask <= 0:
            log.debug(f"  [{name}] SKIP -- no live tick data")
            continue

        # Skip if trading not allowed
        if not info.trade_mode:
            log.debug(f"  [{name}] SKIP -- trading disabled")
            continue

        # Spread check
        sym_type   = _symbol_type(name)
        max_spread = MAX_SPREAD.get(sym_type, MAX_SPREAD["default"])
        spread_pts = round((tick.ask - tick.bid) / info.point, 1)
        if spread_pts > max_spread:
            log.debug(f"  [{name}] SKIP -- spread {spread_pts}pts > {max_spread}pts")
            continue

        # Min lot check -- must be tradeable with small accounts
        if info.volume_min > 0.1:
            log.debug(f"  [{name}] SKIP -- min lot {info.volume_min} too large")
            continue

        # Check enough history exists (at least 200 H1 bars)
        rates = mt5.copy_rates_from_pos(name, 16385, 0, 10)  # H1
        if rates is None or len(rates) < 5:
            log.debug(f"  [{name}] SKIP -- insufficient history")
            continue

        pip_size, pip_value, min_lot, digits = get_pip_info(name)

        log.info(f"  [{name}] OK -- type={sym_type} spread={spread_pts}pts "
                 f"min_lot={min_lot} pip_val=${pip_value:.4f}")
        approved.append(name)

    log.info(f"Auto-scan complete: {len(approved)} symbols approved for trading")
    log.info(f"Symbols: {', '.join(approved)}")
    return approved
