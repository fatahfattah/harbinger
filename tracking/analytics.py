import json, os, csv
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.dirname(__file__))
RUNS_DIR = os.path.join(HERE, "runs")
ANALYTICS_PATH = os.path.join(RUNS_DIR, "analytics.json")

SIGNAL_COLS = ["Val_Score", "Insider_Score", "13F_Score", "Social_Score", "Cat_Score", "Tech_Score", "Niche_Score"]
SIGNAL_THRESHOLD = 3.0


class Analytics:
    def __init__(self):
        self.data = {}

    def compute(self):
        rows = self._collect_rows()
        if not rows:
            return {}

        sig_dist = self._signal_distribution(rows)
        arch_dist = self._archetype_distribution(rows)
        conv = self._signal_convergence(rows)
        sector = self._sector_analysis(rows)
        score_dist = self._score_distribution(rows)
        top_pairs = self._top_signal_pairs(rows)

        self.data = {
            "total_picks": len(rows),
            "total_runs": len(set(r["_run"] for r in rows)),
            "total_tickers": len(set(r["Ticker"] for r in rows)),
            "signal_distribution": sig_dist,
            "archetype_distribution": arch_dist,
            "signal_convergence": conv,
            "sector_analysis": sector,
            "score_distribution": score_dist,
            "top_signal_pairs": top_pairs,
        }
        return self.data

    def _collect_rows(self):
        rows = []
        for fname in sorted(os.listdir(RUNS_DIR), reverse=True):
            if not (fname.startswith("scan_") and fname.endswith(".csv")):
                continue
            path = os.path.join(RUNS_DIR, fname)
            try:
                with open(path) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        row["_run"] = fname
                        for col in SIGNAL_COLS + ["Score"]:
                            try:
                                row[col] = float(row.get(col, 0) or 0)
                            except ValueError:
                                row[col] = 0.0
                        rows.append(row)
            except Exception:
                pass
        return rows

    def _signal_distribution(self, rows):
        dist = {}
        for col in SIGNAL_COLS:
            name = col.replace("_Score", "")
            vals = [r[col] for r in rows]
            active = sum(1 for v in vals if v >= SIGNAL_THRESHOLD)
            avg = sum(vals) / len(vals) if vals else 0
            dist[name] = {
                "avg": round(avg, 2),
                "active": active,
                "pct_active": round(active / len(rows) * 100, 1) if rows else 0,
                "max": round(max(vals), 2) if vals else 0,
            }
        return dist

    def _archetype_distribution(self, rows):
        arch = defaultdict(lambda: {"count": 0, "scores": []})
        for r in rows:
            pat = r.get("Pattern", "Novel") or "Novel"
            sim = r.get("Pattern_Sim", "")
            arch[pat]["count"] += 1
            arch[pat]["scores"].append(r["Score"])
        result = {}
        for pat, d in sorted(arch.items(), key=lambda x: -x[1]["count"]):
            scores = d["scores"]
            result[pat] = {
                "count": d["count"],
                "pct": round(d["count"] / len(rows) * 100, 1),
                "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
                "max_score": round(max(scores), 2) if scores else 0,
            }
        return result

    def _signal_convergence(self, rows):
        conv = defaultdict(lambda: {"count": 0, "scores": []})
        for r in rows:
            active = sum(1 for col in SIGNAL_COLS if r[col] >= SIGNAL_THRESHOLD)
            conv[str(active)]["count"] += 1
            conv[str(active)]["scores"].append(r["Score"])
        result = {}
        for k in sorted(conv.keys(), key=int):
            d = conv[k]
            scores = d["scores"]
            result[k] = {
                "count": d["count"],
                "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
                "max_score": round(max(scores), 2) if scores else 0,
            }
        return result

    def _sector_analysis(self, rows):
        sectors = defaultdict(lambda: {"count": 0, "scores": []})
        for r in rows:
            sec = r.get("Sector", "Unknown") or "Unknown"
            sectors[sec]["count"] += 1
            sectors[sec]["scores"].append(r["Score"])
        result = {}
        for sec, d in sorted(sectors.items(), key=lambda x: -x[1]["count"]):
            scores = d["scores"]
            result[sec] = {
                "count": d["count"],
                "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
                "max_score": round(max(scores), 2) if scores else 0,
            }
        return result

    def _score_distribution(self, rows):
        buckets = defaultdict(int)
        for r in rows:
            s = min(int(r["Score"]), 10)
            buckets[s] += 1
        return {str(i): buckets[i] for i in range(11)}

    def _top_signal_pairs(self, rows, top_n=10):
        pairs = Counter()
        for r in rows:
            active = [col.replace("_Score", "") for col in SIGNAL_COLS if r[col] >= SIGNAL_THRESHOLD]
            for i in range(len(active)):
                for j in range(i + 1, len(active)):
                    pair = tuple(sorted([active[i], active[j]]))
                    pairs[pair] += 1
        return [{"pair": list(k), "count": v} for k, v in pairs.most_common(top_n)]

    def save(self):
        os.makedirs(os.path.dirname(ANALYTICS_PATH), exist_ok=True)
        with open(ANALYTICS_PATH, "w") as f:
            json.dump(self.data, f, indent=2)
        return ANALYTICS_PATH

    def load(self):
        if os.path.exists(ANALYTICS_PATH):
            with open(ANALYTICS_PATH) as f:
                self.data = json.load(f)
        return self.data


def cli(args=None):
    import argparse
    parser = argparse.ArgumentParser(prog="track analytics")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("rebuild")

    args = parser.parse_args(args[1:] if args else sys.argv[1:])
    an = Analytics()

    if args.cmd == "rebuild":
        an.compute()
        path = an.save()
        d = an.data
        print(f"  {d['total_picks']} picks across {d['total_runs']} runs ({d['total_tickers']} tickers)")
        print()
        print("  Signal Distribution:")
        for name, sd in d["signal_distribution"].items():
            print(f"    {name:>12s}: avg={sd['avg']:.2f}  active={sd['active']} ({sd['pct_active']}%)")
        print()
        print("  Archetype Distribution:")
        for pat, ad in d["archetype_distribution"].items():
            print(f"    {pat:>12s}: {ad['count']} ({ad['pct']}%)  avg={ad['avg_score']}  max={ad['max_score']}")
        print()
        print("  Signal Convergence:")
        for k, cd in sorted(d["signal_convergence"].items(), key=lambda x: int(x[0])):
            print(f"    {k} signals: {cd['count']} picks  avg={cd['avg_score']}  max={cd['max_score']}")
        print()
        print("  Top Signal Pairs:")
        for sp in d["top_signal_pairs"][:5]:
            print(f"    {' + '.join(sp['pair']):>25s}: {sp['count']} picks")
        print(f"  saved: {path}")
    else:
        parser.print_help()
