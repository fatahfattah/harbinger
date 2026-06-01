import re
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from utils import parallel_map
from .sec_client import sec_get, fetch_submissions
from .store import get as store_get, set as store_set, TTL_2H, TTL_7D

CIK_CACHE = {}
MAX_FILINGS_PER_TICKER = 3


def _load_cik_map():
    if CIK_CACHE:
        return CIK_CACHE
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        data = sec_get(url, timeout=20).json()
        if data:
            for _, entry in data.items():
                ticker = entry.get("ticker", "").upper()
                cik = str(entry["cik_str"]).zfill(10)
                CIK_CACHE[ticker] = cik
    except Exception:
        pass
    return CIK_CACHE


def fetch(tickers, config):
    cik_map = _load_cik_map()
    cutoff = datetime.now() - timedelta(days=config.INSIDER_DAYS_BACK)

    def process_ticker(t):
        cik = cik_map.get(t.upper())
        if not cik:
            return None

        filings = _get_recent_form4(cik, cutoff)
        if not filings:
            return None

        new_accs = [f["accession_clean"] for f in filings]
        cached = store_get("insider", t)
        if cached and cached.get("accs") == new_accs:
            return cached["result"]

        transactions = []
        for f in filings:
            acc = f["accession_clean"]
            txs = store_get("insider_filing", acc)
            if txs is None:
                txs = _parse_transactions(f)
                if txs:
                    store_set("insider_filing", acc, txs, TTL_7D)
            transactions.extend(txs or [])

        if not transactions:
            return None

        codes = [t["code"] for t in transactions]
        values = [t["value"] for t in transactions]
        buys = codes.count("P")
        sells = codes.count("S")
        buy_value = sum(v for i, v in enumerate(values) if codes[i] == "P")
        sell_value = sum(v for i, v in enumerate(values) if codes[i] == "S")

        net = buys - sells
        net_value = buy_value - sell_value

        count_score = net / 10.0
        normalized_count = max(-1, min(count_score, 1))

        if net_value > 0 and buy_value > 0:
            value_score = min(net_value / 500_000, 1.0)
        elif net_value < 0 and sell_value > 0:
            value_score = max(net_value / 500_000, -1.0)
        else:
            value_score = 0

        raw = normalized_count * 0.4 + value_score * 0.6
        score = max(0, (raw + 1) / 2 * 10)

        tx_summary = [{
            "name": tx["insider_name"],
            "role": tx["insider_role"],
            "code": tx["code"],
            "shares": tx["shares"],
            "price": tx["price"],
            "value": round(tx["value"]),
            "date": tx.get("date", ""),
        } for tx in transactions]

        result = {
            "ticker": t,
            "buys": buys,
            "sells": sells,
            "net": net,
            "buy_value": round(buy_value),
            "sell_value": round(sell_value),
            "net_value": round(net_value),
            "score": round(score, 2),
            "transactions": tx_summary,
        }
        store_set("insider", t, {"result": result, "accs": new_accs}, TTL_2H)
        return result

    return [r for r in parallel_map(process_ticker, tickers, max_workers=6) if r]


def _get_recent_form4(cik, cutoff):
    try:
        data = fetch_submissions(cik)
        if not data:
            return []
    except Exception:
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accession = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filings = []
    for i, form in enumerate(forms):
        if form != "4" or i >= len(accession):
            continue
        try:
            fd = datetime.strptime(dates[i], "%Y-%m-%d")
        except (ValueError, IndexError):
            continue
        if fd < cutoff:
            break
        filings.append({
            "cik_stripped": str(int(cik)),
            "accession_clean": accession[i].replace("-", ""),
            "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
            "filing_date": dates[i],
        })
        if len(filings) >= MAX_FILINGS_PER_TICKER:
            break

    return filings


def _parse_reporter_info(soup):
    name = ""
    role = ""

    # Find the reporting person name from the first table's <a> link
    # The name is in an <a> tag with href containing "action=getcompany&CIK="
    # that is NOT the issuer CIK (it's the reporting person's CIK)
    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        if "action=getcompany&CIK=" in href:
            text = a_tag.get_text(strip=True)
            if text and len(text) > 3:
                name = text
                break

    # Find the relationship section (field 5)
    for table in soup.find_all("table"):
        text = table.get_text()
        if "Relationship of Reporting Person" not in text:
            continue

        rows = table.find_all("tr")
        roles_found = []
        for row in rows:
            cells = row.find_all("td")
            for i, cell in enumerate(cells):
                cell_text = cell.get_text(strip=True)
                # Check if this cell or next cell has a role label
                if cell_text == "X" or cell_text == "true":
                    # The role label is likely in the next cell
                    for j in range(i + 1, min(i + 3, len(cells))):
                        label = cells[j].get_text(strip=True)
                        if label in ("Director", "10% Owner", "Officer (give title below)", "Other (specify below)"):
                            r = label.replace(" (give title below)", "").replace(" (specify below)", "")
                            if r not in roles_found:
                                roles_found.append(r)
                            break
                # Check for Officer title in the blue text cell
                style = cell.get("style", "")
                align = cell.get("align", "")
                if "color: blue" in style and cell_text and len(cell_text) > 2:
                    roles_found.append(cell_text)

        if roles_found:
            role = ", ".join(roles_found)
        break

    # Fallback: look for text patterns in the raw HTML
    if not role:
        body_text = soup.get_text()
        m = re.search(r"5\.\s*Relationship.*?Director.*?(?:Officer|President|CFO|CEO|VP|Chairman|Director|10%\s*Owner)", body_text, re.DOTALL)
        if m:
            # Extract nearby role text
            chunk = body_text[m.start():m.end()]
            for rw in ["CEO", "CFO", "COO", "President", "VP", "Chairman", "Director", "10% Owner", "Officer"]:
                if rw in chunk:
                    role = rw
                    break

    return name.strip(), role.strip()


def _parse_transactions(filing):
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{filing['cik_stripped']}/{filing['accession_clean']}/{filing['primary_doc']}"
    )
    try:
        resp = sec_get(url, timeout=10)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return []

    reporter_name, reporter_role = _parse_reporter_info(soup)

    transactions = []
    filing_date = filing.get("filing_date", "")

    for table in soup.find_all("table"):
        text = table.get_text()
        if "Table I" not in text:
            continue

        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 8:
                continue

            code = _cell(cols, 3)
            raw_shares = _cell(cols, 5)
            raw_price = _cell(cols, 7)

            if code not in ("P", "S"):
                continue

            shares = _parse_num(raw_shares)
            price = _parse_price(raw_price)

            if shares <= 0:
                continue

            transactions.append({
                "insider_name": reporter_name,
                "insider_role": reporter_role,
                "code": code,
                "shares": shares,
                "price": round(price, 4) if price > 0 else 0,
                "value": round(shares * price, 2) if price > 0 else 0,
                "date": filing_date,
            })

    return transactions


def _cell(cols, idx):
    if idx < len(cols):
        return cols[idx].get_text(strip=True)
    return ""


def _parse_num(s):
    try:
        return float(s.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _parse_price(s):
    s = s.replace("$", "").strip()
    m = re.match(r"([\d,]+\.?\d*)", s)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    return 0.0
