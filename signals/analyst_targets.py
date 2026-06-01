import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from .store import get as store_get, set as store_set, TTL_24H

_ANALYST_WORKERS = 10


def fetch(tickers, config):
    result = []
    with ThreadPoolExecutor(max_workers=_ANALYST_WORKERS) as pool:
        futures = {pool.submit(_score_one, t): t for t in tickers}
        for f in as_completed(futures):
            try:
                r = f.result(timeout=25)
                if r:
                    result.append(r)
            except Exception:
                continue
    return result


def _score_one(ticker):
    cached = store_get("analyst", ticker)
    if cached:
        return cached

    stock = yf.Ticker(ticker)
    current_price = None
    try:
        current_price = stock.fast_info.last_price
    except Exception:
        pass
    if not current_price:
        try:
            hist = stock.history(period="5d")
            if not hist.empty:
                current_price = hist["Close"].iloc[-1]
        except Exception:
            pass

    targets = getattr(stock, "analyst_price_targets", None)
    target = None
    if isinstance(targets, dict):
        target = targets.get("mean") or targets.get("median") or targets.get("current")

    rec_summary = getattr(stock, "recommendations_summary", None)
    upgrades = _fetch_upgrades(stock)

    score = 0.0
    signals = []
    pt_upside = None
    consensus = None
    total_recs = 0
    buy_pct = 0

    if rec_summary is not None and isinstance(rec_summary, pd.DataFrame) and not rec_summary.empty:
        latest = rec_summary.sort_index().iloc[-1]
        total_recs = int(latest.get("strongBuy", 0) + latest.get("buy", 0) + latest.get("hold", 0) + latest.get("sell", 0) + latest.get("strongSell", 0))
        sb = int(latest.get("strongBuy", 0))
        b = int(latest.get("buy", 0))
        h = int(latest.get("hold", 0))
        s = int(latest.get("sell", 0))
        ss = int(latest.get("strongSell", 0))

        if total_recs > 0:
            buy_pct = (sb + b) / total_recs

            if buy_pct > 0.6:
                score += 2.5
                signals.append("bullish_consensus")
            elif buy_pct > 0.4:
                score += 1.5
            elif buy_pct > 0.2:
                score += 0.5
            else:
                signals.append("bearish_consensus")

            if total_recs >= 10:
                score += 0.5
                signals.append("broad_coverage")
            elif total_recs >= 5:
                score += 0.25

            consensus = f"{sb}B/{b}B/{h}H/{s}S/{ss}SS"

    if target is not None and current_price is not None and current_price > 0:
        if isinstance(target, (int, float)):
            pt_upside = round((target / current_price - 1) * 100, 1)
            if pt_upside > 50:
                score += 2.5
                signals.append("high_upside")
            elif pt_upside > 25:
                score += 2
            elif pt_upside > 10:
                score += 1
            elif pt_upside > 0:
                score += 0.5
            else:
                signals.append("below_pt")

    if upgrades:
        up = upgrades.get("upgrades", 0)
        down = upgrades.get("downgrades", 0)
        net = up - down
        if net > 2:
            score += 1.5
            signals.append("positive_momentum")
        elif net > 0:
            score += 0.5
        elif net < -2:
            signals.append("negative_momentum")
            score -= 0.5

    if target and current_price and current_price > target and pt_upside and pt_upside < 0:
        signals.append("above_target")

    score = min(max(round(score, 1), 0), 10)

    entry = {
        "ticker": ticker,
        "score": score,
        "price_target": target,
        "current_price": current_price,
        "pt_upside_pct": pt_upside,
        "consensus": consensus,
        "total_analysts": total_recs,
        "buy_pct": round(buy_pct, 2) if total_recs > 0 else None,
        "upgrades_90d": upgrades.get("upgrades", 0) if upgrades else 0,
        "downgrades_90d": upgrades.get("downgrades", 0) if upgrades else 0,
        "signals": signals,
    }
    store_set("analyst", ticker, entry, TTL_24H)
    return entry


def _fetch_upgrades(stock):
    try:
        ud = stock.upgrades_downgrades
        if ud is None or ud.empty:
            return {"upgrades": 0, "downgrades": 0}
        if isinstance(ud.columns, pd.MultiIndex):
            ud.columns = ud.columns.get_level_values(0)
        col = [c for c in ud.columns if "grade" in c.lower() or "action" in c.lower()]
        if not col:
            return {"upgrades": 0, "downgrades": 0}
        action_col = col[0]
        now = pd.Timestamp.now()
        cutoff = now - pd.Timedelta(days=90)
        recent = ud[ud.index >= cutoff] if hasattr(ud.index, "min") else ud
        up = int((recent[action_col].str.lower().str.contains("up|init|buy", na=False)).sum())
        down = int((recent[action_col].str.lower().str.contains("down|sell|reduce", na=False)).sum())
        return {"upgrades": up, "downgrades": down}
    except Exception:
        return {"upgrades": 0, "downgrades": 0}
