import json, os, csv
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(__file__))
RUNS_DIR = os.path.join(HERE, "runs")
HISTORY_PATH = os.path.join(RUNS_DIR, "ticker_history.json")

SIGNAL_COLS = [
    "Score", "Val_Score", "Insider_Score", "13F_Score",
    "Social_Score", "Cat_Score", "Tech_Score", "Niche_Score",
]

DETAIL_COLS = ["Price", "Pattern", "Active_Signals", "RSI", "Ret_1m", "Ret_3m"]


class TickerHistory:
    def __init__(self):
        self.data = {}

    def rebuild(self):
        self.data = {}
        scans = sorted(
            [f for f in os.listdir(RUNS_DIR) if f.startswith("scan_") and f.endswith(".csv")],
            reverse=True,
        )
        for fname in scans:
            ts = fname[5:-4]
            path = os.path.join(RUNS_DIR, fname)
            try:
                with open(path) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ticker = row.get("Ticker", "").upper()
                        if not ticker:
                            continue
                        entry = {"timestamp": ts}
                        for col in SIGNAL_COLS + DETAIL_COLS:
                            val = row.get(col, "")
                            if col in SIGNAL_COLS + ["Score", "RSI", "Ret_1m", "Ret_3m", "Price"]:
                                try:
                                    val = float(val) if val else None
                                except ValueError:
                                    val = None
                            elif col == "Active_Signals":
                                try:
                                    val = int(val) if val else 0
                                except ValueError:
                                    val = 0
                            entry[col] = val
                        if ticker not in self.data:
                            self.data[ticker] = []
                        self.data[ticker].append(entry)
            except Exception:
                pass

        result = {}
        for ticker, history in self.data.items():
            history.sort(key=lambda x: x["timestamp"], reverse=True)
            scores = [h.get("Score") for h in history if h.get("Score") is not None]
            result[ticker] = {
                "history": history,
                "trends": {
                    "num_scans": len(history),
                    "first_seen": history[-1]["timestamp"] if len(history) > 1 else history[0]["timestamp"],
                    "last_seen": history[0]["timestamp"],
                    "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
                    "max_score": max(scores) if scores else None,
                    "min_score": min(scores) if scores else None,
                    "score_delta_1d": self._compute_delta(history, 1),
                    "score_delta_3d": self._compute_delta(history, 3),
                },
            }
        self.data = result
        return result

    def _compute_delta(self, history, max_gap):
        if len(history) < 2:
            return None
        s0 = history[0].get("Score")
        for h in history[1:max_gap + 1]:
            s1 = h.get("Score")
            if s0 is not None and s1 is not None:
                return round(s0 - s1, 1)
        return None

    def save(self):
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        with open(HISTORY_PATH, "w") as f:
            json.dump(self.data, f, indent=2)
        return HISTORY_PATH

    def load(self):
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH) as f:
                self.data = json.load(f)
        return self.data


def cli(args=None):
    import argparse
    parser = argparse.ArgumentParser(prog="track history")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("rebuild")
    p_show = sub.add_parser("show")
    p_show.add_argument("ticker", nargs="?", default=None)

    args = parser.parse_args(args[1:] if args else sys.argv[1:])
    th = TickerHistory()

    if args.cmd == "rebuild":
        th.rebuild()
        path = th.save()
        tickers = len(th.data)
        scans = sum(len(v["history"]) for v in th.data.values())
        print(f"  {tickers} tickers, {scans} scan entries")
        print(f"  saved: {path}")
    elif args.cmd == "show":
        th.load()
        if args.ticker:
            ticker = args.ticker.upper()
            d = th.data.get(ticker)
            if not d:
                print(f"  {ticker} not found in history")
                return
            print(f"  {ticker}")
            print(f"  scans: {d['trends']['num_scans']}, avg: {d['trends']['avg_score']}, "
                  f"max: {d['trends']['max_score']}, min: {d['trends']['min_score']}")
            if d['trends']['score_delta_1d'] is not None:
                print(f"  1d delta: {d['trends']['score_delta_1d']:+.1f}")
            if d['trends']['score_delta_3d'] is not None:
                print(f"  3d delta: {d['trends']['score_delta_3d']:+.1f}")
            print()
            for h in d["history"][:5]:
                print(f"  {h['timestamp']}  score={h.get('Score',''):>5}  "
                      f"pattern={h.get('Pattern',''):>10}  price={h.get('Price','')}")
        else:
            print(f"  {len(th.data)} tickers in history")
            for t, d in sorted(th.data.items(), key=lambda x: -x[1]["trends"]["num_scans"])[:20]:
                print(f"  {t:8s}  {d['trends']['num_scans']:2d} scans  "
                      f"avg={d['trends']['avg_score']}  max={d['trends']['max_score']}")
    else:
        parser.print_help()
