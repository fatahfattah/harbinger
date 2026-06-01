import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from .store import get as store_get, set as store_set, TTL_24H

_INST_WORKERS = 8


def fetch(tickers, config):
    result = []
    with ThreadPoolExecutor(max_workers=_INST_WORKERS) as pool:
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
    cached = store_get("institutional", ticker)
    if cached:
        return cached

    stock = yf.Ticker(ticker)
    try:
        info = stock.info
    except Exception:
        return None
    if not info:
        return None

    inst_pct = info.get("heldPercentInstitutions")
    insiders_pct = info.get("heldPercentInsiders")

    holders_df = None
    try:
        holders_df = stock.institutional_holders
    except Exception:
        pass

    score = 0.0
    signals = []
    holder_count = 0
    avg_change = 0.0

    if holders_df is not None and not holders_df.empty:
        holder_count = len(holders_df)
        changes = pd.to_numeric(holders_df.get("pctChange", pd.Series(dtype=float)), errors="coerce").dropna()
        if len(changes) > 0:
            avg_change = float(changes.mean())

    if inst_pct is not None:
        if inst_pct >= 0.7:
            score += 4
            signals.append("high_inst_own")
        elif inst_pct >= 0.5:
            score += 3
            signals.append("high_inst_own")
        elif inst_pct >= 0.3:
            score += 2
            signals.append("moderate_inst_own")
        elif inst_pct >= 0.1:
            score += 1
        else:
            score += 0.5
    else:
        signals.append("no_inst_data")

    if holder_count > 0:
        if holder_count >= 500:
            score += 2
            signals.append("broad_inst_base")
        elif holder_count >= 200:
            score += 1.5
            signals.append("broad_inst_base")
        elif holder_count >= 50:
            score += 1
        elif holder_count >= 10:
            score += 0.5

    if avg_change > 0.05:
        score += 3
        signals.append("inst_accumulation")
    elif avg_change > 0.01:
        score += 2
    elif avg_change > 0:
        score += 1
    elif avg_change < -0.01:
        signals.append("inst_distribution")

    if insiders_pct is not None and insiders_pct > 0.1 and inst_pct is not None and inst_pct > 0.3:
        score += 1
        signals.append("aligned_ownership")

    score = min(round(score, 1), 10)

    entry = {
        "ticker": ticker,
        "score": score,
        "inst_pct": round(inst_pct, 4) if inst_pct is not None else None,
        "insider_pct": round(insiders_pct, 4) if insiders_pct is not None else None,
        "holder_count": holder_count if holder_count > 0 else None,
        "avg_change": round(avg_change, 4) if holder_count > 0 else None,
        "signals": signals,
    }
    store_set("institutional", ticker, entry, TTL_24H)
    return entry
