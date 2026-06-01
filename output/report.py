import os
import csv
import json
from datetime import datetime
from tracking.outcomes import record_scan


def print_report(scored, llm_analysis, config, metadata=None, cross_val=None):
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    separator = "=" * 74

    print()
    print(separator)
    print(f"  HARBINGER — Daily Signal Scan")
    print(f"  {date_str}")
    print(separator)
    print()

    top = scored[:config.TOP_N]
    if not top:
        print("  No strong signals detected today.")
        print()
        return

    print(f"  TOP {len(top)} SIGNALS")
    print(f"  {'TICKER':<8} {'SCORE':<7} {'VAL':<5} {'INS':<6} {'13F':<5} {'SOC':<5} {'CAT':<5} {'TECH':<5} {'NIC':<5} {'SI':<5} {'EARN':<5} {'FH':<5} {'AN':<5} {'INST':<5} {'DIV':<5} {'SEA':<5} {'MAC':<5} {'SIGNALS'}")
    print(f"  {'─'*8} {'─'*7} {'─'*5} {'─'*6} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*40}")

    for i, entry in enumerate(top):
        t = entry["ticker"]
        ts = entry["total_score"]
        scores = entry["scores"]
        details = entry["details"]

        val_s = scores.get("valuation", 0)
        ins_s = scores.get("insider", 0)
        f13f_s = scores.get("fund_13f", 0)
        soc_s = scores.get("social", 0)
        cat_s = scores.get("catalyst", 0)
        tech_s = scores.get("technicals", 0)
        nic_s = scores.get("niche", 0)
        si_s = scores.get("short_interest", 0)
        earn_s = scores.get("earnings", 0)
        fh_s = scores.get("financial_health", 0)
        an_s = scores.get("analyst_targets", 0)
        inst_s = scores.get("institutional", 0)
        div_s = scores.get("dividend_quality", 0)
        sea_s = scores.get("seasonality", 0)
        mac_s = scores.get("macro_exposure", 0)
        sm_boost = entry.get("sector_momentum_boost", 0)
        ca_boost = entry.get("convergence_amplifier", 0)

        tags = []
        val_d = details.get("valuation", {})
        if val_d:
            sn = val_d.get("signals", [])
            for s in sn[:2]:
                tags.append(s)
            if val_d.get("name"):
                tags.insert(0, val_d["name"][:16])

        niche_d = details.get("niche", {})
        if niche_d and niche_d.get("niche_mentions", 0) > 0:
            kws = ",".join(niche_d.get("keywords", [])[:1])
            tags.append(f"niche({niche_d['niche_mentions']:.0f})")

        ins_d = details.get("insider", {})
        if ins_d and ins_d.get("net", 0) > 0:
            nv = ins_d.get("net_value", 0)
            if nv >= 1_000_000:
                tags.append(f"ins+${nv/1e6:.1f}M")
            elif nv >= 1_000:
                tags.append(f"ins+${nv/1e3:.0f}K")
            else:
                tags.append(f"ins+{ins_d['net']}")
            txs = ins_d.get("transactions", [])
            if txs:
                buys = [t for t in txs if t.get("code") == "P"]
                if buys:
                    best = max(buys, key=lambda t: t.get("value", 0))
                    tags.append(f"by {best.get('name','?').split()[-1]}")

        f13f_d = details.get("fund_13f", {})
        if f13f_d and f13f_d.get("new_funds", 0) > 0:
            tags.append(f"+{f13f_d['new_funds']}f")

        soc_d = details.get("social", {})
        if soc_d and soc_d.get("mentions", 0) > 0:
            tags.append(f"{soc_d['mentions']}rdt")

        cat_d = details.get("catalyst", {})
        if cat_d and cat_d.get("events"):
            first = cat_d["events"][0][:10].replace("news:","").replace("8-K:","")
            tags.append(first)

        tech_d = details.get("technicals", {})
        if tech_d:
            pct_high = tech_d.get("pct_from_high")
            if pct_high is not None and pct_high < 10:
                tags.append(f"52wH")
            sigs = tech_d.get("signals", [])
            for s in sigs[:1]:
                if s not in [x for x in tags]:
                    tags.append(s)

        si_d = details.get("short_interest", {})
        if si_d:
            sp = si_d.get("short_pct", 0)
            if sp > 10:
                tags.append(f"SI{sp:.0f}%")

        earn_d = details.get("earnings", {})
        if earn_d and earn_d.get("total_quarters", 0) > 0:
            tags.append(f"earn{earn_d['beat_rate']*100:.0f}%")

        fh_d = details.get("financial_health", {})
        if fh_d and fh_d.get("signals"):
            sigs = fh_d["signals"]
            if "high_debt" in sigs or "very_high_debt" in sigs:
                tags.append("high_debt")
            if "unprofitable" in sigs:
                tags.append("unprofitable")
            if "pos_fcf" in sigs:
                tags.append("pos_fcf")

        an_d = details.get("analyst_targets", {})
        if an_d and an_d.get("total_analysts", 0) >= 3:
            tags.append(f"an+{an_d['total_analysts']}")
        if an_d and an_d.get("pt_upside_pct") and an_d["pt_upside_pct"] > 30:
            tags.append(f"pt+{an_d['pt_upside_pct']:.0f}%")

        inst_d = details.get("institutional", {})
        if inst_d:
            sigs = inst_d.get("signals", [])
            if "inst_accumulation" in sigs:
                tags.append("inst_acc")
            if "high_inst_own" in sigs:
                tags.append("inst_hi")

        div_d = details.get("dividend_quality", {})
        if div_d:
            if div_d.get("dividend_yield") and div_d["dividend_yield"] > 1:
                tags.append(f"yld{div_d['dividend_yield']:.1f}%")
            sigs = div_d.get("signals", [])
            if "high_gross_margin" in sigs:
                tags.append("hi_gm")

        sea_d = details.get("seasonality", {})
        if sea_d and sea_d.get("seasonality_strength") == "strong":
            tags.append(f"sea+{sea_d['best_month']}")

        mac_d = details.get("macro_exposure", {})
        if mac_d and mac_d.get("score", 0) >= 6:
            tags.append(f"macro{mac_d['score']:.0f}")
        mx_sigs = mac_d.get("signals", []) if mac_d else []
        if "asia_exposure" in mx_sigs:
            tags.append("asia")
        if "rate_sensitive" in mx_sigs:
            tags.append("rate")
        if "commodity_sensitive" in mx_sigs:
            tags.append("comm")

        if sm_boost >= 1:
            tags.append(f"se+{sm_boost:.1f}")
        if ca_boost >= 1:
            tags.append(f"conv")

        tag_str = " ".join(tags[:5]) if tags else ""
        tag_str = tag_str[:36]

        def fmt(v):
            return f"{v:<5.1f}" if v else " " * 5

        print(f"  {t:<8} {ts:<7.1f} {fmt(val_s)} {fmt(ins_s)} {fmt(f13f_s)} {fmt(soc_s)} {fmt(cat_s)} {fmt(tech_s)} {fmt(nic_s)} {fmt(si_s)} {fmt(earn_s)} {fmt(fh_s)} {fmt(an_s)} {fmt(inst_s)} {fmt(div_s)} {fmt(sea_s)} {fmt(mac_s)} {tag_str}")

    print()

    if llm_analysis:
        print(f"  ── LLM NARRATIVES ──")
        print()
        for line in llm_analysis.strip().split("\n"):
            print(f"  {line}")
        print()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = _write_csv(top, config, ts)
    meta_path = _write_metadata(scored, llm_analysis, config, metadata, ts, csv_path, cross_val=cross_val)
    record_scan(scored, config, metadata)
    print(f"  Data saved: {csv_path}")
    if meta_path:
        print(f"  Metadata:   {meta_path}")
    print()


def _write_csv(scored, config, ts):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, f"scan_{ts}.csv")

    if isinstance(scored, dict):
        scored = [scored]

    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Ticker", "Score", "Val_Score", "Insider_Score", "13F_Score",
            "Social_Score", "Cat_Score", "Tech_Score", "Niche_Score", "Short_Score", "Earnings_Score", "FH_Score", "AN_Score", "Inst_Score", "Div_Score", "Sea_Score", "Mac_Score",
            "Active_Signals",
            "Pattern", "Pattern_Sim",
            "Name", "Price", "Sector", "Fwd_PE", "Rev_Growth",
            "Insider_Buys", "Insider_Sells", "Insider_Net",
            "Insider_Buy_Value", "Insider_Sell_Value", "Insider_Net_Value",
            "Insider_Transactions",
            "New_Funds", "Fund_Names",
            "Reddit_Mentions",
            "Niche_Mentions", "Niche_Keywords", "Niche_Communities",
            "Catalyst_Events",
            "Ret_1m", "Ret_3m", "RSI", "Vol_Ratio",
            "Above_50ma", "Above_200ma", "Pct_From_High",
            "Short_Pct", "Short_Ratio", "Short_Change",
            "Beat_Rate", "Avg_Surprise_Pct",
            "D/E", "Current_Ratio", "Profit_Margin", "ROE", "FH_Signals",
            "Price_Target", "PT_Upside", "AN_Consensus", "AN_Analysts",
            "Inst_Pct", "Holder_Count", "Inst_Change", "Inst_Signals",
            "Div_Yield", "Payout_Ratio", "Beta", "Gross_Margin", "Div_Signals",
            "Sea_Profile", "Sea_Best", "Sea_Best_Avg", "Sea_Hit_Rate",
            "Mac_FX", "Mac_Rate", "Mac_Comm", "Mac_Asia", "Mac_Signals",
            "Sector_Momentum_Boost", "Convergence_Amp",
            "Early_Stage_Score",
        ])
        for e in scored:
            if not isinstance(e, dict):
                continue
            det = e["details"]
            v = det.get("valuation", {})
            ins = det.get("insider", {})
            f13f = det.get("fund_13f", {})
            soc = det.get("social", {})
            cat = det.get("catalyst", {})
            tech = det.get("technicals", {})
            niche = det.get("niche", {})
            si = det.get("short_interest", {})
            earn = det.get("earnings", {})
            fh = det.get("financial_health", {})
            an = det.get("analyst_targets", {})
            inst = det.get("institutional", {})
            div = det.get("dividend_quality", {})
            sea = det.get("seasonality", {})
            mac = det.get("macro_exposure", {})

            w.writerow([
                e["ticker"], e["total_score"],
                e["scores"].get("valuation", 0),
                e["scores"].get("insider", 0),
                e["scores"].get("fund_13f", 0),
                e["scores"].get("social", 0),
                e["scores"].get("catalyst", 0),
                e["scores"].get("technicals", 0),
                e["scores"].get("niche", 0),
                e["scores"].get("short_interest", 0),
                e["scores"].get("earnings", 0),
                e["scores"].get("financial_health", 0),
                e["scores"].get("analyst_targets", 0),
                e["scores"].get("institutional", 0),
                e["scores"].get("dividend_quality", 0),
                e["scores"].get("seasonality", 0),
                e["scores"].get("macro_exposure", 0),
                e["active_signals"],
                e.get("archetype", ""),
                e.get("archetype_similarity", 0),
                v.get("name", ""),
                v.get("price", ""),
                v.get("sector", ""),
                v.get("fwd_pe", ""),
                v.get("rev_growth", ""),
                ins.get("buys", 0),
                ins.get("sells", 0),
                ins.get("net", 0),
                ins.get("buy_value", 0),
                ins.get("sell_value", 0),
                ins.get("net_value", 0),
                json.dumps(ins.get("transactions", [])),
                f13f.get("new_funds", 0),
                ", ".join(f13f.get("fund_names", [])),
                soc.get("mentions", 0),
                niche.get("niche_mentions", 0),
                ", ".join(niche.get("keywords", [])),
                ", ".join(niche.get("communities", [])),
                "; ".join(cat.get("events", [])),
                tech.get("ret_1m", ""),
                tech.get("ret_3m", ""),
                tech.get("rsi", ""),
                tech.get("vol_ratio", ""),
                tech.get("above_50ma", ""),
                tech.get("above_200ma", ""),
                tech.get("pct_from_high", ""),
                si.get("short_pct", 0),
                si.get("short_ratio", 0),
                si.get("short_change", ""),
                earn.get("beat_rate", 0),
                earn.get("avg_surprise_pct", 0),
                fh.get("debt_to_equity", ""),
                fh.get("current_ratio", ""),
                fh.get("profit_margin", ""),
                fh.get("return_on_equity", ""),
                ", ".join(fh.get("signals", [])),
                an.get("price_target", ""),
                an.get("pt_upside_pct", ""),
                an.get("consensus", ""),
                an.get("total_analysts", 0),
                inst.get("inst_pct", ""),
                inst.get("holder_count", ""),
                inst.get("avg_change", ""),
                ", ".join(inst.get("signals", [])),
                div.get("dividend_yield", ""),
                div.get("payout_ratio", ""),
                div.get("beta", ""),
                div.get("gross_margin", ""),
                ", ".join(div.get("signals", [])),
                sea.get("profile", ""),
                sea.get("best_month", ""),
                sea.get("best_month_avg", ""),
                sea.get("best_hit_rate", ""),
                mac.get("fx_score", 0),
                mac.get("rate_score", 0),
                mac.get("commodity_score", 0),
                mac.get("asia_score", 0),
                ", ".join(mac.get("signals", [])),
                e.get("sector_momentum_boost", 0),
                e.get("convergence_amplifier", 0),
                e.get("early_stage_score", 0),
            ])

    return path


def _write_metadata(scored, llm_analysis, config, metadata, ts, csv_path, cross_val=None):
    if not metadata:
        metadata = {}
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    path = os.path.join(config.OUTPUT_DIR, f"run_{ts}.json")

    if isinstance(scored, dict):
        scored = [scored]
    top = scored[:config.TOP_N] if scored else []
    top_data = []
    for e in top:
        if not isinstance(e, dict):
            continue
        det = e.get("details", {})
        v = det.get("valuation", {})
        ins = det.get("insider", {})
        f13f = det.get("fund_13f", {})
        soc = det.get("social", {})
        cat = det.get("catalyst", {})
        tech = det.get("technicals", {})
        niche = det.get("niche", {})
        si = det.get("short_interest", {})
        earn = det.get("earnings", {})

        top_data.append({
            "ticker": e["ticker"],
            "total_score": e["total_score"],
            "active_signals": e["active_signals"],
            "archetype": e.get("archetype", ""),
            "archetype_similarity": e.get("archetype_similarity", 0),
            "scores": {
                "valuation": e["scores"].get("valuation", 0),
                "insider": e["scores"].get("insider", 0),
                "fund_13f": e["scores"].get("fund_13f", 0),
                "social": e["scores"].get("social", 0),
                "catalyst": e["scores"].get("catalyst", 0),
                "technicals": e["scores"].get("technicals", 0),
                "niche": e["scores"].get("niche", 0),
                "short_interest": e["scores"].get("short_interest", 0),
                "earnings": e["scores"].get("earnings", 0),
            },
            "details": {
                "name": v.get("name", ""),
                "price": v.get("price", ""),
                "sector": v.get("sector", ""),
                "fwd_pe": str(v.get("fwd_pe", "")),
                "rev_growth": v.get("rev_growth", ""),
                "insider_net": ins.get("net", 0),
                "insider_buy_value": ins.get("buy_value", 0),
                "insider_sell_value": ins.get("sell_value", 0),
                "insider_net_value": ins.get("net_value", 0),
                "insider_transactions": ins.get("transactions", []),
                "new_funds": f13f.get("new_funds", 0),
                "fund_names": f13f.get("fund_names", []),
                "mentions": soc.get("mentions", 0),
                "events": cat.get("events", []),
                "ret_1m": tech.get("ret_1m", ""),
                "ret_3m": tech.get("ret_3m", ""),
                "rsi": tech.get("rsi", ""),
                "vol_ratio": tech.get("vol_ratio", ""),
                "niche_mentions": niche.get("niche_mentions", 0),
                "niche_keywords": niche.get("keywords", []),
                "niche_communities": niche.get("communities", []),
                "short_pct": si.get("short_pct", 0),
                "short_ratio": si.get("short_ratio", 0),
                "short_change": si.get("short_change", ""),
                "pct_from_high": tech.get("pct_from_high", ""),
                "earnings_beat_rate": earn.get("beat_rate", 0),
                "earnings_surprise_pct": earn.get("avg_surprise_pct", 0),
                "early_stage_score": e.get("early_stage_score", 0),
                "sector_momentum_boost": e.get("sector_momentum_boost", 0),
                "convergence_amplifier": e.get("convergence_amplifier", 0),
            },
        })

    data = {
        "timestamp": ts,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "csv_file": os.path.basename(csv_path),
        "top_n": config.TOP_N,
        "llm_enabled": config.LLM_ENABLED,
        "llm_narratives": llm_analysis,
        "llm_cross_validation": cross_val,
        "top_count": len(top),
        "total_scored": len(scored),
        "metadata": metadata,
        "top_picks": top_data,
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return path
