import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "harbinger/1.0 (research)"}


def fetch_sp600():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.find("table", {"id": "constituents"})
        if not table:
            table = soup.find("table", class_="wikitable sortable")
        tickers = []
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if cols:
                ticker = cols[0].get_text(strip=True)
                if ticker and ticker != "Ticker":
                    tickers.append(ticker)
        return sorted(set(tickers))
    except Exception as e:
        print(f"  [universe] Failed to fetch S&P 600: {e}")
        return []


def fetch_recent_ipos(years_back=2):
    return [
        "RKLB", "ASTS", "DDOG", "MDB", "NET", "ZS",
        "SNOW", "UPST", "AFRM", "SOFI", "RXRX",
        "CRSP", "BE", "ALGM", "SITM", "ACLS", "NTRA",
    ]


def build_universe(include_sp600=True, include_ipos=True, seed_only=False):
    tickers = set()
    if seed_only:
        from config import SEED_TICKERS
        return list(SEED_TICKERS)
    if include_sp600:
        sp = fetch_sp600()
        tickers.update(sp)
        print(f"  [universe] S&P 600: {len(sp)} tickers")
    if include_ipos:
        ipos = fetch_recent_ipos()
        tickers.update(ipos)
        print(f"  [universe] Recent IPOs: {len(ipos)} tickers")
    return sorted(tickers)
