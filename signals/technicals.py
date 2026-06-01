import io
import contextlib
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

_MOMENTUM_WORKERS = 12


def fetch(tickers, config=None):
    if not tickers:
        return []

    results = []
    with ThreadPoolExecutor(max_workers=_MOMENTUM_WORKERS) as pool:
        futures = {pool.submit(_score_one, t): t for t in tickers}
        for f in as_completed(futures):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception:
                continue

    return results


def _score_one(ticker):
    try:
        tk = yf.Ticker(ticker)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            hist = tk.history(period="6mo")
            info = tk.info
    except Exception:
        return None

    if hist.empty or len(hist) < 20:
        return None

    close = hist["Close"]
    volumes = hist["Volume"]

    price_now = float(close.iloc[-1])

    price_1m_ago = float(close.iloc[-min(21, len(close))]) if len(close) >= 21 else float(close.iloc[0])
    price_3m_ago = float(close.iloc[-min(63, len(close))]) if len(close) >= 63 else float(close.iloc[0])

    ret_1m = (price_now - price_1m_ago) / price_1m_ago
    ret_3m = (price_now - price_3m_ago) / price_3m_ago

    vol_20d_avg = float(volumes.tail(20).mean())
    vol_today = float(volumes.iloc[-1])
    vol_ratio = vol_today / vol_20d_avg if vol_20d_avg > 0 else 1.0

    rsi_val = _rsi(close, 14)

    sma_50 = float(close.tail(50).mean()) if len(close) >= 50 else None
    sma_200 = float(close.tail(200).mean()) if len(close) >= 200 else None
    above_sma_50 = price_now > sma_50 if sma_50 else None
    above_sma_200 = price_now > sma_200 if sma_200 else None

    fifty_two_high = info.get("fiftyTwoWeekHigh") or info.get("regularMarketDayHigh")
    pct_from_high = (fifty_two_high - price_now) / fifty_two_high if fifty_two_high and fifty_two_high > 0 else None

    score = 0.0
    signals = []

    if ret_1m > 0.05:
        score += min(ret_1m * 50, 3)
        signals.append(f"1m+{ret_1m*100:.0f}%")
    elif ret_1m < -0.05:
        score += min(abs(ret_1m) * 20, 1)
        signals.append(f"1m{ret_1m*100:.0f}%")

    if ret_3m > 0.10:
        score += min(ret_3m * 15, 3)
        signals.append(f"3m+{ret_3m*100:.0f}%")

    if vol_ratio > 1.5:
        score += min((vol_ratio - 1.5) * 2, 2)
        signals.append(f"vol{vol_ratio:.1f}x")

    if rsi_val is not None and rsi_val < 30:
        score += 2
        signals.append("oversold")
    elif rsi_val is not None and rsi_val > 70:
        score += 1
        signals.append("overbought")

    if above_sma_50 is True:
        score += 1
        signals.append(">50ma")
    if above_sma_200 is True:
        score += 1
        signals.append(">200ma")

    if pct_from_high is not None and pct_from_high < 0.05:
        score += 2
        signals.append("52wkHi")
    elif pct_from_high is not None and pct_from_high < 0.10:
        score += 1
        signals.append("nearHi")

    score = min(score, 10)

    if score == 0:
        return None

    return {
        "ticker": ticker,
        "score": round(score, 2),
        "ret_1m": round(ret_1m * 100, 1),
        "ret_3m": round(ret_3m * 100, 1),
        "rsi": round(rsi_val, 1) if rsi_val is not None else None,
        "vol_ratio": round(vol_ratio, 2),
        "above_50ma": above_sma_50,
        "above_200ma": above_sma_200,
        "pct_from_high": round(pct_from_high * 100, 1) if pct_from_high is not None else None,
        "signals": signals,
    }


def _rsi(close, period=14):
    if len(close) < period + 1:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1] if avg_loss.iloc[-1] != 0 else 100
    return 100 - (100 / (1 + rs))
