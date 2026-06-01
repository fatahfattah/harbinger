from collections import defaultdict, Counter
import statistics
from llm.patterns import ARCHEYTPE_PROFILES

ARCH_DIMS = ["valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche",
             "short_interest", "earnings", "financial_health", "analyst_targets",
             "institutional", "dividend_quality", "seasonality", "macro_exposure"]

LEADING_SIGNALS = {"insider", "earnings", "catalyst", "valuation", "analyst_targets"}
LAGGING_SIGNALS = {"technicals", "social", "niche", "short_interest", "fund_13f", "financial_health",
                   "institutional", "dividend_quality", "seasonality", "macro_exposure"}

SECTOR_MOMENTUM_BOOST_MAX = 2.0
CONVERGENCE_BOOST_MAX = 2.0
CONVERGENCE_BOOST_PER_SIGNAL = 0.5


def rank(signal_data: dict[str, list], weights: dict, sector_map: dict[str, str] = None):
    merged = defaultdict(lambda: {"ticker": None, "scores": {}, "details": {}})
    tickers_seen = set()

    for signal_name, candidates in signal_data.items():
        if not candidates:
            continue
        for c in candidates:
            if isinstance(c, dict):
                t = c.get("ticker", "")
                sc = c.get("score", 0)
            else:
                t = getattr(c, "ticker", "")
                sc = getattr(c, "score", 0)
            if not t:
                continue
            tickers_seen.add(t)
            merged[t]["ticker"] = t
            merged[t]["scores"][signal_name] = sc
            merged[t]["details"][signal_name] = _extract_details(signal_name, c if isinstance(c, dict) else c.details)

    # — Sector momentum boost —
    sector_scores = _compute_sector_momentum(
        {t: merged[t]["scores"] for t in tickers_seen},
        sector_map or {}
    )

    # — Regime detection —
    regime_boost = _detect_regime(merged, tickers_seen)

    scored = []
    for t in tickers_seen:
        entry = merged[t]

        total = sum(entry["scores"].get(s, 0) * weights.get(s, 0) for s in ARCH_DIMS if s in weights)

        raw_score = total

        # 1. Convergence boost
        active = sum(1 for s in ARCH_DIMS if entry["scores"].get(s, 0) > 0)
        convergence_boost = min(active * CONVERGENCE_BOOST_PER_SIGNAL, CONVERGENCE_BOOST_MAX)

        # 2. Sector momentum boost
        boost = 0
        sector = (sector_map or {}).get(t, "")
        if sector in sector_scores:
            sector_avg = sector_scores[sector]
            if sector_avg > 0.05:
                boost = min(sector_avg * 10, SECTOR_MOMENTUM_BOOST_MAX)

        # 3. Social+Niche convergence amplifier
        social = entry["scores"].get("social", 0)
        niche = entry["scores"].get("niche", 0)
        convergence_amp = 0
        if social >= 7 and niche >= 7:
            convergence_amp = 1.5
        elif social >= 5 and niche >= 5:
            convergence_amp = 0.5

        # 4. Regime archetype boost
        archetype_boost = 0
        alpha = entry["scores"].get("technicals", 0) * 0.5 + social * 0.3 + niche * 0.2
        if alpha > 5:
            archetype_boost = regime_boost

        total = total + convergence_boost + boost + convergence_amp + archetype_boost

        # — Pre-discovery (early stage) score —
        leading = sum(entry["scores"].get(s, 0) * w for s, w in weights.items() if s in LEADING_SIGNALS)
        lagging = sum(entry["scores"].get(s, 0) * w for s, w in weights.items() if s in LAGGING_SIGNALS)
        early_stage = leading - lagging * 0.5

        archetype, sim = _match_archetype(entry["scores"])

        scored.append({
            "ticker": t,
            "total_score": round(total, 2),
            "raw_score": round(raw_score, 2),
            "active_signals": active,
            "scores": dict(entry["scores"]),
            "details": dict(entry["details"]),
            "archetype": archetype,
            "archetype_similarity": sim,
            "early_stage_score": round(early_stage, 2),
            "leading_score": round(leading, 2),
            "lagging_score": round(lagging, 2),
            "sector_momentum_boost": round(boost, 2),
            "convergence_amplifier": round(convergence_amp, 2),
            "archetype_regime_boost": round(archetype_boost, 2),
        })

    scored.sort(key=lambda x: x["total_score"], reverse=True)
    return scored


def _compute_sector_momentum(ticker_scores, sector_map):
    sector_tech_scores = defaultdict(list)
    for t, scores in ticker_scores.items():
        sector = sector_map.get(t, "")
        if not sector:
            continue
        tech = scores.get("technicals", 0)
        if tech > 0:
            sector_tech_scores[sector].append(tech)

    sector_avg = {}
    for sector, vals in sector_tech_scores.items():
        sector_avg[sector] = statistics.mean(vals) if vals else 0
    return sector_avg


def _detect_regime(merged, tickers_seen):
    pattern_counts = Counter()
    for t in tickers_seen:
        scores = merged[t]["scores"]
        a, _ = _match_archetype(scores)
        pattern_counts[a] += 1

    if not pattern_counts:
        return 0

    total = sum(pattern_counts.values())
    asts_pct = pattern_counts.get("ASTS-like", 0) / total if total > 0 else 0
    mu_pct = pattern_counts.get("MU-like", 0) / total if total > 0 else 0

    if asts_pct > 0.4:
        return 1.5
    elif mu_pct > 0.4:
        return -0.5
    return 0


def _match_archetype(scores):
    active_dims = [d for d in ARCH_DIMS if scores.get(d, 0) > 0]
    if len(active_dims) < 3:
        return "Novel", 0

    best = "Novel"
    best_sim = -1

    for name, ref in ARCHEYTPE_PROFILES.items():
        sims = []
        for d in active_dims:
            c = scores.get(d, 0)
            r = ref.get(d, 0)
            sims.append(1 - abs(c - r) / 10)
        avg = sum(sims) / len(sims)
        if avg > best_sim:
            best_sim = avg
            best = name

    pct = round(best_sim * 100)
    return ("Novel", pct) if pct < 30 else (best, pct)


def _extract_details(signal_name, candidate):
    if signal_name == "valuation":
        return {
            "name": candidate.get("name", ""),
            "price": candidate.get("price", 0),
            "sector": candidate.get("sector", ""),
            "fwd_pe": candidate.get("fwd_pe", 0),
            "rev_growth": candidate.get("rev_growth", 0),
            "signals": candidate.get("signals", []),
        }
    elif signal_name == "insider":
        return {
            "buys": candidate.get("buys", 0),
            "sells": candidate.get("sells", 0),
            "net": candidate.get("net", 0),
            "buy_value": candidate.get("buy_value", 0),
            "sell_value": candidate.get("sell_value", 0),
            "net_value": candidate.get("net_value", 0),
            "transactions": candidate.get("transactions", []),
        }
    elif signal_name == "fund_13f":
        return {
            "new_funds": candidate.get("new_fund_count", 0),
            "fund_names": candidate.get("funds", []),
        }
    elif signal_name == "social":
        return {
            "mentions": candidate.get("mentions", 0),
            "subreddits": candidate.get("subreddits", {}),
        }
    elif signal_name == "catalyst":
        return {
            "events": candidate.get("catalysts", []),
        }
    elif signal_name == "technicals":
        return {
            "ret_1m": candidate.get("ret_1m", 0),
            "ret_3m": candidate.get("ret_3m", 0),
            "rsi": candidate.get("rsi", 0),
            "vol_ratio": candidate.get("vol_ratio", 0),
            "above_50ma": candidate.get("above_50ma", None),
            "above_200ma": candidate.get("above_200ma", None),
            "pct_from_high": candidate.get("pct_from_high", None),
            "signals": candidate.get("signals", []),
        }
    elif signal_name == "niche":
        return {
            "niche_mentions": candidate.get("niche_mentions", 0),
            "general_mentions": candidate.get("general_mentions", 0),
            "keywords": candidate.get("keywords", []),
            "communities": candidate.get("communities", []),
        }
    elif signal_name == "short_interest":
        return {
            "short_pct": candidate.get("short_pct", 0),
            "short_ratio": candidate.get("short_ratio", 0),
            "short_change": candidate.get("short_change", ""),
        }
    elif signal_name == "earnings":
        return {
            "beat_rate": candidate.get("beat_rate", 0),
            "avg_surprise_pct": candidate.get("avg_surprise_pct", 0),
            "beats": candidate.get("beats", 0),
            "total_quarters": candidate.get("total", 0),
        }
    elif signal_name == "financial_health":
        return {
            "debt_to_equity": candidate.get("debt_to_equity"),
            "current_ratio": candidate.get("current_ratio"),
            "profit_margin": candidate.get("profit_margin"),
            "return_on_equity": candidate.get("return_on_equity"),
            "signals": candidate.get("signals", []),
        }
    elif signal_name == "analyst_targets":
        return {
            "price_target": candidate.get("price_target"),
            "pt_upside": candidate.get("pt_upside"),
            "consensus": candidate.get("consensus"),
            "analyst_count": candidate.get("analyst_count"),
        }
    elif signal_name == "institutional":
        return {
            "inst_pct": candidate.get("inst_pct"),
            "insider_pct": candidate.get("insider_pct"),
            "holder_count": candidate.get("holder_count"),
            "avg_change": candidate.get("avg_change"),
            "signals": candidate.get("signals", []),
        }
    elif signal_name == "dividend_quality":
        return {
            "dividend_yield": candidate.get("dividend_yield"),
            "payout_ratio": candidate.get("payout_ratio"),
            "beta": candidate.get("beta"),
            "gross_margin": candidate.get("gross_margin"),
            "signals": candidate.get("signals", []),
        }
    return {}
