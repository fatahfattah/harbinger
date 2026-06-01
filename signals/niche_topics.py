import re
from datetime import datetime, timedelta
from collections import defaultdict
from utils import fetch_reddit_rss, RSS_USER_AGENTS

SECTOR_COMMUNITIES = [
    ("Biotechnology",       ["biotech", "BiotechInvesting", "clinicaltrials"]),
    ("Semiconductors",      ["hardware", "chipdesign", "AMD", "NVIDIA", "ECE"]),
    ("Communication Services", ["technology", "space", "Starlink", "ASTSpaceMobile"]),
    ("Consumer Cyclical",   ["retail", "SupplyChain", "logistics"]),
    ("Consumer Defensive",  ["retail", "SupplyChain"]),
    ("Basic Materials",     ["mining", "commodities", "uranium", "pennystocks"]),
    ("Real Estate",         ["realestate", "REITs", "commercialrealestate"]),
    ("Automotive",          ["electricvehicles", "cars", "Mvis"]),
    ("Technology",          ["hardware", "AMD", "NVIDIA", "datacenter", "LocalLLaMA"]),
    ("Healthcare",          ["biotech", "BiotechInvesting", "clinicaltrials"]),
    ("Energy",              ["energy", "RenewableEnergy", "oilandgas", "hydrogen"]),
    ("Industrials",         ["aerospace", "manufacturing", "logistics", "SupplyChain"]),
    ("Financial",           ["fintech", "SPACs"]),
    ("Utilities",           ["energy", "RenewableEnergy", "nuclear"]),
    ("Defense",             ["aerospace", "defense", "LessCredibleDefense"]),
]

SECTOR_KEYWORDS = {
    "Technology":           ["ai", "llm", "datacenter", "hpc", "gpu", "cloud", "saas", "infrastructure"],
    "Semiconductors":       ["hbm", "dram", "nand", "wafer", "foundry", "node", "chiplet", "packaging", "tsmc", "allocation"],
    "Healthcare":           ["trial", "fda", "pdufa", "nda", "phase 1", "phase 2", "phase 3", "readout", "approval"],
    "Biotechnology":        ["trial", "fda", "pdufa", "nda", "crispr", "car-t", "mrna", "antibody"],
    "Energy":               ["lithium", "battery", "solar", "wind", "hydrogen", "grid", "renewable", "ev charging"],
    "Industrials":          ["supply chain", "inventory", "logistics", "shipping", "port", "freight"],
    "Consumer Cyclical":    ["inventory", "retail", "consumer", "spending", "ecommerce"],
    "Financial":            ["fintech", "lending", "payment", "bnpl", "neobank", "spac"],
    "Communication Services": ["spectrum", "satellite", "direct-to-cell", "5g", "broadband", "space"],
    "Basic Materials":      ["copper", "lithium", "rare earth", "uranium", "commodity"],
    "Real Estate":          ["reit", "cre", "office", "data center", "industrial", "warehouse"],
    "Utilities":            ["grid", "renewable", "power", "utility", "battery storage", "nuclear"],
    "Automotive":           ["ev", "electric", "battery", "autonomous", "charging"],
    "Defense":              ["contract", "dod", "pentagon", "military", "defense", "procurement"],
}

GENERAL_SUBS = {"investing", "stocks", "wallstreetbets", "valueinvesting", "smallstreetbets", "pennystocks"}

HEADERS = {"User-Agent": RSS_USER_AGENTS[0]}


def fetch(tickers_info, config):
    cutoff = datetime.now() - timedelta(days=config.NICHE_DAYS_BACK)
    cutoff_ts = cutoff.timestamp()

    sector_map = {}
    for t, info in tickers_info.items():
        sector_map[t] = info.get("sector", "")

    subs_needed = set()
    ticker_subs = {}
    for t, sector in sector_map.items():
        matched = _match_sector(sector)
        subs_needed.update(matched)
        ticker_subs[t] = matched

    niche_texts = fetch_reddit_rss(sorted(subs_needed), cutoff_ts)

    all_texts = niche_texts
    return _score(ticker_subs, sector_map, all_texts, cutoff_ts, config)


def _match_sector(sector):
    sector_lower = sector.lower()
    words = sector_lower.split()
    for key, subs in SECTOR_COMMUNITIES:
        key_lower = key.lower()
        if key_lower == sector_lower:
            return subs
        if " " in key_lower:
            if key_lower in sector_lower:
                return subs
        else:
            if key_lower in words:
                return subs
    return []


def _score(ticker_subs, sector_map, all_texts, cutoff_ts, config):
    ticker_patterns = {t: re.compile(r'\b' + re.escape(t) + r'\b') for t in ticker_subs}
    keyword_map = {}
    for t, sector in sector_map.items():
        keyword_map[t] = _match_keywords(sector)

    now = datetime.now()

    niche_mentions = defaultdict(float)
    niche_keywords = defaultdict(set)
    niche_subs_used = defaultdict(set)
    general_mentions = defaultdict(float)

    for text, ts, source in all_texts:
        age_days = max(0, (now - datetime.fromtimestamp(ts)).total_seconds() / 86400)
        weight = max(0.1, 1.0 - age_days * 0.2)
        upper = text.upper() if isinstance(text, str) else ""

        for t in ticker_subs:
            if ticker_patterns[t].search(upper):
                is_niche = source not in GENERAL_SUBS and not source.startswith("st_")
                if is_niche:
                    niche_mentions[t] += weight
                    niche_subs_used[t].add(source)
                else:
                    general_mentions[t] += weight

                for kw in keyword_map.get(t, []):
                    if kw.upper() in upper:
                        niche_keywords[t].add(kw.upper())

    results = []
    for t in ticker_subs:
        nw = niche_mentions.get(t, 0)
        gw = general_mentions.get(t, 0)

        if nw < config.NICHE_MIN_MENTIONS:
            continue

        niche_only = max(nw - gw, 0)
        keyword_bonus = min(len(niche_keywords.get(t, set())) * 1.5, 3)
        community_diversity = min(len(niche_subs_used.get(t, set())) * 0.5, 2)

        raw = nw / config.NICHE_MIN_MENTIONS * 5 + keyword_bonus + community_diversity

        if niche_only > 0 and gw > 0:
            ratio = niche_only / (nw + gw)
            raw *= 1 + ratio

        early_score = round(min(raw, 10), 2)

        results.append({
            "ticker": t,
            "niche_mentions": round(nw, 1),
            "general_mentions": round(gw, 1),
            "keywords": sorted(niche_keywords.get(t, set())),
            "communities": sorted(niche_subs_used.get(t, set())),
            "score": early_score,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def _match_keywords(sector):
    sector_lower = sector.lower()
    words = sector_lower.split()
    for key, kws in SECTOR_KEYWORDS.items():
        key_lower = key.lower()
        if key_lower == sector_lower:
            return kws
        if " " in key_lower:
            if key_lower in sector_lower:
                return kws
        else:
            if key_lower in words:
                return kws
    return []
