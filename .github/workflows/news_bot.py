BASE_URL=https://autonomus.ai
# =============================================================================
# news_bot.py -- A2_NewsBot Engine
# Tier-based news trading with deviation logic and dynamic strategy selection.
# =============================================================================

import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from logger import log
from config import NEWS_TIERS, NEWS_THRESHOLDS, NEWS_RISK, NEWS_STALL_MINUTES, NEWS_FOMC_WAIT_MINUTES
from risk_manager import RiskManager

class A2_NewsBot:
    """
    Advanced News Trading Engine (A2_NewsBot).
    Classifies events, computes deviations, and selects Trend vs Fade strategies.
    """
    def __init__(self, symbol: str, balance: float):
        self.symbol = symbol
        self.balance = balance
        self.rm = RiskManager()
        
    def get_event_tier(self, event_name: str) -> int:
        if any(e in event_name for e in NEWS_TIERS["TIER_1"]): return 1
        if any(e in event_name for e in NEWS_TIERS["TIER_2"]): return 2
        if any(e in event_name for e in NEWS_TIERS["TIER_3"]): return 3
        return 0

    def evaluate_news_setup(self, event_data: Dict, df_m1: pd.DataFrame) -> Optional[dict]:
        """
        Determines if a news trade is valid based on deviation and tier.
        event_data: { 'name': str, 'actual': float, 'forecast': float, 'time': datetime }
        """
        if not event_data or df_m1.empty:
            return None

        event_name = event_data['name']
        tier = self.get_event_tier(event_name)
        if tier == 0: return None

        # 1. Compute Deviation
        actual = event_data['actual']
        forecast = event_data['forecast']
        deviation = actual - forecast
        abs_dev = abs(deviation)

        # 2. Threshold Logic
        threshold = self._get_threshold(event_name)
        
        # 3. Decision Engine
        strategy = None
        direction = "bullish" if deviation > 0 else "bearish"
        
        # Specific Event: FOMC
        if "FOMC" in event_name:
            time_since_release = (datetime.now(timezone.utc) - event_data['time']).total_seconds() / 60
            if time_since_release < NEWS_FOMC_WAIT_MINUTES:
                log.info(f"[NewsBot] FOMC Detected. Waiting for Powell speech confirmation...")
                return None
            # Post-Powell Trend logic
            strategy = "TREND"
        
        elif tier == 1:
            if abs_dev >= threshold:
                strategy = "TREND"
            else:
                strategy = "FADE"
                
        elif tier == 2:
            if abs_dev >= threshold:
                strategy = "TREND"
            else:
                log.info(f"[NewsBot] Tier 2 deviation ({abs_dev}) below threshold ({threshold}). No trade.")
                return None
                
        elif tier == 3:
            if abs_dev >= threshold * 2: # Must be extreme for Tier 3
                strategy = "TREND"
            else:
                return None

        if not strategy: return None

        # 4. Strategy Execution logic
        return self._process_strategy(strategy, direction, tier, event_name, abs_dev, df_m1)

    def _get_threshold(self, event_name: str) -> float:
        for key in NEWS_THRESHOLDS:
            if key in event_name: return NEWS_THRESHOLDS[key]
        return NEWS_THRESHOLDS["Default"]

    def _process_strategy(self, strategy: str, direction: str, tier: int, 
                          event: str, dev: float, df_m1: pd.DataFrame) -> Optional[dict]:
        
        last_close = df_m1['close'].iloc[-1]
        risk_pct = NEWS_RISK.get(f"TIER_{tier}", 0.01)
        
        # Entry Logic: TREND
        if strategy == "TREND":
            # Wait for 1-minute confirmation (check if last candle is impulsive)
            m1_candle = df_m1.iloc[-1]
            is_confirmed = (m1_candle['close'] > m1_candle['open']) if direction == "bullish" else (m1_candle['close'] < m1_candle['open'])
            
            if not is_confirmed:
                log.debug(f"[NewsBot] Trend setup waiting for M1 confirmation.")
                return None

            # Setup SL/TP
            atr = (df_m1['high'] - df_m1['low']).rolling(14).mean().iloc[-1]
            sl_dist = atr * 2.5 # News needs wider stops
            sl = last_close - sl_dist if direction == "bullish" else last_close + sl_dist
            tp = last_close + (sl_dist * 1.5) if direction == "bullish" else last_close - (sl_dist * 1.5)
            
            return self._build_news_signal(direction, last_close, sl, tp, risk_pct, strategy, event, tier, dev)

        # Entry Logic: FADE
        if strategy == "FADE":
            # Only trade if we've seen rejection (long wick)
            m1_candle = df_m1.iloc[-1]
            wick_size = (m1_candle['high'] - m1_candle['close']) if direction == "bullish" else (m1_candle['close'] - m1_candle['low'])
            body_size = abs(m1_candle['close'] - m1_candle['open'])
            
            if wick_size < body_size:
                log.debug(f"[NewsBot] FADE waiting for rejection wick.")
                return None
                
            # Inverse direction for FADE
            fade_direction = "bearish" if direction == "bullish" else "bullish"
            sl = m1_candle['high'] if fade_direction == "bearish" else m1_candle['low']
            tp = last_close + (abs(last_close - sl) * 2.0) if fade_direction == "bullish" else last_close - (abs(last_close - sl) * 2.0)
            
            return self._build_news_signal(fade_direction, last_close, sl, tp, risk_pct, strategy, event, tier, dev)

        return None

    def _build_news_signal(self, direction, entry, sl, tp, risk, strategy, event, tier, dev):
        lot = self.rm.lot_size(self.balance, entry, sl, symbol=self.symbol)
        
        # Safety check: Low balance handling
        if lot <= 0:
            log.warning(f"[NewsBot] Trade skipped: Insufficient margin/balance for {self.symbol}")
            return None

        reason = f"A2_NewsBot {strategy} | {event} (Tier {tier}) | Deviation: {dev:.2f}"
        
        return {
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lot": lot,
            "reason": reason,
            "tier": tier,
            "event": event
        }

class NewsFetcher:
    """
    Fetches high-impact economic events from Forex Factory RSS.
    Returns active event if one fired within the last 10 minutes.
    """
    _cache: Optional[dict] = None
    _cache_time: float = 0
    CACHE_TTL = 300  # refresh every 5 minutes

    @staticmethod
    def get_active_event() -> Optional[dict]:
        import time, urllib.request, xml.etree.ElementTree as ET
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)

        # Use cache to avoid hammering the API
        if NewsFetcher._cache_time and (time.time() - NewsFetcher._cache_time) < NewsFetcher.CACHE_TTL:
            return NewsFetcher._cache

        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                import json
                events = json.loads(r.read().decode())

            for ev in events:
                # Only high impact
                if ev.get("impact") not in ("High", "Medium"):
                    continue
                try:
                    ev_time = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
                except Exception:
                    continue

                # Active if fired within last 10 minutes
                diff = (now - ev_time).total_seconds() / 60
                if 0 <= diff <= 10:
                    actual   = ev.get("actual",   "")
                    forecast = ev.get("forecast", "")
                    try:
                        actual_f   = float(str(actual).replace("%","").replace("K","000").replace("M","000000"))
                        forecast_f = float(str(forecast).replace("%","").replace("K","000").replace("M","000000"))
                    except Exception:
                        continue

                    result = {
                        "name":     ev.get("title", ""),
                        "actual":   actual_f,
                        "forecast": forecast_f,
                        "time":     ev_time,
                        "impact":   ev.get("impact", ""),
                        "currency": ev.get("country", ""),
                    }
                    NewsFetcher._cache      = result
                    NewsFetcher._cache_time = time.time()
                    return result

        except Exception as e:
            log.debug(f"[NewsFetcher] Could not fetch calendar: {e}")

        NewsFetcher._cache      = None
        NewsFetcher._cache_time = time.time()
        return None

    @staticmethod
    def log_to_website(trade_data: dict):
        log.info(f"[DASHBOARD] Posting News Trade: {trade_data['event']} | Result: Pending")