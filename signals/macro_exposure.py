import yfinance as yf
import pandas as pd
from .store import get as store_get, set as store_set, TTL_24H

RATE_SENSITIVE_SECTORS = {
    "Financial Services", "Banks", "Insurance", "Real Estate", "REITs",
    "Utilities", "Independent Power", "Consumer Finance",
}

COMMODITY_SECTORS = {
    "Basic Materials", "Energy", "Oil & Gas", "Metals & Mining",
    "Chemicals", "Agriculture", "Forestry",
}

ASIA_KEYWORDS = ["japan", "asia", "china", "korea", "taiwan", "india",
                 "pacific", "singapore", "hong kong", "apac"]


def fetch(tickers, config):
    result = []
    for t in tickers:
        cached = store_get("macro_exposure", t)
        if cached:
            result.append(cached)
            continue
        try:
            stock = yf.Ticker(t)
            info = {}
            try:
                info = stock.info or {}
            except Exception:
                pass
            sector = info.get("sector", "")
            industry = info.get("industry", "")
            country = info.get("country", "")
            # FX risk: international revenue %
            intl_rev_pct = 0
            for key in ["revenueBreakdown", "revenue"]:
                val = info.get(key, {})
                if isinstance(val, dict):
                    for region_key in ["asia", "europe", "international", "restOfWorld",
                                       "japan", "china", "korea"]:
                        if region_key in val:
                            intl_rev_pct = max(intl_rev_pct, float(val[region_key]) if val[region_key] else 0)
                    if "total" in val:
                        us_rev = float(val.get("unitedStates", 0) or 0)
                        intl_rev_pct = max(intl_rev_pct, 100 - us_rev) if us_rev else intl_rev_pct
            fx_score = round(min(intl_rev_pct / 20, 3), 1)
            # Rate sensitivity score
            is_rate_sensitive = sector in RATE_SENSITIVE_SECTORS or any(
                kw in (sector + " " + industry).lower()
                for kw in ["bank", "insurance", "reit", "utility", "credit", "mortgage"]
            )
            rate_score = 3 if is_rate_sensitive else 0
            # Commodity sensitivity
            is_commodity = sector in COMMODITY_SECTORS or any(
                kw in (sector + " " + industry).lower()
                for kw in ["oil", "gas", "mining", "metal", "chemical", "agriculture", "commodity"]
            )
            commodity_score = 2 if is_commodity else 0
            # Asia/Japan exposure
            asia_exposure_score = 0
            if country and country.lower() in ["japan", "china", "taiwan", "south korea", "india"]:
                asia_exposure_score = 2
            elif info.get("address1", ""):
                loc = (info.get("city", "") + " " + info.get("state", "") + " " + country).lower()
                for kw in ASIA_KEYWORDS:
                    if kw in loc:
                        asia_exposure_score = 2
                        break
            if intl_rev_pct > 30 and asia_exposure_score < 1:
                asia_exposure_score = 1
            total = round(fx_score + rate_score + commodity_score + asia_exposure_score, 1)
            entry = {
                "ticker": t,
                "score": min(total, 10),
                "fx_score": fx_score,
                "rate_score": rate_score,
                "commodity_score": commodity_score,
                "asia_score": asia_exposure_score,
                "intl_rev_pct": round(intl_rev_pct, 0),
                "sector": sector,
                "signals": [],
            }
            signals = entry["signals"]
            if fx_score >= 2:
                signals.append("high_fx_risk")
            if rate_score >= 2:
                signals.append("rate_sensitive")
            if commodity_score >= 1:
                signals.append("commodity_sensitive")
            if asia_exposure_score >= 1:
                signals.append("asia_exposure")
            store_set("macro_exposure", t, entry, TTL_24H)
            result.append(entry)
        except Exception as e:
            import sys
            print(f"[macro_exposure] error for {t}: {e}", file=sys.stderr)
    return result
