import requests
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


def parallel_map(func, items, max_workers=8, ordered=False):
    if not items:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(func, item): item for item in items}
        for f in as_completed(futures):
            try:
                r = f.result()
                if r is not None:
                    results.append(r)
            except Exception:
                pass
    return results


def parallel_map_batch(func, batch_iter, max_workers=8):
    batches = list(batch_iter)
    return parallel_map(func, batches, max_workers=max_workers)


RSS_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def fetch_reddit_rss(subreddits, cutoff_ts, timeout=15):
    texts = []
    for sub in subreddits:
        text = _fetch_one_reddit_rss(sub, cutoff_ts, timeout)
        texts.extend(text)
    return texts


def _fetch_one_reddit_rss(sub, cutoff_ts, timeout):
    urls = [
        f"https://www.reddit.com/r/{sub}/new/.rss",
        f"https://old.reddit.com/r/{sub}/new/.rss",
    ]
    for url in urls:
        for ua in RSS_USER_AGENTS:
            try:
                resp = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
                if resp.status_code != 200:
                    continue
                return _parse_rss_entries(resp.content, cutoff_ts, sub)
            except Exception:
                continue
    return []


def _parse_rss_entries(content, cutoff_ts, source):
    texts = []
    try:
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            updated = entry.findtext("atom:updated", "", ns)
            try:
                cleaned = updated.replace("T", " ")[:19]
                dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S")
                ts = dt.timestamp()
            except (ValueError, TypeError):
                continue
            if ts < cutoff_ts:
                continue
            title = entry.findtext("atom:title", "", ns)
            content_text = entry.findtext("atom:content", "", ns)[:2000]
            combined = f"{title} {content_text}"
            if combined.strip():
                texts.append((combined, int(ts), source))
    except Exception:
        pass
    return texts
