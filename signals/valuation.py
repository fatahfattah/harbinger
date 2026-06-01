import os
import json
import re
import io
import time
import contextlib
import yfinance as yf
import pandas as pd
from multiprocessing import Process, Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from yfinance.exceptions import YFRateLimitError
from config import MCAP_MIN, MCAP_MAX, PRICE_MIN, FWD_PE_MAX, REV_GROWTH_MIN, DEAD_TICKER_TTL_DAYS
from .store import get as store_get, set as store_set, TTL_24H

BANNED_SUFFIXES = [".", "-", "+", "="]
MAX_DEEP_DIVE = 100
INFO_TIMEOUT = 20
_VAL_WORKERS = 8

_price_passed_cache = []
_last_prices = {}
_last_prices_ratelimited = False
_global_rate_limited = False
_dead_cache_path = os.path.join(os.path.dirname(__file__), "..", "runs", "dead_tickers.json")


def _load_dead():
    try:
        if os.path.exists(_dead_cache_path):
            with open(_dead_cache_path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                now = time.time()
                cutoff = now - DEAD_TICKER_TTL_DAYS * 86400
                return {t for t, ts in data.items() if ts > cutoff}
            return set(data)
    except Exception:
        pass
    return set()


def _save_dead(dead):
    try:
        os.makedirs(os.path.dirname(_dead_cache_path), exist_ok=True)
        existing = {}
        if os.path.exists(_dead_cache_path):
            try:
                with open(_dead_cache_path) as f:
                    old = json.load(f)
                if isinstance(old, dict):
                    existing = old
                else:
                    existing = {t: time.time() for t in old}
            except Exception:
                pass
        now = time.time()
        for t in dead:
            existing[t] = now
        with open(_dead_cache_path, "w") as f:
            json.dump(existing, f)
    except Exception:
        pass


def last_price_passed():
    return _price_passed_cache


def batch_price_filter(tickers):
    global _price_passed_cache
    dead = _load_dead()

    filtered = [t for t in tickers if t not in dead and not any(suf in t for suf in BANNED_SUFFIXES)]
    if not filtered:
        _price_passed_cache = []
        _save_dead(dead)
        return []

    prices = _batch_prices(filtered)
    above = []
    rate_limited = any(p == PRICE_MIN + 1 for p in prices.values())
    for t in filtered:
        p = prices.get(t, 0)
        if p >= PRICE_MIN:
            above.append(t)
        elif p == 0 and t not in dead and not rate_limited:
            dead.add(t)
            _save_dead(dead)

    if rate_limited:
        above = list(filtered)

    above.sort(key=lambda t: prices.get(t, 0), reverse=True)
    _price_passed_cache = above
    return above


def screen(tickers, _config=None):
    global _global_rate_limited
    _global_rate_limited = False
    above_min = batch_price_filter(tickers)
    candidates = above_min[:MAX_DEEP_DIVE]

    if _last_prices_ratelimited:
        _global_rate_limited = True
        print(f"  [valuation] YFinance rate-limited — skipping deep dive, using SEC fallback for {len(candidates)} tickers", flush=True)
        return _fallback_screen(candidates)

    results = []
    with ThreadPoolExecutor(max_workers=_VAL_WORKERS) as pool:
        futures = {pool.submit(_score_one_safe, t): t for t in candidates}
        for f in as_completed(futures):
            try:
                r = f.result(timeout=INFO_TIMEOUT + 5)
                if r:
                    results.append(r)
            except Exception:
                continue

    return results


def _batch_prices(tickers, chunk_size=100):
    global _last_prices, _last_prices_ratelimited
    prices = {}
    _last_prices_ratelimited = False
    dead = _load_dead()
    rate_limited = False

    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]

        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            try:
                data = yf.download(chunk, period="1d", progress=False, auto_adjust=True)
            except YFRateLimitError:
                rate_limited = True
                for t in chunk:
                    prices[t] = PRICE_MIN + 1
                continue
            except Exception:
                for t in chunk:
                    prices[t] = 0
                continue

        if data is None or data.empty:
            for t in chunk:
                prices[t] = 0
            continue

        for t in chunk:
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    val = data["Close"][t].iloc[-1]
                else:
                    val = data["Close"].iloc[-1]
                prices[t] = float(val) if pd.notna(val) else 0
                if prices[t] == 0:
                    dead.add(t)
            except Exception:
                prices[t] = 0

    if rate_limited:
        print("  [yfinance] RATE LIMITED — bypassing price filter; some data may be missing", flush=True)
        _last_prices_ratelimited = True
    else:
        _save_dead(dead)
    _last_prices = prices
    return prices


def _get_info_process(ticker, q):
    try:
        _buf = io.StringIO()
        with contextlib.redirect_stderr(_buf):
            info = yf.Ticker(ticker).info
        q.put(info)
    except Exception:
        q.put(None)


def _score_one_safe(ticker):
    if _global_rate_limited:
        return _fallback_result(ticker)

    cached = store_get("valuation", ticker)
    if cached:
        return cached

    q = Queue()
    p = Process(target=_get_info_process, args=(ticker, q))
    p.start()
    p.join(INFO_TIMEOUT)
    if p.is_alive():
        p.terminate()
        p.join()
        return _fallback_result(ticker)
    try:
        info = q.get_nowait()
    except Exception:
        return _fallback_result(ticker)

    if not info:
        return _fallback_result(ticker)

    result = _score_from_info(ticker, info)
    if result:
        store_set("valuation", ticker, result, TTL_24H)
    return result


def _score_from_info(ticker, info):
    mcap = info.get("marketCap") or info.get("enterpriseValue", 0)
    if not mcap or mcap < MCAP_MIN or mcap > MCAP_MAX:
        return None

    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose", 0)
    if not price or price < PRICE_MIN:
        return None

    fwd_pe = info.get("forwardPE")
    rev_growth = info.get("revenueGrowth")
    pb = info.get("priceToBook")
    sector = info.get("sector", "")
    industry = info.get("industry", "")
    name = info.get("longName") or info.get("shortName", ticker)

    score = 0.0
    signals = []

    # Graduated PE scoring: strong value under 15x, moderate 15-25x, low 25-40x
    if fwd_pe and fwd_pe > 0:
        if fwd_pe < FWD_PE_MAX:
            score += (FWD_PE_MAX - int(fwd_pe)) / FWD_PE_MAX * 5
            signals.append(f"fwdPE={fwd_pe:.1f}")
        elif fwd_pe < 25:
            score += 2
            signals.append(f"fwdPE={fwd_pe:.1f}")
        elif fwd_pe < 40:
            score += 1
            signals.append(f"fwdPE={fwd_pe:.1f}")
    else:
        signals.append("pre-rev")

    # Graduated growth scoring
    if rev_growth is not None:
        if rev_growth > (REV_GROWTH_MIN / 100):
            score += min(rev_growth * 20, 5)
            signals.append(f"revGrowth={rev_growth*100:.0f}%")
        elif rev_growth > 0.05:
            score += 2
            signals.append(f"revGrowth={rev_growth*100:.0f}%")
        elif rev_growth > 0:
            score += 0.5
    else:
        signals.append("no-rev")

    if pb and pb < 3:
        signals.append(f"P/B={pb:.1f}")

    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "mcap": mcap,
        "sector": sector,
        "industry": industry,
        "fwd_pe": fwd_pe or 0,
        "rev_growth": rev_growth or 0,
        "score": round(min(score, 10), 2),
        "signals": signals,
    }


def _fallback_result(ticker):
    from .sec_client import get_ticker_name_map
    names = get_ticker_name_map()
    name = names.get(ticker, ticker)
    price = _last_prices.get(ticker, 0)
    return {
        "ticker": ticker,
        "name": name,
        "price": price,
        "mcap": 0,
        "sector": "",
        "industry": "",
        "fwd_pe": 0,
        "rev_growth": 0,
        "score": 0,
        "signals": ["rate-limited"],
    }


def _fallback_screen(candidates):
    return [_fallback_result(t) for t in candidates]
