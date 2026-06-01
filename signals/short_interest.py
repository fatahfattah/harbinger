import io
import contextlib
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from .store import get as store_get, set as store_set, TTL_12H

_SI_WORKERS = 8


def fetch(tickers, config=None):
    if not tickers:
        return []
    workers = getattr(config, "SHORT_INTEREST_WORKERS", _SI_WORKERS)
    max_pct = getattr(config, "SHORT_PCT_MAX", 1.0)
    scale = getattr(config, "SHORT_PCT_SCALE", 8.0)

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_score_one, t, max_pct, scale): t for t in tickers}
        for f in as_completed(futures):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception:
                continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _score_one(ticker, max_pct, scale):
    cached = store_get("short_interest", ticker)
    if cached:
        return cached

    try:
        tk = yf.Ticker(ticker)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            info = tk.info
    except Exception:
        return None

    short_pct = info.get("shortPercentOfFloat")
    short_ratio = info.get("shortRatio")
    shares_short = info.get("sharesShort")
    shares_prior = info.get("sharesShortPriorMonth")

    if short_pct is None and short_ratio is None:
        return None

    score = 0.0
    details = {}

    if short_pct is not None:
        capped = min(short_pct, max_pct)
        score += capped * scale
        details["short_pct"] = round(capped * 100, 1)

    if short_ratio is not None and short_ratio > 1:
        score += min((short_ratio - 1) * 0.5, 2)
        details["short_ratio"] = round(short_ratio, 1)

    if shares_short and shares_prior and shares_prior > 0:
        change = (shares_short - shares_prior) / shares_prior
        if change > 0.1:
            score += min(change * 3, 2)
            details["short_change"] = f"+{change*100:.0f}%"
        details["shares_short"] = shares_short

    if score == 0:
        return None

    score = min(score, 10)
    details["short_pct"] = details.get("short_pct", 0)
    details["short_ratio"] = details.get("short_ratio", 0)

    result = {
        "ticker": ticker,
        "score": round(score, 2),
        "short_pct": details.get("short_pct", 0),
        "short_ratio": details.get("short_ratio", 0),
        "short_change": details.get("short_change", ""),
    }
    store_set("short_interest", ticker, result, TTL_12H)
    return result
