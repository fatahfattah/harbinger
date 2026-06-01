import sqlite3
import os
import json
import csv
from datetime import datetime, timedelta
from collections import defaultdict

HERE = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(HERE, "cache", "outcomes.db")

BENCHMARK_TICKER = "IWM"
SIGNAL_KEYS = [
    "valuation", "insider", "fund_13f", "social", "catalyst",
    "technicals", "niche", "short_interest", "earnings",
]


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT UNIQUE,
            run_date TEXT,
            universe TEXT,
            total_scored INTEGER
        );
        CREATE TABLE IF NOT EXISTS picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_id INTEGER,
            ticker TEXT,
            rank INTEGER,
            total_score REAL,
            val_score REAL,
            insider_score REAL,
            f13f_score REAL,
            social_score REAL,
            cat_score REAL,
            tech_score REAL,
            niche_score REAL,
            si_score REAL,
            earn_score REAL,
            early_stage_score REAL,
            entry_price REAL,
            FOREIGN KEY(scan_id) REFERENCES scans(id)
        );
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pick_id INTEGER,
            period TEXT,
            exit_price REAL,
            return_pct REAL,
            benchmark_return REAL,
            alpha REAL,
            checked_at TEXT,
            FOREIGN KEY(pick_id) REFERENCES picks(id)
        );
        CREATE INDEX IF NOT EXISTS idx_picks_ticker ON picks(ticker);
        CREATE INDEX IF NOT EXISTS idx_picks_scan ON picks(scan_id);
        CREATE INDEX IF NOT EXISTS idx_outcomes_pick ON outcomes(pick_id);
    """)
    conn.commit()
    conn.close()


def record_scan(scored_list, config, metadata):
    init_db()
    top = scored_list[:config.TOP_N]
    if not top:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    universe = (metadata or {}).get("universe", "unknown")
    total_scored = len(scored_list)
    conn = _db()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO scans(timestamp, run_date, universe, total_scored) VALUES (?,?,?,?)",
        (ts, datetime.now().isoformat(), universe, total_scored),
    )
    scan_id = c.lastrowid
    if scan_id is None:
        c.execute("SELECT id FROM scans WHERE timestamp = ?", (ts,))
        row = c.fetchone()
        if row:
            scan_id = row["id"]
        else:
            conn.close()
            return
    for rank, e in enumerate(top, 1):
        scores = e.get("scores", {})
        v = e.get("details", {}).get("valuation", {})
        price = v.get("price", 0) or 0
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = 0
        c.execute(
            """INSERT INTO picks(scan_id, ticker, rank, total_score,
               val_score, insider_score, f13f_score, social_score,
               cat_score, tech_score, niche_score, si_score,
               earn_score, early_stage_score, entry_price)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                scan_id, e["ticker"], rank, e["total_score"],
                scores.get("valuation", 0),
                scores.get("insider", 0),
                scores.get("fund_13f", 0),
                scores.get("social", 0),
                scores.get("catalyst", 0),
                scores.get("technicals", 0),
                scores.get("niche", 0),
                scores.get("short_interest", 0),
                scores.get("earnings", 0),
                e.get("early_stage_score", 0),
                price,
            ),
        )
    conn.commit()
    conn.close()


def check_outcomes():
    import yfinance as yf
    init_db()
    conn = _db()
    c = conn.cursor()
    now = datetime.now()
    picks = c.execute(
        "SELECT p.id, p.ticker, p.entry_price, s.timestamp FROM picks p "
        "JOIN scans s ON p.scan_id = s.id "
        "WHERE p.entry_price > 0"
    ).fetchall()
    try:
        bench = yf.Ticker(BENCHMARK_TICKER)
        bench_hist = bench.history(period="6mo")
    except Exception:
        bench_hist = None
    updated = 0
    for pick in picks:
        pick_id, ticker, entry_price, scan_ts = pick["id"], pick["ticker"], pick["entry_price"], pick["timestamp"]
        try:
            scan_date = datetime.strptime(scan_ts, "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        tk = yf.Ticker(ticker)
        try:
            hist = tk.history(period="6mo")
        except Exception:
            continue
        if hist.empty:
            continue
        for period_name, days in [("1m", 21), ("3m", 63), ("6m", 126)]:
            already = c.execute(
                "SELECT id FROM outcomes WHERE pick_id=? AND period=?",
                (pick_id, period_name),
            ).fetchone()
            if already:
                continue
            cutoff = scan_date + timedelta(days=days)
            if now < cutoff:
                continue
            after = hist[hist.index >= cutoff.strftime("%Y-%m-%d")]
            if after.empty:
                continue
            exit_price = float(after.iloc[0]["Close"])
            ret = (exit_price - entry_price) / entry_price if entry_price else 0
            bench_after = None
            if bench_hist is not None and not bench_hist.empty:
                bench_after = bench_hist[bench_hist.index >= cutoff.strftime("%Y-%m-%d")]
            bench_enter = None
            bench_exit = None
            if bench_after is not None and not bench_after.empty:
                bench_enter = float(bench_hist.iloc[-1]["Close"]) if not bench_hist.empty else None
                bench_exit = float(bench_after.iloc[0]["Close"]) if not bench_after.empty else None
                if bench_enter and bench_exit:
                    bench_ret = (bench_exit - bench_enter) / bench_enter
                    alpha = ret - bench_ret
                else:
                    bench_ret = None
                    alpha = None
            else:
                bench_ret = None
                alpha = None
            c.execute(
                "INSERT INTO outcomes(pick_id, period, exit_price, return_pct, benchmark_return, alpha, checked_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (pick_id, period_name, exit_price, ret, bench_ret, alpha, now.isoformat()),
            )
            updated += 1
    conn.commit()
    conn.close()
    return updated


def get_outcomes():
    init_db()
    conn = _db()
    c = conn.cursor()
    rows = c.execute(
        "SELECT s.timestamp as scan_ts, p.ticker, p.rank, p.total_score, p.entry_price, "
        "o.period, o.return_pct, o.benchmark_return, o.alpha, o.checked_at "
        "FROM picks p "
        "JOIN scans s ON p.scan_id = s.id "
        "LEFT JOIN outcomes o ON o.pick_id = p.id "
        "ORDER BY s.timestamp DESC, p.rank"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signal_correlation():
    init_db()
    conn = _db()
    c = conn.cursor()
    rows = c.execute(
        "SELECT p.*, o.return_pct, o.period FROM picks p "
        "JOIN outcomes o ON o.pick_id = p.id "
        "WHERE o.return_pct IS NOT NULL"
    ).fetchall()
    conn.close()
    if not rows:
        return []
    by_signal = defaultdict(list)
    for r in rows:
        d = dict(r)
        for key in SIGNAL_KEYS:
            col = key + "_score"
            if col in d and d[col] is not None:
                by_signal[key].append((float(d[col]), float(d["return_pct"])))
    result = []
    for signal, pairs in by_signal.items():
        if len(pairs) < 3:
            continue
        scores = [p[0] for p in pairs]
        returns = [p[1] for p in pairs]
        n = len(scores)
        mean_s = sum(scores) / n
        mean_r = sum(returns) / n
        num = sum((s - mean_s) * (r - mean_r) for s, r in pairs)
        den = (sum((s - mean_s) ** 2 for s in scores) ** 0.5 *
               sum((r - mean_r) ** 2 for r in returns) ** 0.5)
        corr = num / den if den else 0
        result.append({"signal": signal, "correlation": round(corr, 3), "samples": n})
    result.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    return result


def get_pending_outcomes():
    init_db()
    conn = _db()
    c = conn.cursor()
    rows = c.execute(
        "SELECT p.id, p.ticker, s.timestamp, p.entry_price "
        "FROM picks p JOIN scans s ON p.scan_id = s.id "
        "WHERE p.entry_price > 0 "
        "AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.pick_id = p.id AND o.period = '6m') "
        "ORDER BY s.timestamp"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
