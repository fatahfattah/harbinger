import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from .store import get as store_get, set as store_set, TTL_24H

_HEALTH_WORKERS = 8


def fetch(tickers, config):
    result = []
    with ThreadPoolExecutor(max_workers=_HEALTH_WORKERS) as pool:
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
    cached = store_get("financial_health", ticker)
    if cached:
        return cached

    stock = yf.Ticker(ticker)
    try:
        info = stock.info
    except Exception:
        return None
    if not info:
        return None

    de = info.get("debtToEquity")
    cr = info.get("currentRatio")
    qr = info.get("quickRatio")
    pm = info.get("profitMargins")
    om = info.get("operatingMargins")
    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    fcf = info.get("freeCashflow")
    ocf = info.get("operatingCashflow")
    total_debt = info.get("totalDebt")
    total_cash = info.get("totalCash")

    score = 0.0
    signals = []

    if de is not None and de > 0:
        if de < 0.3:
            score += 3
            signals.append("low_debt")
        elif de < 0.7:
            score += 2.5
            signals.append("moderate_debt")
        elif de < 1.5:
            score += 1.5
        elif de < 3:
            score += 0.5
            signals.append("high_debt")
        else:
            signals.append("very_high_debt")
    elif de is not None and de <= 0:
        score += 2
        signals.append("neg_equity")

    if cr is not None:
        if cr > 3:
            score += 2
        elif cr > 2:
            score += 1.5
            signals.append("strong_liquidity")
        elif cr > 1.5:
            score += 1
        elif cr > 1:
            score += 0.5
        else:
            signals.append("low_liquidity")

    if qr is not None and qr < 0.5:
        signals.append("low_quick_ratio")

    if pm is not None:
        if pm > 0.15:
            score += 2
            signals.append("high_margin")
        elif pm > 0.05:
            score += 1.5
        elif pm > 0:
            score += 0.5
        else:
            signals.append("unprofitable")

    if roe is not None and roe > 0:
        if roe > 0.2:
            score += 1.5
            signals.append("high_roe")
        elif roe > 0.1:
            score += 1
        elif roe > 0.05:
            score += 0.5

    if roa is not None and roa > 0:
        if roa > 0.1:
            score += 0.5

    if fcf is not None and fcf > 0:
        score += 0.5
        signals.append("pos_fcf")
    elif fcf is not None:
        signals.append("neg_fcf")

    if ocf is not None and ocf < 0:
        signals.append("neg_ocf")

    score = min(round(score, 1), 10)

    entry = {
        "ticker": ticker,
        "score": score,
        "debt_to_equity": round(de, 2) if de is not None else None,
        "current_ratio": round(cr, 2) if cr is not None else None,
        "quick_ratio": round(qr, 2) if qr is not None else None,
        "profit_margin": round(pm, 4) if pm is not None else None,
        "return_on_equity": round(roe, 4) if roe is not None else None,
        "return_on_assets": round(roa, 4) if roa is not None else None,
        "free_cashflow": fcf,
        "operating_cashflow": ocf,
        "total_debt": total_debt,
        "total_cash": total_cash,
        "signals": signals,
    }
    store_set("financial_health", ticker, entry, TTL_24H)
    return entry
