import yfinance as yf
import pandas as pd
import numpy as np
from .store import get as store_get, set as store_set, TTL_24H

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch(tickers, config):
    result = []
    for t in tickers:
        cached = store_get("seasonality", t)
        if cached:
            result.append(cached)
            continue
        try:
            stock = yf.Ticker(t)
            hist = stock.history(period="5y")
            if hist is None or hist.empty:
                continue
            monthly = hist["Close"].resample("ME").ffill()
            if len(monthly) < 24:
                continue
            rets = monthly.pct_change().dropna()
            monthly_rets = {m: [] for m in range(1, 13)}
            for idx, val in rets.items():
                monthly_rets[idx.month].append(val)
            month_stats = {}
            for m in range(1, 13):
                vals = monthly_rets[m]
                if len(vals) >= 2:
                    month_stats[m] = {
                        "avg": float(np.mean(vals)),
                        "std": float(np.std(vals)),
                        "hit_rate": sum(1 for v in vals if v > 0) / len(vals),
                        "count": len(vals),
                    }
            if not month_stats:
                continue
            current_month = pd.Timestamp.now().month
            scores_per_month = {}
            for m, st in month_stats.items():
                sharpe = st["avg"] / st["std"] if st["std"] > 0 else 0
                scores_per_month[m] = (
                    st["avg"] * 15 +
                    st["hit_rate"] * 3 +
                    min(sharpe, 2) * 1
                )
            best_month = max(scores_per_month, key=scores_per_month.get)
            best_score = max(scores_per_month.values())
            upcoming_months = [(current_month % 12) + 1, ((current_month + 1) % 12) + 1]
            upcoming_bonus = 0
            for um in upcoming_months:
                if um in scores_per_month and scores_per_month[um] > 0.5:
                    upcoming_bonus += 1.5
            score = min(best_score + upcoming_bonus, 10)
            profile_parts = []
            for m in sorted(
                scores_per_month, key=scores_per_month.get, reverse=True
            )[:3]:
                if scores_per_month[m] > 0.3:
                    profile_parts.append(MONTH_NAMES[m - 1])
            profile = "-".join(profile_parts) if profile_parts else "None"
            entry = {
                "ticker": t,
                "score": round(score, 1),
                "best_month": MONTH_NAMES[best_month - 1],
                "best_month_avg": round(month_stats[best_month]["avg"] * 100, 1),
                "best_hit_rate": round(month_stats[best_month]["hit_rate"], 2),
                "upcoming_months": "-".join(MONTH_NAMES[(current_month % 12)]),
                "profile": profile,
                "seasonality_strength": "strong" if score >= 6 else "moderate" if score >= 3 else "weak",
            }
            store_set("seasonality", t, entry, TTL_24H)
            result.append(entry)
        except Exception as e:
            import sys
            print(f"[seasonality] error for {t}: {e}", file=sys.stderr)
    return result
