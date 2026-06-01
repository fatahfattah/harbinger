import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from .sec_client import sec_get, fetch_submissions
from .store import get_or_fetch, TTL_7D

CIK_CACHE = {}

_CATALYST_WORKERS = 12


def _load_cik_map():
    if CIK_CACHE:
        return CIK_CACHE
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        resp = sec_get(url, timeout=20)
        if not resp:
            return CIK_CACHE
        data = resp.json()
        if data:
            for _, entry in data.items():
                ticker = entry.get("ticker", "").upper()
                cik = str(entry["cik_str"]).zfill(10)
                CIK_CACHE[ticker] = cik
    except Exception:
        pass
    return CIK_CACHE


def _get_cik(ticker):
    _load_cik_map()
    return CIK_CACHE.get(ticker.upper())


def fetch(tickers, config):
    _load_cik_map()
    results = []

    with ThreadPoolExecutor(max_workers=_CATALYST_WORKERS) as pool:
        futures = {pool.submit(_score_one, t): t for t in tickers}
        for f in as_completed(futures):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception:
                continue

    return results


def _score_one(ticker):
    score = 0.0
    catalysts = []

    upcoming = _get_upcoming_earnings(ticker)
    if upcoming:
        catalysts.append(f"earnings:{upcoming}")
        score += 3

    news = _get_recent_news(ticker)
    if news:
        catalysts.append(f"news:{news[0][:60]}")
        score += 2

    sec_events = get_or_fetch("catalyst_sec", ticker, TTL_7D,
                              lambda: _get_recent_sec_events(ticker))
    if sec_events:
        for ev in sec_events:
            catalysts.append(ev)
        score += min(len(sec_events) * 2, 5)

    if catalysts:
        return {
            "ticker": ticker,
            "catalysts": catalysts,
            "score": round(min(score, 10), 2),
        }
    return None


def _get_upcoming_earnings(ticker):
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        cal = tk.calendar
        if cal is not None and "Earnings Date" in cal.index:
            ed = cal.loc["Earnings Date"].values[0]
            if hasattr(ed, "strftime"):
                return ed.strftime("%Y-%m-%d")
            return str(ed)[:10]
    except Exception:
        pass
    return None


def _get_recent_news(ticker):
    headlines = _get_google_news(ticker)
    if headlines:
        return headlines
    return _get_yfinance_news(ticker)


def _get_google_news(ticker):
    try:
        url = f"https://news.google.com/rss/search?q={ticker}+stock+earnings&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=10)
        try:
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            headlines = []
            for item in items[:3]:
                title = item.findtext("title", "")
                if title:
                    headlines.append(title)
            return headlines
        finally:
            resp.close()
    except Exception:
        return []


def _get_yfinance_news(ticker):
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        news = tk.news
        if not news:
            return []
        headlines = []
        for item in news[:3]:
            title = item.get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception:
        return []


def _get_recent_sec_events(ticker):
    cik = _get_cik(ticker)
    if not cik:
        return []

    try:
        data = fetch_submissions(cik)
        if not data:
            return []
    except Exception:
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    descriptions = recent.get("primaryDocDescription", [])
    events = []

    cutoff = datetime.now() - timedelta(days=30)

    for i, form in enumerate(forms):
        if i < len(dates):
            try:
                fd = datetime.strptime(dates[i], "%Y-%m-%d")
                if fd < cutoff:
                    break
            except ValueError:
                continue

        if form == "8-K":
            desc = descriptions[i] if i < len(descriptions) else "8-K filing"
            events.append(f"8-K:{desc[:60]}")
        elif form == "6-K":
            events.append("6-K:foreign filing")
        elif form == "S-1":
            events.append("S-1:registration")
        elif form == "S-4":
            events.append("S-4:merger registered")

        if len(events) >= 3:
            break

    return events
