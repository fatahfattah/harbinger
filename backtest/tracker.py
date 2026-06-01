import os
import csv
import json
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict

RUNS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runs")
RESULTS_PATH = os.path.join(RUNS_DIR, "backtest_results.json")
SPY = "SPY"
FORWARD_WINDOWS = [14, 30, 60, 90]

DEFAULT_WEIGHTS = {
    "valuation": 0.18, "insider": 0.15, "fund_13f": 0.18,
    "social": 0.05, "catalyst": 0.09, "technicals": 0.20, "niche": 0.15,
}


def _parse_scan_date(csv_name):
    ts = csv_name.replace("scan_", "").replace(".csv", "")
    try:
        return datetime.strptime(ts[:8], "%Y%m%d")
    except ValueError:
        return None


def _get_forward_prices(ticker, scan_date, windows):
    try:
        end = scan_date + timedelta(days=max(windows) + 5)
        hist = yf.download(ticker, start=scan_date, end=end, progress=False, auto_adjust=True)
        if hist.empty:
            return {}
        prices = hist["Close"]
        scan_price = None
        if scan_date.strftime("%Y-%m-%d") in prices.index:
            scan_price = float(prices.loc[scan_date.strftime("%Y-%m-%d")])
        else:
            for i in range(1, 10):
                d = (scan_date + timedelta(days=i)).strftime("%Y-%m-%d")
                if d in prices.index:
                    scan_price = float(prices.loc[d])
                    break
        if scan_price is None or scan_price <= 0:
            return {}
        result = {"scan_price": scan_price, "ticker": ticker}
        for w in windows:
            target = scan_date + timedelta(days=w)
            target_price = None
            for offset in range(-2, 6):
                d = (target + timedelta(days=offset)).strftime("%Y-%m-%d")
                if d in prices.index:
                    target_price = float(prices.loc[d])
                    break
            if target_price and target_price > 0:
                result[f"ret_{w}d"] = (target_price - scan_price) / scan_price
        return result
    except Exception:
        return {}


def _get_benchmark(scan_date, windows):
    return _get_forward_prices(SPY, scan_date, windows)


def _load_runs():
    runs = []
    if not os.path.isdir(RUNS_DIR):
        return runs
    for f in sorted(os.listdir(RUNS_DIR), reverse=True):
        if f.startswith("scan_") and f.endswith(".csv"):
            path = os.path.join(RUNS_DIR, f)
            date = _parse_scan_date(f)
            if date is None:
                continue
            rows = []
            with open(path) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    rows.append(row)
            if not rows:
                continue
            runs.append({"file": f, "date": date, "rows": rows})
    return runs


def compute_score_quartile(score, min_s, max_s):
    if max_s == min_s:
        return 2
    pct = (score - min_s) / (max_s - min_s) * 100
    if pct >= 75:
        return 3
    if pct >= 50:
        return 2
    if pct >= 25:
        return 1
    return 0


def track(existing_only=False):
    runs = _load_runs()
    if not runs:
        print("No scan runs found.")
        return

    all_runs_data = []
    all_trades = []
    all_benchmarks = []

    for run in runs:
        rows = run["rows"]
        scores = [float(r.get("Score", 0)) for r in rows if r.get("Score")]
        if not scores:
            continue
        min_s, max_s = min(scores), max(scores)
        date_str = run["date"].strftime("%Y-%m-%d")

        print(f"  {run['file']}: {len(rows)} picks, date={date_str}")

        tickers = [r["Ticker"] for r in rows if r.get("Ticker")]
        if not tickers:
            continue

        benchmark = _get_benchmark(run["date"], FORWARD_WINDOWS)
        all_benchmarks.append({"date": date_str, "file": run["file"], **benchmark})

        for r in rows:
            score = float(r.get("Score", 0))
            quartile = compute_score_quartile(score, min_s, max_s)
            ticker = r.get("Ticker", "")
            fp = _get_forward_prices(ticker, run["date"], FORWARD_WINDOWS)
            if fp:
                entry = {
                    "date": date_str,
                    "file": run["file"],
                    "ticker": ticker,
                    "score": score,
                    "quartile": quartile,
                    "scan_price": fp.get("scan_price", 0),
                }
                for w in FORWARD_WINDOWS:
                    key = f"ret_{w}d"
                    if key in fp:
                        entry[key] = fp[key]
                all_trades.append(entry)

        run_result = {
            "date": date_str,
            "file": run["file"],
            "total_picks": len(rows),
            "traded": sum(1 for t in all_trades if t["file"] == run["file"]),
            "benchmark": {
                "scan_price": benchmark.get("scan_price", 0),
                "forward": {f"ret_{w}d": benchmark.get(f"ret_{w}d") for w in FORWARD_WINDOWS},
            },
        }
        all_runs_data.append(run_result)

    result = _aggregate(all_runs_data, all_trades, all_benchmarks)
    _save(result)
    return result


def _aggregate(runs_data, trades, benchmarks):
    by_quartile = defaultdict(list)
    for t in trades:
        by_quartile[t["quartile"]].append(t)

    quartile_stats = {}
    for q in range(4):
        group = by_quartile.get(q, [])
        if not group:
            continue
        stats = {"count": len(group)}
        for w in FORWARD_WINDOWS:
            key = f"ret_{w}d"
            vals = [t[key] for t in group if key in t]
            if vals:
                stats[key] = {
                    "avg": sum(vals) / len(vals),
                    "median": sorted(vals)[len(vals) // 2],
                    "positive": sum(1 for v in vals if v > 0) / len(vals),
                    "best": max(vals),
                    "worst": min(vals),
                    "count": len(vals),
                }
        quartile_stats[f"Q{q}"] = stats

    total_traded = len(trades)
    total_in_run = sum(r["total_picks"] for r in runs_data)

    bench_avg = {}
    for w in FORWARD_WINDOWS:
        key = f"ret_{w}d"
        vals = [b[key] for b in benchmarks if key in b and b.get(key) is not None]
        if vals:
            bench_avg[key] = sum(vals) / len(vals)

    all_forward = defaultdict(list)
    for t in trades:
        for w in FORWARD_WINDOWS:
            key = f"ret_{w}d"
            if key in t:
                all_forward[key].append(t[key])

    universe_avg = {}
    for w in FORWARD_WINDOWS:
        key = f"ret_{w}d"
        vals = all_forward.get(key, [])
        if vals:
            universe_avg[key] = sum(vals) / len(vals)

    return {
        "summary": {
            "total_runs": len(runs_data),
            "total_picks_in_runs": total_in_run,
            "total_traded": total_traded,
            "traded_pct": round(total_traded / total_in_run * 100, 1) if total_in_run else 0,
            "benchmark_avg": bench_avg,
            "universe_avg": universe_avg,
            "quartile": quartile_stats,
            "top_vs_bottom": _top_vs_bottom(quartile_stats),
        },
        "runs": runs_data,
    }


def _top_vs_bottom(quartile_stats):
    result = {}
    for w in FORWARD_WINDOWS:
        key = f"ret_{w}d"
        q3 = quartile_stats.get("Q3", {}).get(key, {})
        q0 = quartile_stats.get("Q0", {}).get(key, {})
        if q3.get("avg") is not None and q0.get("avg") is not None:
            result[f"{w}d"] = {
                "top_avg": q3["avg"],
                "bottom_avg": q0["avg"],
                "outperformance": q3["avg"] - q0["avg"],
            }
        elif q3.get("avg") is not None:
            result[f"{w}d"] = {"top_avg": q3["avg"], "bottom_avg": None, "outperformance": None}
    return result


def _save(result):
    os.makedirs(RUNS_DIR, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResults saved: {RESULTS_PATH}")


def load_results():
    if os.path.exists(RESULTS_PATH):
        with open(RESULTS_PATH) as f:
            return json.load(f)
    return None
