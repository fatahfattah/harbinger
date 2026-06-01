import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
from utils import parallel_map, fetch_reddit_rss, RSS_USER_AGENTS

SUBREDDITS = [
    "investing", "stocks", "wallstreetbets",
    "smallstreetbets", "ValueInvesting",
    "pennystocks", "SPACs", "biotech",
]

HEADERS = {"User-Agent": RSS_USER_AGENTS[0]}


def fetch(tickers, config):
    ticker_set = set(t.upper() for t in tickers)
    cutoff = datetime.now() - timedelta(days=config.SOCIAL_DAYS_BACK)
    cutoff_ts = cutoff.timestamp()

    texts_with_ts = []
    texts_with_ts += fetch_reddit_rss(SUBREDDITS, cutoff_ts)
    texts_with_ts += _fetch_yahoo_news_rss(cutoff_ts)

    return _score_tickers(ticker_set, texts_with_ts, config)


def _score_tickers(ticker_set, texts_with_ts, config):
    patterns = {t: re.compile(r'\b' + re.escape(t) + r'\b') for t in ticker_set}
    ticker_mentions = defaultdict(float)
    now = datetime.now()

    for text, created_ts, _ in texts_with_ts:
        age_days = max(0, (now - datetime.fromtimestamp(created_ts)).total_seconds() / 86400)
        weight = max(0.1, 1.0 - age_days * 0.15)
        upper = text.upper() if isinstance(text, str) else ""
        for t in ticker_set:
            if patterns[t].search(upper):
                ticker_mentions[t] += weight

    results = []
    for t in ticker_set:
        weighted = ticker_mentions.get(t, 0)
        if weighted < config.SOCIAL_MIN_MENTIONS:
            continue
        results.append({
            "ticker": t,
            "mentions": round(weighted, 1),
            "score": round(min(weighted / config.SOCIAL_MIN_MENTIONS * 2.5, 10), 2),
        })

    return results


def _fetch_yahoo_news_rss(cutoff_ts):
    try:
        url = "https://finance.yahoo.com/news/rssindex"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return []
        texts = []
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            pubdate = item.findtext("pubDate", "")
            try:
                cleaned = pubdate.replace("T", " ").replace("Z", "")[:19]
                dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
                ts = dt.timestamp()
            except (ValueError, TypeError):
                continue
            if ts < cutoff_ts:
                continue
            title = item.findtext("title", "")
            desc = item.findtext("description", "")[:2000]
            combined = f"{title} {desc}"
            if combined.strip():
                texts.append((combined, int(ts), "yahoo_news"))
        return texts
    except Exception:
        return []
