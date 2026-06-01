import json, os, sys
from datetime import datetime

HERE = os.path.dirname(os.path.dirname(__file__))
WATCHLIST_PATH = os.path.join(HERE, "runs", "watchlist.json")


class Watchlist:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(WATCHLIST_PATH):
            with open(WATCHLIST_PATH) as f:
                return json.load(f)
        return {"tickers": {}}

    def _save(self):
        os.makedirs(os.path.dirname(WATCHLIST_PATH), exist_ok=True)
        with open(WATCHLIST_PATH, "w") as f:
            json.dump(self.data, f, indent=2)

    def add(self, ticker, reason="", signals=None, tags=None):
        ticker = ticker.upper()
        if ticker in self.data["tickers"]:
            return False, f"{ticker} already in watchlist"
        self.data["tickers"][ticker] = {
            "added": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "reason": reason,
            "signals": signals or [],
            "tags": tags or [],
            "decisions": [],
            "price": None,
        }
        self._save()
        return True, f"{ticker} added to watchlist"

    def remove(self, ticker):
        ticker = ticker.upper()
        if ticker not in self.data["tickers"]:
            return False, f"{ticker} not in watchlist"
        del self.data["tickers"][ticker]
        self._save()
        return True, f"{ticker} removed from watchlist"

    def add_decision(self, ticker, action, size_pct=None, price=None, notes=""):
        ticker = ticker.upper()
        if ticker not in self.data["tickers"]:
            return False, f"{ticker} not in watchlist"
        entry = self.data["tickers"][ticker]
        decision = {
            "date": datetime.now().strftime("%Y%m%d"),
            "action": action,
            "size_pct": size_pct,
            "price": price,
            "notes": notes,
        }
        entry["decisions"].append(decision)
        if price is not None:
            entry["price"] = price
        self._save()
        return True, f"Decision recorded for {ticker}: {action}"

    def list(self):
        return self.data["tickers"]

    def get(self, ticker):
        return self.data["tickers"].get(ticker.upper())


def cli(args=None):
    import argparse
    parser = argparse.ArgumentParser(prog="track watchlist")
    sub = parser.add_subparsers(dest="cmd")

    p_add = sub.add_parser("add")
    p_add.add_argument("ticker")
    p_add.add_argument("--reason", default="")
    p_add.add_argument("--signals", nargs="*", default=[])
    p_add.add_argument("--tags", nargs="*", default=[])

    p_rm = sub.add_parser("remove")
    p_rm.add_argument("ticker")

    p_dec = sub.add_parser("decision")
    p_dec.add_argument("ticker")
    p_dec.add_argument("--action", required=True, choices=["buy", "sell", "skip", "add", "trim"])
    p_dec.add_argument("--size", type=float, default=None)
    p_dec.add_argument("--price", type=float, default=None)
    p_dec.add_argument("--notes", default="")

    p_ls = sub.add_parser("list")

    args = parser.parse_args(args[1:] if args else sys.argv[1:])
    wl = Watchlist()

    if args.cmd == "add":
        ok, msg = wl.add(args.ticker, args.reason, args.signals, args.tags)
        print(f"  {'OK' if ok else 'FAIL'} {msg}")
    elif args.cmd == "remove":
        ok, msg = wl.remove(args.ticker)
        print(f"  {'OK' if ok else 'FAIL'} {msg}")
    elif args.cmd == "decision":
        ok, msg = wl.add_decision(args.ticker, args.action, args.size, args.price, args.notes)
        print(f"  {'OK' if ok else 'FAIL'} {msg}")
    elif args.cmd == "list":
        items = wl.list()
        if not items:
            print("  (empty)")
            return
        for t, e in sorted(items.items()):
            decisions = len(e.get("decisions", []))
            signals = ", ".join(e.get("signals", [])) or "-"
            print(f"  {t:8s}  {signals:30s}  {decisions} decisions  {e.get('reason', '')[:40]}")
    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
