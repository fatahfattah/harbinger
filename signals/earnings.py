import yfinance as yf
import pandas as pd
from .store import get as store_get, set as store_set, TTL_24H


def fetch(tickers, config):
    result = []
    for t in tickers:
        cached = store_get("earnings", t)
        if cached:
            result.append(cached)
            continue
        try:
            stock = yf.Ticker(t)
            ed = stock.earnings_dates
            if ed is None or ed.empty:
                continue
            recent = ed.head(4)
            beats, total_surprise, count = 0, 0.0, 0
            for _, row in recent.iterrows():
                est = row.get("EPS Estimate")
                rep = row.get("Reported EPS")
                surp = row.get("Surprise(%)")
                if rep is not None and est is not None and not pd.isna(est) and not pd.isna(rep):
                    count += 1
                    if rep > est:
                        beats += 1
                    if surp is not None and not pd.isna(surp):
                        total_surprise += abs(float(surp))
            if count == 0:
                continue
            beat_rate = beats / count
            avg_surprise = total_surprise / count if count > 0 else 0
            score = min(beat_rate * 5, 5) + min(avg_surprise / 5, 1) * 3
            cal = stock.calendar
            if cal is not None:
                raw = cal.get("Earnings Date") if isinstance(cal, dict) else None
                if raw is None and hasattr(cal, "get"):
                    raw = cal.get("Earnings Date")
                if raw is not None:
                    if hasattr(raw, "iloc"):
                        val = raw.iloc[0]
                    elif isinstance(raw, (list, tuple)):
                        val = raw[0]
                    else:
                        val = raw
                    days = (pd.Timestamp(val) - pd.Timestamp.now()).days
                    if 0 < days <= 14:
                        score += 2
            entry = {
                "ticker": t,
                "score": round(min(score, 10), 1),
                "beat_rate": round(beat_rate, 2),
                "avg_surprise_pct": round(avg_surprise, 2),
                "beats": beats,
                "total": count,
            }
            store_set("earnings", t, entry, TTL_24H)
            result.append(entry)
        except Exception as e:
            import sys
            print(f"[earnings] error for {t}: {e}", file=sys.stderr)
    return result
