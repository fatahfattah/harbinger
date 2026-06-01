import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_EXCEPTION
from .sec_client import sec_get, sec_get_json, fetch_submissions
from .sec_client import _cache_get, _cache_set
from .store import get as store_get, set as store_set, TTL_12H, TTL_7D

NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"
HOLDING_TAG = "{" + NS + "}informationTable"
HOLDING_TIMEOUT = 30
FUND_TIMEOUT = 60

_NAME_CACHE = None


def _load_name_map():
    global _NAME_CACHE
    if _NAME_CACHE is not None:
        return _NAME_CACHE
    cached = _cache_get("__name_map")
    if cached:
        _NAME_CACHE = cached
        return cached

    names = {}
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        data = sec_get_json(url, timeout=30)
        if data:
            for _, entry in data.items():
                ticker = entry.get("ticker", "").upper()
                title = entry.get("title", "").upper().strip()
                if ticker and title:
                    names[title] = ticker
                    names[title.replace(" ", "")] = ticker
                    names[title.replace("&", " AND ")] = ticker
    except Exception:
        pass
    _NAME_CACHE = names
    _cache_set("__name_map", names, ttl=86400)
    return names


def _clean_name(name):
    name = name.upper().strip()
    for suffix in [" INC", " CORP", " COMPANY", " CORP.", " LTD", " PLC",
                    " LLC", " LP", " LP.", " COMMON STOCK", " COM", " COM.",
                    " CL A", " CL C", " CLASS A", " CLASS C"]:
        name = name.replace(suffix, "")
    name = name.replace("&", " AND ").replace(" ", "").strip()
    return name


def _match_by_name(name_of_issuer):
    names = _load_name_map()
    cleaned = _clean_name(name_of_issuer)
    if cleaned in names:
        return names[cleaned]

    for known_name, ticker in names.items():
        kn_clean = known_name.replace(" ", "").upper()
        if kn_clean == cleaned:
            return ticker

    for known_name, ticker in names.items():
        kn_clean = known_name.replace(" ", "").upper()
        if len(cleaned) >= 8 and cleaned.startswith(kn_clean[:8]):
            return ticker
    return None


def fetch(tickers, config):
    tracked = set(t.upper() for t in tickers)
    fund_results = {}

    funded = list(config.NOTABLE_FUNDS.items())

    def process_fund(args):
        cik, fund_name = args
        try:
            pair = _get_13f_pair(cik)
            if not pair:
                return None
            latest_data, prev_data = pair
            latest_holdings = _parse_13f_holdings(latest_data)
            prev_holdings = _parse_13f_holdings(prev_data)
            new_positions = set(latest_holdings.keys()) - set(prev_holdings.keys())
            all_held = set(latest_holdings.keys())
            relevant_new = new_positions & tracked
            relevant_all = all_held & tracked
            if relevant_all:
                return {
                    "fund_name": fund_name,
                    "new": relevant_new,
                    "all": relevant_all,
                }
        except Exception:
            pass
        return None

    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(process_fund, (cik, name)): name for cik, name in funded}
        try:
            for f in as_completed(futures, timeout=FUND_TIMEOUT):
                r = f.result()
                if r:
                    results.append(r)
        except TimeoutError:
            for f in futures:
                f.cancel()
            print(f"[fund_13f] timed out after {FUND_TIMEOUT}s, {len(results)} funds processed", file=__import__('sys').stderr)

    t_new = defaultdict(list)
    t_all = defaultdict(list)
    for r in results:
        for t in r["new"]:
            t_new[t].append(r["fund_name"])
        for t in r["all"]:
            t_all[t].append(r["fund_name"])

    out = []
    for t in tracked:
        new_funds = t_new.get(t, [])
        all_funds = t_all.get(t, [])
        if not all_funds:
            continue
        score = min((len(new_funds) * 3 + len(all_funds)) / 3 * 10, 10)
        out.append({
            "ticker": t,
            "new_fund_count": len(new_funds),
            "funds": all_funds,
            "new_funds": new_funds,
            "existing_funds": [f for f in all_funds if f not in new_funds],
            "score": round(score, 2),
        })

    return out


def _get_13f_pair(cik):
    cached = store_get("13f_pair", cik)
    if cached is not None:
        return None if cached == "_NONE_" else cached
    pair = _fetch_13f_pair(cik)
    store_set("13f_pair", cik, list(pair) if pair else "_NONE_", TTL_12H)
    return pair

def _fetch_13f_pair(cik):
    try:
        data = fetch_submissions(cik)
        if not data:
            return None
    except Exception:
        return None

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession = recent.get("accessionNumber", [])

    filings = []
    for i, form in enumerate(forms):
        if form not in ("13F-HR", "13F-HR/A") or i >= len(accession):
            continue
        acc = accession[i].replace("-", "")
        holding_file = _find_holding_file(cik, acc)
        if holding_file:
            filings.append({
                "cik": cik,
                "accession_clean": acc,
                "holding_file": holding_file,
            })
            if len(filings) == 2:
                break

    if len(filings) >= 2:
        return filings[0], filings[1]
    return None


def _find_holding_file(cik, accession_clean):
    ci = str(int(cik))
    url = f"https://www.sec.gov/Archives/edgar/data/{ci}/{accession_clean}/index.json"
    try:
        data = sec_get_json(url, timeout=15)
        if not data:
            return None
        items = data.get("directory", {}).get("item", [])
        for item in items:
            raw = item.get("name", "")
            if "holding" in raw.lower() and raw.endswith(".xml"):
                return raw
        for item in items:
            raw = item.get("name", "")
            if "infotable" in raw.lower() and raw.endswith(".xml"):
                return raw
        for item in reversed(items):
            raw = item.get("name", "")
            if raw.endswith(".xml") and raw.find(".") > 0:
                return raw
        return None
    except Exception:
        return None


def _parse_13f_holdings(filing):
    acc = filing.get("accession_clean", "")
    cached = store_get("13f_holdings", acc)
    if cached is not None:
        return cached

    holdings = {}
    ci = str(int(filing["cik"]))
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{ci}/{filing['accession_clean']}/{filing['holding_file']}"
    )
    try:
        resp = sec_get(url, timeout=HOLDING_TIMEOUT)
        if not resp:
            return holdings
        root = ET.fromstring(resp.content)
    except Exception:
        return holdings

    if root.tag == HOLDING_TAG:
        for info_table in root:
            ticker = _extract_ticker(info_table)
            if ticker:
                value_str = info_table.findtext(f"{{{NS}}}value", "").replace(",", "")
                try:
                    value = int(float(value_str)) if value_str else 0
                except (ValueError, TypeError):
                    value = 0
                holdings[ticker] = holdings.get(ticker, 0) + value

    if acc:
        store_set("13f_holdings", acc, holdings, TTL_7D)
    return holdings


def _extract_ticker(info_table):
    ticker_tag = info_table.find(f"{{{NS}}}ticker")
    if ticker_tag is not None and ticker_tag.text:
        t = ticker_tag.text.strip().upper()
        if t and len(t) <= 5 and t.isalnum():
            return t

    name = info_table.findtext(f"{{{NS}}}nameOfIssuer", "")
    if name:
        t = _match_by_name(name)
        if t:
            return t

    return None
