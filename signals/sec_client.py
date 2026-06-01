import json as _json
import requests
import time
import threading

SEC_HEADERS = {
    "User-Agent": "harbinger research v1 (research@example.com)",
    "Accept": "application/json",
}

# Thread-safe rate limiter — SEC allows 10 req/sec
_RATE_LOCK = threading.Lock()
_LAST_CALL = 0.0
_MIN_INTERVAL = 0.12

# In-memory cache with TTL (seconds)
# Stores (status_code, text) tuples only — never raw Response objects
_CACHE = {}
_CACHE_TTL = {}
_CACHE_LOCK = threading.Lock()
_DEFAULT_TTL = 3600


class _CachedResponse:
    """Lightweight stand-in for requests.Response holding cached text."""
    __slots__ = ("status_code", "text", "content")

    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8") if text else b""

    def json(self):
        return _json.loads(self.text)


def _wait_interval():
    global _LAST_CALL
    with _RATE_LOCK:
        now = time.time()
        elapsed = now - _LAST_CALL
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _LAST_CALL = time.time()


def _cache_get(key):
    with _CACHE_LOCK:
        if key in _CACHE:
            if time.time() - _CACHE_TTL.get(key, 0) < _DEFAULT_TTL:
                return _CACHE[key]
    return None


def _cache_set(key, value, ttl=None):
    with _CACHE_LOCK:
        _CACHE[key] = value
        _CACHE_TTL[key] = time.time()


def cache_clear():
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_TTL.clear()


def sec_get(url, timeout=30, max_retries=2):
    cached = _cache_get(url)
    if cached is not None:
        status_code, text = cached
        return _CachedResponse(status_code, text)

    _wait_interval()
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=timeout)
            if resp.status_code == 429:
                wait = min(5 * (attempt + 1), 30)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            pair = (resp.status_code, resp.text)
            resp.close()
            _cache_set(url, pair)
            return _CachedResponse(pair[0], pair[1])
        except requests.exceptions.HTTPError:
            if attempt < max_retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise
        except requests.RequestException:
            if attempt < max_retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    return None


def sec_get_json(url, timeout=30):
    resp = sec_get(url, timeout=timeout)
    if resp and resp.status_code == 200:
        return resp.json()
    return None


def fetch_submissions(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    return sec_get_json(url)


_TICKER_NAME_MAP = None
_TICKER_CIK_MAP = None


def get_ticker_cik_map():
    """Fetch SEC company tickers JSON → {ticker: CIK_padded_to_10_digits}.
    Cached in-memory for the lifetime of the process.
    """
    global _TICKER_CIK_MAP
    if _TICKER_CIK_MAP is not None:
        return _TICKER_CIK_MAP
    try:
        data = sec_get_json("https://www.sec.gov/files/company_tickers.json")
        if data:
            _TICKER_CIK_MAP = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
        else:
            _TICKER_CIK_MAP = {}
    except Exception:
        _TICKER_CIK_MAP = {}
    return _TICKER_CIK_MAP


def cik_for_ticker(ticker):
    """Look up the 10-digit CIK for a ticker. Returns None if not found."""
    m = get_ticker_cik_map()
    return m.get(ticker.upper())


def get_ticker_name_map():
    """Fetch SEC company tickers JSON → {ticker: company_name} mapping.
    Cached in-memory for the lifetime of the process.
    """
    global _TICKER_NAME_MAP
    if _TICKER_NAME_MAP is not None:
        return _TICKER_NAME_MAP
    try:
        data = sec_get_json("https://www.sec.gov/files/company_tickers.json")
        if data:
            _TICKER_NAME_MAP = {v["ticker"].upper(): v["title"] for v in data.values()}
        else:
            _TICKER_NAME_MAP = {}
    except Exception:
        _TICKER_NAME_MAP = {}
    return _TICKER_NAME_MAP
