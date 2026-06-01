import os
import json
import time
from collections import defaultdict, Counter
from datetime import datetime

ANALYSIS_FILE = "sector_analysis.json"
HISTORY_FILE = "sector_history.json"

SIGNAL_NAMES = ["valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche", "short_interest", "earnings", "financial_health", "analyst_targets"]

SIGNAL_LABELS = {
    "valuation": "Valuation",
    "insider": "Insider",
    "fund_13f": "13F",
    "social": "Social",
    "catalyst": "Catalyst",
    "technicals": "Technicals",
    "niche": "Niche",
    "short_interest": "Short Interest",
    "earnings": "Earnings",
    "financial_health": "Financial Health",
    "analyst_targets": "Analyst Targets",
}

SIGNAL_COLORS = {
    "valuation": "#3b82f6",
    "insider": "#8b5cf6",
    "fund_13f": "#f59e0b",
    "social": "#34d399",
    "catalyst": "#f472b6",
    "technicals": "#06b6d4",
    "niche": "#f97316",
    "short_interest": "#ef4444",
    "earnings": "#a78bfa",
    "financial_health": "#14b8a6",
    "analyst_targets": "#e879f9",
}

_KNOWN_SECTORS = {}

_TICKER_CACHE = {}


def _classify_sector(ticker, name="", yf_sector=""):
    if yf_sector and yf_sector not in ("Unknown", "", "N/A"):
        return yf_sector

    cache_key = f"{ticker}:{name}"
    if cache_key in _TICKER_CACHE:
        return _TICKER_CACHE[cache_key]

    if ticker in _KNOWN_SECTORS:
        _TICKER_CACHE[cache_key] = _KNOWN_SECTORS[ticker]
        return _KNOWN_SECTORS[ticker]

    name_lower = name.lower() if name else ""
    ticker_upper = ticker.upper()

    rules = [
        (["semiconductor", "memory", "chip", "processor"], "Semiconductors"),
        (["software", "cloud", "saas", "platform", "data"], "Technology"),
        (["bank", "insurance", "financial", "capital", "trust", "finance"], "Financials"),
        (["biotech", "pharma", "therapeutic", "clinical", "drug", "bio", "genetic"], "Biotechnology"),
        (["health", "medical", "hospital", "diagnostic"], "Healthcare"),
        (["solar", "renewable", "energy", "clean", "green"], "Renewable Energy"),
        (["oil", "gas", "petroleum", "refining", "mining", "coal"], "Energy & Materials"),
        (["real estate", "reit", "property", "mortgage"], "Real Estate"),
        (["retail", "consumer", "restaurant", "store", "brand"], "Consumer"),
        (["industrial", "manufacturing", "machinery", "defense", "aerospace"], "Industrials"),
        (["space", "satellite", "rocket", "launch"], "Space & Defense"),
        (["communication", "telecom", "network", "broadband"], "Telecommunications"),
        (["automotive", "electric vehicle", "ev", "auto"], "Automotive"),
        (["cyber", "security", "protection", "encrypt"], "Cybersecurity"),
        (["ai", "artificial intelligence", "machine learning", "ml", "deep learning"], "Technology"),
        (["internet", "e-commerce", "ecommerce", "online", "digital"], "Technology"),
        (["entertainment", "media", "gaming", "streaming"], "Media & Entertainment"),
        (["utility", "power", "electric", "water"], "Utilities"),
    ]

    for keywords, sector in rules:
        for kw in keywords:
            if kw in name_lower or kw in ticker_upper.lower():
                _TICKER_CACHE[cache_key] = sector
                return sector

    _TICKER_CACHE[cache_key] = "Other"
    return "Other"


def analyze(scored, ticker_info, config, llm_client=None):
    sector_data = defaultdict(lambda: {
        "tickers": [],
        "scores": {s: [] for s in SIGNAL_NAMES},
        "price": {"ret_1m": [], "ret_3m": [], "rsi": [], "vol_ratio": []},
        "insider": {"buy_value": 0, "sell_value": 0, "buying_tickers": []},
        "catalysts": {"count": 0, "tickers_with_events": set()},
        "social": {"total_mentions": 0},
        "niche": {"total_mentions": 0, "unique_keywords": set(), "unique_communities": set()},
        "short_interest": {"pct": [], "high_si_tickers": []},
        "momentum": {"52wk_breakouts": 0, "above_50ma": 0, "above_200ma": 0},
        "13f": {"new_fund_count": 0, "fund_inflow_tickers": set()},
        "convergence": {"social_niche_pairs": 0},
        "sector_boost": 0,
    })

    for e in scored:
        if not isinstance(e, dict):
            continue
        ticker = e.get("ticker", "")
        scores = e.get("scores", {})
        details = e.get("details", {})
        info = ticker_info.get(ticker, {})

        yf_sector = info.get("sector", "")
        name = info.get("name", "")
        sector = _classify_sector(ticker, name, yf_sector)
        sd = sector_data[sector]

        sd["tickers"].append(ticker)

        for s in SIGNAL_NAMES:
            v = scores.get(s, 0)
            sd["scores"][s].append(v)

        tech = details.get("technicals", {})
        if tech:
            for k in ["ret_1m", "ret_3m", "rsi", "vol_ratio"]:
                v = tech.get(k)
                if v is not None and v != "":
                    sd["price"][k].append(float(v))

            if tech.get("above_50ma") is True or tech.get("above_50ma") == "True":
                sd["momentum"]["above_50ma"] += 1
            if tech.get("above_200ma") is True or tech.get("above_200ma") == "True":
                sd["momentum"]["above_200ma"] += 1
            pct_high = tech.get("pct_from_high")
            if pct_high is not None and pct_high != "" and float(pct_high) < 5:
                sd["momentum"]["52wk_breakouts"] += 1

        ins = details.get("insider", {})
        if ins:
            bv = float(ins.get("buy_value", 0) or 0)
            sv = float(ins.get("sell_value", 0) or 0)
            sd["insider"]["buy_value"] += bv
            sd["insider"]["sell_value"] += sv
            if ins.get("net", 0) > 0:
                sd["insider"]["buying_tickers"].append(ticker)

        cat = details.get("catalyst", {})
        if cat and cat.get("events"):
            sd["catalysts"]["count"] += len(cat["events"])
            sd["catalysts"]["tickers_with_events"].add(ticker)

        soc = details.get("social", {})
        if soc:
            sd["social"]["total_mentions"] += float(soc.get("mentions", 0) or 0)

        nic = details.get("niche", {})
        if nic:
            sd["niche"]["total_mentions"] += float(nic.get("niche_mentions", 0) or 0)
            for k in nic.get("keywords", []):
                sd["niche"]["unique_keywords"].add(k)
            for c in nic.get("communities", []):
                sd["niche"]["unique_communities"].add(c)

        si = details.get("short_interest", {})
        if si:
            sp = si.get("short_pct", 0)
            if sp:
                sd["short_interest"]["pct"].append(float(sp))
            if sp and float(sp) > 20:
                sd["short_interest"]["high_si_tickers"].append(ticker)

        f13f = details.get("fund_13f", {})
        if f13f:
            sd["13f"]["new_fund_count"] += int(f13f.get("new_funds", 0) or 0)
            if f13f.get("new_funds", 0) > 0:
                sd["13f"]["fund_inflow_tickers"].add(ticker)

        social_s = scores.get("social", 0)
        niche_s = scores.get("niche", 0)
        if social_s >= 7 and niche_s >= 7:
            sd["convergence"]["social_niche_pairs"] += 1

        sd["sector_boost"] += e.get("sector_momentum_boost", 0)

    sectors_compiled = {}
    for sector, sd in sector_data.items():
        count = len(sd["tickers"])
        if count < 1:
            continue

        sig_avgs = {}
        for s in SIGNAL_NAMES:
            vals = sd["scores"][s]
            avg = sum(vals) / len(vals) if vals else 0
            active = sum(1 for v in vals if v > 0)
            sig_avgs[s] = {
                "avg": round(avg, 2),
                "active_count": active,
                "active_pct": round(active / count * 100, 1) if count > 0 else 0,
            }

        composite = round(sum(sig_avgs[s]["avg"] for s in SIGNAL_NAMES) / len(SIGNAL_NAMES), 2)

        def avg_or(vals):
            return round(sum(vals) / len(vals), 1) if vals else 0

        sectors_compiled[sector] = {
            "ticker_count": count,
            "composite_score": composite,
            "signals": sig_avgs,
            "price": {
                "avg_1m": avg_or(sd["price"]["ret_1m"]),
                "avg_3m": avg_or(sd["price"]["ret_3m"]),
                "avg_rsi": avg_or(sd["price"]["rsi"]),
                "avg_vol_ratio": avg_or(sd["price"]["vol_ratio"]),
                "positive_1m": round(100 * sum(1 for v in sd["price"]["ret_1m"] if v > 0) / max(len(sd["price"]["ret_1m"]), 1), 1),
            },
            "insider": {
                "net_value": round(sd["insider"]["buy_value"] - sd["insider"]["sell_value"], 0),
                "buy_value": round(sd["insider"]["buy_value"], 0),
                "sell_value": round(sd["insider"]["sell_value"], 0),
                "buying_tickers": len(sd["insider"]["buying_tickers"]),
                "buying_names": sd["insider"]["buying_tickers"][:5],
            },
            "catalysts": {
                "total_events": sd["catalysts"]["count"],
                "tickers_with_events": len(sd["catalysts"]["tickers_with_events"]),
            },
            "social": {
                "total_mentions": round(sd["social"]["total_mentions"], 1),
            },
            "niche": {
                "total_mentions": round(sd["niche"]["total_mentions"], 1),
                "unique_keywords": list(sd["niche"]["unique_keywords"]),
                "unique_communities": list(sd["niche"]["unique_communities"]),
            },
            "short_interest": {
                "avg_pct": avg_or(sd["short_interest"]["pct"]),
                "high_si_tickers": len(sd["short_interest"]["high_si_tickers"]),
                "high_si_names": sd["short_interest"]["high_si_tickers"][:5],
            },
            "momentum": {
                "52wk_breakouts": sd["momentum"]["52wk_breakouts"],
                "above_50ma_pct": round(100 * sd["momentum"]["above_50ma"] / count, 1) if count > 0 else 0,
                "above_200ma_pct": round(100 * sd["momentum"]["above_200ma"] / count, 1) if count > 0 else 0,
            },
            "13f": {
                "new_fund_count": sd["13f"]["new_fund_count"],
                "inflow_tickers": len(sd["13f"]["fund_inflow_tickers"]),
            },
            "convergence": {
                "social_niche_pairs": sd["convergence"]["social_niche_pairs"],
            },
            "sector_boost_avg": round(sd["sector_boost"] / count, 2) if count > 0 else 0,
            "avg_active_signals": round(sum(len([s for s in SIGNAL_NAMES if sig_avgs[s]["avg"] > 0]) for _ in range(1)) / 1, 1),
        }

    ranked = sorted(sectors_compiled.items(), key=lambda x: x[1]["composite_score"], reverse=True)

    divergences = _find_divergences(sectors_compiled, ranked)

    llm_brief = ""
    if llm_client and sectors_compiled:
        llm_brief = _generate_llm_brief(sectors_compiled, ranked, divergences, llm_client)

    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    result = {
        "timestamp": ts,
        "date": now.strftime("%Y-%m-%d %H:%M"),
        "total_tickers_analyzed": len(scored),
        "total_sectors": len(sectors_compiled),
        "sectors": sectors_compiled,
        "rankings": [s for s, _ in ranked],
        "divergences": divergences,
        "llm_brief": llm_brief,
        "top_sector": ranked[0][0] if ranked else "",
        "top_score": ranked[0][1]["composite_score"] if ranked else 0,
        "bottom_sector": ranked[-1][0] if ranked else "",
        "bottom_score": ranked[-1][1]["composite_score"] if ranked else 0,
    }

    delta = _compute_delta(result, config)
    if delta:
        result["rotation"] = delta

    _save(result, config)
    return result


def _find_divergences(sectors, ranked):
    divergences = []

    for sector, data in sectors.items():
        score = data["composite_score"]
        avg_1m = data["price"]["avg_1m"]
        insiders = data["insider"]["buying_tickers"]
        si_high = data["short_interest"]["high_si_tickers"]
        conv = data["convergence"]["social_niche_pairs"]

        notifications = []

        if score > 5 and avg_1m < 5:
            notifications.append({
                "type": "potential_value",
                "priority": "high",
                "message": f"Score {score} but only {avg_1m}% 1m return — strong signals not yet priced in",
            })

        if score > 5 and avg_1m < 0:
            notifications.append({
                "type": "undervalued",
                "priority": "high",
                "message": f"Score {score} with negative 1m return — contrarian buy candidate",
            })

        if score < 3 and avg_1m > 10:
            notifications.append({
                "type": "overbought",
                "priority": "medium",
                "message": f"Price up {avg_1m}% but signals weak ({score}) — potential top",
            })

        if insiders >= 2:
            notifications.append({
                "type": "insider_cluster",
                "priority": "high",
                "message": f"{insiders} companies with insider buying — verify filing details before treating as signal",
            })

        if si_high >= 2:
            notifications.append({
                "type": "high_short",
                "priority": "medium",
                "message": f"{si_high} companies with >20% short interest — high bearish positioning, elevated risk",
            })

        if conv >= 3:
            notifications.append({
                "type": "convergence",
                "priority": "medium",
                "message": f"{conv} tickers with social+niche convergence — elevated attention cluster, treat as noise unless corroborated",
            })

        if notifications:
            divergences.append({
                "sector": sector,
                "notifications": notifications[:3],
            })

    return divergences


def _generate_llm_brief(sectors, ranked, divergences, llm_client):
    text = "=== SECTOR ANALYSIS ===\n\n"

    for sector, data in ranked[:5]:
        text += f"\n{sector}:\n"
        text += f"  Composite: {data['composite_score']} | Tickers: {data['ticker_count']}\n"
        text += f"  1m: {data['price']['avg_1m']}% | 3m: {data['price']['avg_3m']}% | RSI: {data['price']['avg_rsi']}\n"

        active = [(s, v["avg"]) for s, v in data["signals"].items() if v["avg"] > 0]
        if active:
            sigs = ", ".join(f"{s}={v}" for s, v in active)
            text += f"  Active signals: {sigs}\n"

        if data["insider"]["buying_tickers"] > 0:
            text += f"  Insider buying: {data['insider']['buying_tickers']} companies (${data['insider']['buy_value']:,.0f})\n"
        if data["short_interest"]["high_si_tickers"] > 0:
            text += f"  High SI: {data['short_interest']['high_si_tickers']} companies\n"
        if data["13f"]["inflow_tickers"] > 0:
            text += f"  13F inflow: {data['13f']['inflow_tickers']} companies\n"
        if data["convergence"]["social_niche_pairs"] > 0:
            text += f"  Buzz convergence: {data['convergence']['social_niche_pairs']} tickers\n"

    if divergences:
        text += "\n=== DIVERGENCES ===\n"
        for d in divergences[:3]:
            for n in d["notifications"][:2]:
                text += f"{d['sector']}: [{n['type']}] {n['message']}\n"

    text += "\nProvide 3 concise observations based on the above sector data. Be critical — flag sectors where signals are weakening or diverging from price. Note where insider clusters or signal convergence appear genuine vs noise. Be specific. No boilerplate."

    try:
        from llm.client import HarbingerLLM
        if isinstance(llm_client, str):
            client = HarbingerLLM(llm_client)
        else:
            client = llm_client
        if client.health():
            return client.analyze(text)
    except Exception:
        pass
    return ""


def _compute_delta(current, config):
    prev = load_latest(config)
    if not prev:
        return None

    current_sectors = current.get("sectors", {})
    prev_sectors = prev.get("sectors", {})

    rotation = []
    all_sectors = set(list(current_sectors.keys()) + list(prev_sectors.keys()))
    for s in sorted(all_sectors):
        cur = current_sectors.get(s, {})
        prv = prev_sectors.get(s, {})
        if not cur or not prv:
            continue

        score_change = round(cur.get("composite_score", 0) - prv.get("composite_score", 0), 2)
        if abs(score_change) < 0.3:
            continue

        direction = "inflow" if score_change > 0 else "outflow"
        rotation.append({
            "sector": s,
            "composite_change": score_change,
            "direction": direction,
        })

    return sorted(rotation, key=lambda x: -abs(x["composite_change"]))


def load_latest(config):
    path = os.path.join(config.OUTPUT_DIR, ANALYSIS_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_history(config):
    path = os.path.join(config.OUTPUT_DIR, HISTORY_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _save(result, config):
    path = os.path.join(config.OUTPUT_DIR, ANALYSIS_FILE)
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    history = load_history(config) or []
    if isinstance(history, list):
        summary = {
            "timestamp": result["timestamp"],
            "date": result["date"],
            "total_sectors": result["total_sectors"],
            "rankings": result["rankings"],
            "has_llm": bool(result.get("llm_brief")),
        }
        history.append(summary)
        hpath = os.path.join(config.OUTPUT_DIR, HISTORY_FILE)
        with open(hpath, "w") as f:
            json.dump(history[-50:], f, indent=2)
