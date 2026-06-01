import math
import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(__file__))
RUNS_DIR = os.path.join(HERE, "runs")
SIM_RESULTS_PATH = os.path.join(RUNS_DIR, "backtest_simulation.json")

# Fixed pool of liquid tickers for simulation (seed list + major holdings)
SIM_TICKERS = [
    "ASTS", "NBIS", "MU", "RKLB", "LUNR", "PLTR", "SOFI", "IONQ", "RXRX",
    "ARM", "CRSP", "BE", "UPST", "AFRM",
    "TEAM", "DDOG", "MDB", "NET", "ZS", "SNOW", "PATH",
    "ALGM", "SITM", "ACLS",
    "RNA", "NTRA", "ALKS",
    "RDW", "GSAT",
    "AMD", "MRVL", "WOLF", "ON", "STM",
    "AMAT", "LRCX", "KLAC", "ENTG",
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META",
]

FORWARD_WINDOWS = [30, 60, 90]
SIM_DAYS_BACK = [60, 90, 120, 180, 270, 365]


def _technicals_as_of(hist, date):
    hist_before = hist[hist.index <= date]
    if len(hist_before) < 20:
        return None

    close = hist_before["Close"]
    volumes = hist_before["Volume"]
    price = float(close.iloc[-1])
    price_1m = float(close.iloc[-min(21, len(close))]) if len(close) >= 21 else float(close.iloc[0])
    price_3m = float(close.iloc[-min(63, len(close))]) if len(close) >= 63 else float(close.iloc[0])
    ret_1m = (price - price_1m) / price_1m
    ret_3m = (price - price_3m) / price_3m
    vol_20d = float(volumes.tail(20).mean())
    vol_today = float(volumes.iloc[-1])
    vol_ratio = vol_today / vol_20d if vol_20d > 0 else 1.0

    if len(close) >= 14:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1])))
    else:
        rsi = 50

    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    above_50ma = float(close.iloc[-1]) > float(sma50.iloc[-1]) if len(sma50) > 0 else False
    above_200ma = float(close.iloc[-1]) > float(sma200.iloc[-1]) if len(sma200) > 0 and not pd.isna(sma200.iloc[-1]) else False

    score = 0
    signals = []
    if ret_1m > 0.05: score += 1.5; signals.append("1m+5%")
    if ret_3m > 0.15: score += 1.5; signals.append("3m+15%")
    if rsi > 50 and rsi < 70: score += 2; signals.append("rsi_bull")
    if rsi < 30: score += 2.5; signals.append("rsi_oversold")
    if vol_ratio > 1.5: score += 1.5; signals.append("high_vol")
    if above_50ma: score += 1; signals.append("above_50ma")
    if above_200ma: score += 1; signals.append("above_200ma")

    return {
        "score": min(score, 10),
        "ret_1m": ret_1m,
        "ret_3m": ret_3m,
        "rsi": rsi,
        "vol_ratio": vol_ratio,
        "above_50ma": above_50ma,
        "above_200ma": above_200ma,
        "price": price,
        "signals": signals,
    }


def _forward_return(hist, buy_date, window_days):
    buy_str = buy_date.strftime("%Y-%m-%d")
    target = buy_date + timedelta(days=window_days)

    buy_price = None
    for offset in range(5):
        d = (buy_date - timedelta(days=offset)).strftime("%Y-%m-%d")
        if d in hist.index:
            buy_price = float(hist.loc[d, "Close"])
            break
    if buy_price is None:
        for offset in range(1, 6):
            d = (buy_date + timedelta(days=offset)).strftime("%Y-%m-%d")
            if d in hist.index:
                buy_price = float(hist.loc[d, "Close"])
                break
    if buy_price is None or buy_price <= 0:
        return None

    sell_price = None
    for offset in range(5):
        d = (target + timedelta(days=offset)).strftime("%Y-%m-%d")
        if d in hist.index:
            sell_price = float(hist.loc[d, "Close"])
            break
    if sell_price is None:
        for offset in range(-1, -6, -1):
            d = (target + timedelta(days=offset)).strftime("%Y-%m-%d")
            if d in hist.index:
                sell_price = float(hist.loc[d, "Close"])
                break
    if sell_price is None or sell_price <= 0:
        return None

    return (sell_price - buy_price) / buy_price


def simulate():
    # Fetch all price history in one batch
    print(f"  Fetching {len(SIM_TICKERS)} tickers...", flush=True)
    hist_all = yf.download(SIM_TICKERS, period="20mo", group_by="ticker", auto_adjust=True, progress=False)

    results = []
    now = datetime.now()

    for d in SIM_DAYS_BACK:
        sim_date = now - timedelta(days=d)
        forward_windows = [w for w in FORWARD_WINDOWS if d >= w + 10]
        if not forward_windows:
            print(f"    skipping {sim_date.strftime('%Y-%m-%d')} (too recent for forward windows)", flush=True)
            continue
        date_str = sim_date.strftime("%Y-%m-%d")
        print(f"  Simulating {date_str}...", flush=True)

        scored = []
        for ticker in SIM_TICKERS:
            try:
                if isinstance(hist_all.columns, pd.MultiIndex):
                    hist = hist_all.xs(ticker, axis=1, level=0)
                else:
                    hist = hist_all
                hist.index = pd.to_datetime(hist.index)
            except Exception:
                hist = pd.DataFrame()

            if hist.empty:
                continue

            tech = _technicals_as_of(hist, sim_date)
            if tech is None:
                continue

            price = tech["price"]
            # Simple val estimate using price range
            val_score = 5.0  # neutral default
            if price < 5:
                val_score = 2.0
            elif price > 200:
                val_score = 8.0
            elif price > 50:
                val_score = 6.0

            total_score = tech["score"] * 0.6 + val_score * 0.4

            forward = {}
            for w in forward_windows:
                ret = _forward_return(hist, sim_date, w)
                if ret is not None and not math.isnan(ret):
                    forward[f"ret_{w}d"] = ret

            scored.append({
                "ticker": ticker,
                "score": total_score,
                "tech_score": tech["score"],
                "val_score": val_score,
                "price": price,
                "rsi": tech["rsi"],
                "ret_1m": tech["ret_1m"],
                "ret_3m": tech["ret_3m"],
                "vol_ratio": tech["vol_ratio"],
                "signals": tech["signals"],
                "forward": forward,
            })

        if not scored:
            continue

        scores = [s["score"] for s in scored]
        min_s, max_s = min(scores), max(scores)

        for s in scored:
            if max_s == min_s:
                s["quartile"] = 2
            else:
                pct = (s["score"] - min_s) / (max_s - min_s) * 100
                s["quartile"] = 3 if pct >= 75 else 2 if pct >= 50 else 1 if pct >= 25 else 0

        results.append({
            "date": date_str,
            "tickers_analyzed": len(scored),
            "tickers": scored,
        })

    aggregated = _aggregate(results)
    _save(aggregated, results)
    return aggregated


def _aggregate(sim_runs):
    all_quartile = defaultdict(list)
    for run in sim_runs:
        for s in run["tickers"]:
            all_quartile[s["quartile"]].append(s)

    # Determine which forward windows have data across quartiles
    all_keys = set()
    for q in range(4):
        for s in all_quartile.get(q, []):
            all_keys.update(s.get("forward", {}).keys())
    available_windows = sorted([int(k.replace("ret_", "").replace("d", "")) for k in all_keys])

    qstats = {}
    for q in range(4):
        group = all_quartile.get(q, [])
        if not group:
            continue
        stats = {"count": len(group)}
        for w in available_windows:
            key = f"ret_{w}d"
            vals = [s["forward"][key] for s in group if key in s.get("forward", {})]
            vals = [v for v in vals if not math.isnan(v)]
            if vals:
                stats[key] = {
                    "avg": sum(vals) / len(vals),
                    "median": sorted(vals)[len(vals) // 2],
                    "positive": sum(1 for v in vals if v > 0) / len(vals),
                    "best": max(vals),
                    "worst": min(vals),
                    "n": len(vals),
                }
        qstats[f"Q{q}"] = stats

    tvb = {}
    for w in available_windows:
        key = f"ret_{w}d"
        q3 = qstats.get("Q3", {}).get(key, {})
        q0 = qstats.get("Q0", {}).get(key, {})
        if q3.get("avg") is not None and q3.get("avg") is not None:
            tvb[f"{w}d"] = {
                "top_avg": q3["avg"],
                "bottom_avg": q0.get("avg"),
                "outperformance": q3["avg"] - q0.get("avg") if q0.get("avg") is not None else None,
            }

    return {
        "total_simulations": len(sim_runs),
        "total_trades": sum(len(r["tickers"]) for r in sim_runs),
        "windows_tracked": available_windows,
        "quartile": qstats,
        "top_vs_bottom": tvb,
    }


def _save(aggregated, raw_runs):
    os.makedirs(RUNS_DIR, exist_ok=True)
    with open(SIM_RESULTS_PATH, "w") as f:
        json.dump({"summary": aggregated, "runs": raw_runs}, f, indent=2, default=str)
    print(f"\n  Results: {SIM_RESULTS_PATH}")


def load_results():
    if os.path.exists(SIM_RESULTS_PATH):
        with open(SIM_RESULTS_PATH) as f:
            return json.load(f)
    return None
