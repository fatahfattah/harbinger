import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from .store import get as store_get, set as store_set, TTL_24H

_DIV_WORKERS = 8


def fetch(tickers, config):
    result = []
    with ThreadPoolExecutor(max_workers=_DIV_WORKERS) as pool:
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
    cached = store_get("dividend_quality", ticker)
    if cached:
        return cached

    stock = yf.Ticker(ticker)
    try:
        info = stock.info
    except Exception:
        return None
    if not info:
        return None

    div_yield = info.get("dividendYield")
    payout = info.get("payoutRatio")
    five_yr_div = info.get("fiveYearAvgDividendYield")
    beta = info.get("beta")
    gm = info.get("grossMargins")
    om = info.get("operatingMargins")
    roe = info.get("returnOnEquity")
    roa = info.get("returnOnAssets")
    bv = info.get("bookValue")
    fcf = info.get("freeCashflow")
    ocf = info.get("operatingCashflow")

    score = 0.0
    signals = []

    if div_yield is not None and div_yield > 0:
        if div_yield > 0.04:
            score += 3
            signals.append("high_yield")
        elif div_yield > 0.02:
            score += 2
            signals.append("div_payer")
        elif div_yield > 0.005:
            score += 1
            signals.append("div_payer")
        else:
            score += 0.5
        if payout is not None and 0 < payout < 0.8:
            score += 1
            signals.append("sustainable_payout")
        elif payout is not None and payout >= 0.8:
            signals.append("high_payout")
        if five_yr_div is not None and five_yr_div > 0:
            if div_yield >= five_yr_div * 0.8:
                score += 1
                signals.append("stable_div")
    else:
        signals.append("no_dividend")

    if gm is not None:
        if gm > 0.5:
            score += 2
            signals.append("high_gross_margin")
        elif gm > 0.3:
            score += 1.5
        elif gm > 0.1:
            score += 0.5
        else:
            signals.append("low_margin")

    if om is not None and om > 0.15:
        score += 1
        signals.append("high_op_margin")
    elif om is not None and om <= 0:
        signals.append("neg_op_margin")

    if roe is not None and roe > 0.15:
        score += 1
        signals.append("high_roe_quality")

    if roa is not None and roa > 0.05:
        score += 0.5

    if bv is not None and bv > 0:
        score += 0.5

    if fcf is not None and fcf > 0:
        score += 0.5
        signals.append("pos_fcf_quality")
    elif fcf is not None:
        signals.append("neg_fcf_quality")

    if ocf is not None and ocf < 0:
        signals.append("neg_ocf_quality")

    if beta is not None:
        if beta < 0.8:
            score += 0.5
            signals.append("low_beta")
        elif beta > 2:
            signals.append("high_beta")

    score = min(round(score, 1), 10)

    entry = {
        "ticker": ticker,
        "score": score,
        "dividend_yield": round(div_yield * 100, 2) if div_yield is not None else None,
        "payout_ratio": round(payout, 4) if payout is not None else None,
        "beta": round(beta, 2) if beta is not None else None,
        "gross_margin": round(gm, 4) if gm is not None else None,
        "operating_margin": round(om, 4) if om is not None else None,
        "return_on_equity": round(roe, 4) if roe is not None else None,
        "book_value": round(bv, 2) if bv is not None else None,
        "signals": signals,
    }
    store_set("dividend_quality", ticker, entry, TTL_24H)
    return entry
