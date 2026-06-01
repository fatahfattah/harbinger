#!/usr/bin/env python3
import sys
import os
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

import config
from signals import valuation, social, technicals, insider, fund_13f, catalysts, niche_topics, short_interest, earnings, universe, store, financial_health, analyst_targets, institutional, dividend_quality, seasonality, macro_exposure
from scoring.ranker import rank, LEADING_SIGNALS
from output.report import print_report
from llm.client import HarbingerLLM
from tracking import sector_watch


def main():
    parser = argparse.ArgumentParser(description="harbinger — stock signal scanner")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM analysis pass")
    parser.add_argument("--tickers", nargs="+", help="Override ticker universe")
    parser.add_argument("--top-n", type=int, default=config.TOP_N, help="Number of top results")
    parser.add_argument("--universe", choices=["seed", "sp600", "sp600+ipos"], default="seed")
    parser.add_argument("--early", action="store_true", help="Sort by early-stage score (pre-discovery)")
    args = parser.parse_args()

    if args.top_n:
        config.TOP_N = args.top_n
    if args.skip_llm:
        config.LLM_ENABLED = False

    store.init_db()
    store.delete_expired()

    print(f"  harbinger scan — {datetime.now().strftime('%Y-%m-%d %H:%M')}", flush=True)
    print(f"  press Ctrl+C to abort\n", flush=True)

    # Build universe
    all_tickers = _build_universe(args)
    print(f"  Universe: {len(all_tickers)} tickers\n", flush=True)

    signal_data = {}
    total_start = time.time()

    def run_signal(name, fetch_fn, tickers, msg=""):
        print(f"  [{name}] running...", end=" ", flush=True)
        t0 = time.time()
        try:
            r = fetch_fn(tickers, config)
            print(f"{len(r)} candidates, {time.time()-t0:.1f}s [OK]", flush=True)
            signal_data[name] = r or []
            return r
        except Exception as e:
            print(f"ERROR: {e} [{time.time()-t0:.1f}s]", flush=True)
            signal_data[name] = []
            return []

    # ── Tier 1: Fast filters (full universe) ──
    val_result = run_signal("valuation", valuation.screen, all_tickers)
    soc_result = run_signal("social", social.fetch, all_tickers)
    tech_result = run_signal("technicals", technicals.fetch, all_tickers)
    earn_result = run_signal("earnings", earnings.fetch, all_tickers)

    # ── Build tier 2 candidate set ──
    tier2 = _build_tier2(val_result, soc_result, tech_result, all_tickers, earn_result)
    print(f"  Tier 2 (SEC modules): {len(tier2)} tickers\n", flush=True)

    # ── Tier 2: SEC-heavy modules ──
    run_signal("insider", insider.fetch, tier2)
    run_signal("fund_13f", fund_13f.fetch, tier2)
    run_signal("catalyst", catalysts.fetch, tier2)
    run_signal("short_interest", short_interest.fetch, tier2)
    run_signal("financial_health", financial_health.fetch, tier2)
    run_signal("analyst_targets", analyst_targets.fetch, tier2)
    run_signal("institutional", institutional.fetch, tier2)
    run_signal("dividend_quality", dividend_quality.fetch, tier2)
    run_signal("seasonality", seasonality.fetch, tier2)
    run_signal("macro_exposure", macro_exposure.fetch, tier2)

    # ── Tier 2b: Niche (needs sector info) ──
    info = {}
    for r in val_result or []:
        info[r["ticker"]] = {"sector": r.get("sector", ""), "name": r.get("name", "")}
    for t in tier2:
        if t not in info:
            info[t] = {"sector": "", "name": ""}

    print(f"  [niche] running...", end=" ", flush=True)
    t0 = time.time()
    try:
        niche_result = niche_topics.fetch(info, config)
        print(f"{len(niche_result)} candidates, {time.time()-t0:.1f}s [OK]", flush=True)
        signal_data["niche"] = niche_result or []
    except Exception as e:
        print(f"ERROR: {e} [{time.time()-t0:.1f}s]", flush=True)
        signal_data["niche"] = []

    total_time = time.time() - total_start
    print(f"\n  Scan complete in {total_time:.1f}s", flush=True)

    # ── 3. Rank ──
    sector_map = {t: info[t]["sector"] for t in info}
    scored = rank(signal_data, config.WEIGHTS, sector_map=sector_map)

    if args.early:
        scored.sort(key=lambda x: x["early_stage_score"], reverse=True)
        print("  Sorted by early-stage score (leading - lagging*0.5)", flush=True)

    print(f"  {len(scored)} tickers scored\n", flush=True)

    # ── 4. Sector analysis ──
    llm = None
    if config.LLM_ENABLED:
        try:
            llm = HarbingerLLM(config.LLM_API)
        except Exception:
            pass
    try:
        sector_watch.analyze(scored, info, config, llm_client=llm if (llm and llm.health()) else None)
    except Exception as e:
        print(f"  [sector_watch] ERROR: {e}", flush=True)

    # ── 5. LLM analysis ──
    llm_analysis = None
    top_candidates = scored[:config.TOP_N]
    if config.LLM_ENABLED:
        print("  LLM analysis...", end=" ", flush=True)
        llm = HarbingerLLM(config.LLM_API)
        if llm.health():
            text = _format_for_llm(top_candidates)
            try:
                llm_analysis = llm.analyze(text)
                print("done\n", flush=True)
            except Exception as e:
                print(f"FAILED: {e}\n", flush=True)
        else:
            print(f"server not reachable at {config.LLM_API}\n", flush=True)

    # ── 6. LLM cross-validation ──
    cross_val = None
    if config.LLM_ENABLED and llm_analysis and not llm_analysis.startswith("[LLM"):
        print("  Cross-validation...", end=" ", flush=True)
        try:
            cross_val = llm.cross_validate(top_candidates)
            print("done\n", flush=True)
        except Exception as e:
            print(f"FAILED: {e}\n", flush=True)

    # ── 7. Report ──
    run_meta = {
        "universe": args.universe,
        "total_tickers": len(all_tickers),
        "tier2_tickers": len(tier2),
        "scan_duration_seconds": round(total_time, 1),
    }
    for k in ("valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche", "short_interest", "earnings", "financial_health", "analyst_targets", "institutional", "dividend_quality"):
        run_meta[f"{k}_candidates"] = len(signal_data.get(k, []))
    run_meta["sector_momentum"] = scored[0].get("sector_momentum_boost", 0) if scored else 0

    print_report(scored, llm_analysis, config, metadata=run_meta, cross_val=cross_val)


def _build_universe(args):
    if args.tickers:
        return args.tickers
    if args.universe == "sp600":
        return universe.build_universe(include_sp600=True, include_ipos=False, seed_only=False)
    if args.universe == "sp600+ipos":
        return universe.build_universe(include_sp600=True, include_ipos=True, seed_only=False)
    return universe.build_universe(seed_only=True)


def _build_tier2(val_result, soc_result, tech_result, all_tickers, earn_result=None):
    tier2 = set()
    for r in val_result or []:
        tier2.add(r["ticker"])
    for r in soc_result or []:
        tier2.add(r["ticker"])
    if earn_result:
        for r in earn_result:
            tier2.add(r["ticker"])

    for t in valuation.last_price_passed()[:config.MAX_SEC_TICKERS]:
        tier2.add(t)

    tier2_list = sorted(tier2)
    if len(tier2_list) < config.MAX_SEC_TICKERS and tech_result:
        existing = set(tier2_list)
        for r in sorted(tech_result, key=lambda r: r.get("score", 0), reverse=True):
            if r["ticker"] not in existing:
                tier2_list.append(r["ticker"])
                existing.add(r["ticker"])
                if len(tier2_list) >= config.MAX_SEC_TICKERS:
                    break

    return sorted(tier2_list)[:config.MAX_SEC_TICKERS * 2]


def _format_for_llm(candidates):
    lines = []
    for e in candidates:
        det = e["details"]
        tags = []

        v = det.get("valuation", {})
        if v:
            tags.append(f"val({v.get('fwd_pe','?')}pe,{v.get('rev_growth','?')}gr)")

        ins = det.get("insider", {})
        if ins:
            nv = ins.get("net_value", 0)
            tags.append(f"ins({ins.get('net',0)}tx,${nv:+.0f})")

        f13f = det.get("fund_13f", {})
        if f13f:
            tags.append(f"13f(+{f13f.get('new_funds',0)}funds)")

        soc = det.get("social", {})
        if soc:
            tags.append(f"rdt({soc.get('mentions',0)})")

        cat = det.get("catalyst", {})
        if cat:
            tags.append(f"cat({'; '.join(cat.get('events', []))[:40]})")

        tech = det.get("technicals", {})
        if tech:
            tags.append(f"tech(1m{tech.get('ret_1m','?')}%,3m{tech.get('ret_3m','?')}%)")

        niche = det.get("niche", {})
        if niche:
            kws = ",".join(niche.get("keywords", []))[:20]
            tags.append(f"niche({niche.get('niche_mentions',0)}m,{kws})")

        si = det.get("short_interest", {})
        if si and si.get("short_pct", 0) > 0:
            tags.append(f"short({si.get('short_pct',0):.0f}%)")

        earn = det.get("earnings", {})
        if earn and earn.get("total_quarters", 0) > 0:
            tags.append(f"earn({earn.get('beat_rate',0)*100:.0f}%beat,{earn.get('avg_surprise_pct',0):.1f}%surp)")

        lines.append(f"- {e['ticker']} (score {e['total_score']}, {e['active_signals']} signals): {' '.join(tags)}")

    return "\n".join(lines)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Aborted.", flush=True)
        sys.exit(1)
