#!/usr/bin/env python3
import os
import json
import csv
import sys
import math
import subprocess
import threading
import uuid
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
RUNS_DIR = os.path.join(HERE, "runs")
PORT = int(os.environ.get("PORT", 8080))

# Background command runner
_running = {}

# Deep-dive cache: {ticker: {result, timestamp}}
_deepdive_cache = {}
_DEEPDIVE_TTL = 3600  # 1 hour


def _csv_to_signal_row(row):
    import json
    details = {}
    details["valuation"] = {
        "name": row.get("Name", ""),
        "price": _float(row.get("Price")),
        "sector": row.get("Sector", ""),
        "fwd_pe": _float(row.get("Fwd_PE")),
        "rev_growth": _float(row.get("Rev_Growth")),
        "signals": [],
    }
    details["insider"] = {
        "buys": _int(row.get("Insider_Buys")),
        "sells": _int(row.get("Insider_Sells")),
        "net": _int(row.get("Insider_Net")),
        "buy_value": _float(row.get("Insider_Buy_Value")),
        "sell_value": _float(row.get("Insider_Sell_Value")),
        "net_value": _float(row.get("Insider_Net_Value")),
        "transactions": json.loads(row.get("Insider_Transactions", "[]")),
    }
    details["fund_13f"] = {
        "new_funds": _int(row.get("New_Funds")),
        "fund_names": [f.strip() for f in row.get("Fund_Names", "").split(",") if f.strip()],
    }
    details["social"] = {"mentions": _int(row.get("Reddit_Mentions")), "subreddits": {}}
    details["niche"] = {
        "niche_mentions": _float(row.get("Niche_Mentions")),
        "general_mentions": 0,
        "keywords": [k.strip() for k in row.get("Niche_Keywords", "").split(",") if k.strip()],
        "communities": [c.strip() for c in row.get("Niche_Communities", "").split(",") if c.strip()],
    }
    details["catalyst"] = {"events": [e.strip() for e in row.get("Catalyst_Events", "").split(";") if e.strip()]}
    details["technicals"] = {
        "ret_1m": _float(row.get("Ret_1m")),
        "ret_3m": _float(row.get("Ret_3m")),
        "rsi": _float(row.get("RSI")),
        "vol_ratio": _float(row.get("Vol_Ratio")),
        "above_50ma": row.get("Above_50ma"),
        "above_200ma": row.get("Above_200ma"),
        "pct_from_high": _float(row.get("Pct_From_High")),
        "signals": [],
    }
    details["short_interest"] = {
        "short_pct": _float(row.get("Short_Pct")),
        "short_ratio": _float(row.get("Short_Ratio")),
        "short_change": row.get("Short_Change", ""),
    }
    details["earnings"] = {
        "beat_rate": _float(row.get("Beat_Rate")),
        "avg_surprise_pct": _float(row.get("Avg_Surprise_Pct")),
        "total_quarters": 4,
    }
    return {
        "ticker": row.get("Ticker", ""),
        "total_score": _float(row.get("Score")),
        "early_stage_score": _float(row.get("Early_Stage_Score")),
        "active_signals": _int(row.get("Active_Signals")),
        "archetype": row.get("Pattern", ""),
        "scores": {
            "valuation": _float(row.get("Val_Score")),
            "insider": _float(row.get("Insider_Score")),
            "fund_13f": _float(row.get("13F_Score")),
            "social": _float(row.get("Social_Score")),
            "catalyst": _float(row.get("Cat_Score")),
            "technicals": _float(row.get("Tech_Score")),
            "niche": _float(row.get("Niche_Score")),
            "short_interest": _float(row.get("Short_Score")),
            "earnings": _float(row.get("Earnings_Score")),
        },
        "details": details,
    }


def _float(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def _int(v):
    if v is None or v == "":
        return 0
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _sanitize_json(o):
    """json.dumps default handler: convert NaN/Inf to None."""
    if isinstance(o, float):
        if math.isnan(o) or math.isinf(o):
            return None
        return o
    if isinstance(o, dict):
        return {k: _sanitize_json(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_sanitize_json(v) for v in o]
    return o


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "":
            self._serve_static(os.path.join(RUNS_DIR, "index.html"))
        elif parsed.path in ("/backtest", "/backtest/"):
            self._serve_static(os.path.join(RUNS_DIR, "backtest.html"))
        elif parsed.path == "/api/runs":
            self._serve_runs_list()
        elif parsed.path.startswith("/api/runs/"):
            name = parsed.path[len("/api/runs/"):]
            self._serve_run(name)
        elif parsed.path == "/api/backtest":
            self._serve_backtest()
        elif parsed.path == "/api/backtest/simulation":
            self._serve_backtest_simulation()
        elif parsed.path == "/api/watchlist":
            self._serve_watchlist(parsed.query)
        elif parsed.path == "/api/history":
            self._serve_history(parsed.query)
        elif parsed.path == "/api/sectors":
            self._serve_sectors()
        elif parsed.path == "/api/analytics":
            self._serve_analytics()
        elif parsed.path == "/api/outcomes":
            self._serve_outcomes()
        elif parsed.path == "/api/outcomes/correlation":
            self._serve_outcomes_correlation()
        elif parsed.path.startswith("/api/run/"):
            run_id = parsed.path[len("/api/run/"):]
            self._serve_run_status(run_id)
        elif parsed.path == "/api/chart":
            self._serve_chart(parsed.query)
        elif parsed.path == "/api/info":
            self._serve_info()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len else ""

        if parsed.path.startswith("/api/watchlist"):
            self._serve_watchlist(body)
        elif parsed.path == "/api/run":
            self._handle_run(json.loads(body) if body else {})
        elif parsed.path == "/api/deepdive":
            self._serve_deepdive(json.loads(body) if body else {})
        elif parsed.path == "/api/outcomes/check":
            self._serve_check_outcomes()
        else:
            self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/runs/"):
            ts = parsed.path[len("/api/runs/"):]
            self._delete_run(ts)
        else:
            self.send_error(404)

    def _delete_run(self, ts):
        csv_path = os.path.join(RUNS_DIR, f"scan_{ts}.csv")
        meta_path = os.path.join(RUNS_DIR, f"run_{ts}.json")
        deleted = []
        if os.path.exists(csv_path):
            os.remove(csv_path)
            deleted.append(f"scan_{ts}.csv")
        if os.path.exists(meta_path):
            os.remove(meta_path)
            deleted.append(f"run_{ts}.json")
        self._json_response({"deleted": deleted})

    def _serve_static(self, path):
        if not os.path.exists(path):
            self.send_error(404)
            return
        ext = os.path.splitext(path)[1]
        ct = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css",
            ".js": "application/javascript",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, data):
        body = json.dumps(_sanitize_json(data)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_runs_list(self):
        runs = []
        if os.path.isdir(RUNS_DIR):
            for f in sorted(os.listdir(RUNS_DIR), reverse=True):
                if f.startswith("scan_") and f.endswith(".csv"):
                    ts = f[5:-4]
                    meta_file = f"run_{ts}.json"
                    meta_path = os.path.join(RUNS_DIR, meta_file)
                    meta = {}
                    if os.path.exists(meta_path):
                        with open(meta_path) as mf:
                            meta = json.load(mf)
                    csv_path = os.path.join(RUNS_DIR, f)
                    row_count = sum(1 for _ in open(csv_path)) - 1
                    runs.append({
                        "timestamp": ts,
                        "csv_file": f,
                        "meta_file": meta_file if os.path.exists(meta_path) else None,
                        "meta": meta,
                        "row_count": max(row_count, 0),
                    })
        self._json_response(runs)

    def _serve_run(self, name):
        if not name.endswith(".csv"):
            self.send_error(400, "Must request a .csv file")
            return
        path = os.path.join(RUNS_DIR, name)
        if not os.path.exists(path):
            self.send_error(404)
            return

        ts = name[5:-4]
        meta = {}
        meta_path = os.path.join(RUNS_DIR, f"run_{ts}.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)

        rows = []
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        self._json_response({"meta": meta, "rows": rows})

    def _serve_backtest(self):
        path = os.path.join(RUNS_DIR, "backtest_results.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            data = {"summary": {"total_runs": 0, "total_picks_in_runs": 0, "total_traded": 0}, "runs": []}
        self._json_response(data)

    def _serve_backtest_simulation(self):
        path = os.path.join(RUNS_DIR, "backtest_simulation.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            data = {"summary": {"total_simulations": 0, "total_trades": 0}, "runs": []}
        self._json_response(data)


    def _serve_watchlist(self, query):
        from tracking.watchlist import Watchlist
        wl = Watchlist()
        params = parse_qs(query) if query else {}

        if "action" in params:
            action = params["action"][0]
            if action == "add":
                ticker = params.get("ticker", [""])[0]
                if ticker:
                    ok, msg = wl.add(ticker, params.get("reason", [""])[0])
                    self._json_response({"ok": ok, "message": msg})
                    return
            elif action == "remove":
                ticker = params.get("ticker", [""])[0]
                if ticker:
                    ok, msg = wl.remove(ticker)
                    self._json_response({"ok": ok, "message": msg})
                    return
            elif action == "decision":
                ticker = params.get("ticker", [""])[0]
                act = params.get("decision_action", [""])[0]
                size = params.get("size", [None])[0]
                price = params.get("price", [None])[0]
                notes = params.get("notes", [""])[0]
                if ticker and act:
                    ok, msg = wl.add_decision(
                        ticker, act,
                        float(size) if size else None,
                        float(price) if price else None,
                        notes,
                    )
                    self._json_response({"ok": ok, "message": msg})
                    return
            self._json_response({"ok": False, "message": "invalid request"})
            return

        self._json_response(wl.data)

    def _serve_history(self, query):
        from tracking.history import TickerHistory
        th = TickerHistory()
        th.load()
        params = parse_qs(query) if query else {}
        if "ticker" in params:
            t = params["ticker"][0].upper()
            d = th.data.get(t)
            if d:
                self._json_response({"ticker": t, "data": d})
            else:
                self._json_response({"ticker": t, "data": None})
            return
        self._json_response(th.data)

    def _serve_sectors(self):
        from tracking import sector_watch
        data = sector_watch.load_latest(type("cfg", (), {"OUTPUT_DIR": RUNS_DIR})())
        if not data:
            data = {"sectors": {}, "rankings": [], "divergences": [], "llm_brief": "", "message": "Run a scan first"}
        self._json_response(data)

    def _serve_analytics(self):
        path = os.path.join(RUNS_DIR, "analytics.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            data = {}
        self._json_response(data)

    def _serve_outcomes(self):
        from tracking.outcomes import get_outcomes
        self._json_response(get_outcomes())

    def _serve_outcomes_correlation(self):
        from tracking.outcomes import get_signal_correlation
        self._json_response(get_signal_correlation())

    def _serve_check_outcomes(self):
        from tracking.outcomes import check_outcomes
        updated = check_outcomes()
        self._json_response({"ok": True, "updated": updated})

    def _serve_run_status(self, run_id):
        proc = _running.get(run_id)
        if not proc:
            self._json_response({"status": "not_found"})
            return
        lines = proc["output"].split("\n")
        last = lines[-20:] if len(lines) > 20 else lines
        self._json_response({
            "id": proc["id"],
            "status": proc["status"],
            "cmd": proc["cmd"],
            "label": proc["label"],
            "started": proc["started"],
            "output_tail": "\n".join(last),
            "output_len": len(proc["output"]),
            "returncode": proc["returncode"],
        })

    def _serve_deepdive(self, body):
        ticker = (body or {}).get("ticker", "").upper()
        if not ticker:
            self._json_response({"ok": False, "error": "Missing ticker"})
            return

        # Check cache
        cached = _deepdive_cache.get(ticker)
        if cached and (datetime.now() - cached["ts"]).total_seconds() < _DEEPDIVE_TTL:
            self._json_response({"ok": True, "ticker": ticker, "analysis": cached["result"], "cached": True})
            return

        # Load latest run data
        runs = []
        if os.path.isdir(RUNS_DIR):
            for f in sorted(os.listdir(RUNS_DIR), reverse=True):
                if f.startswith("scan_") and f.endswith(".csv"):
                    ts = f[5:-4]
                    meta_path = os.path.join(RUNS_DIR, f"run_{ts}.json")
                    if os.path.exists(meta_path):
                        runs.append((ts, f, meta_path))
                    if len(runs) >= 1:
                        break

        if not runs:
            self._json_response({"ok": False, "error": "No runs found"})
            return

        ts, csv_file, meta_path = runs[0]
        rows = []
        with open(os.path.join(RUNS_DIR, csv_file)) as f:
            import csv as csv_mod
            reader = csv_mod.DictReader(f)
            for row in reader:
                if row.get("Ticker", "").upper() == ticker:
                    rows.append(row)

        if not rows:
            self._json_response({"ok": False, "error": f"Ticker {ticker} not found in latest run"})
            return

        # Convert CSV row to structured signal data
        signal_row = _csv_to_signal_row(rows[0])

        # Fetch recent SEC filings for context
        sec_summary = ""
        try:
            from signals.sec_client import cik_for_ticker, fetch_submissions as sec_fetch_submissions
            cik = cik_for_ticker(ticker)
            if cik:
                data = sec_fetch_submissions(cik)
                if data and "filings" in data and "recent" in data["filings"]:
                    recent = data["filings"]["recent"]
                    forms, dates, descs = recent.get("form", []), recent.get("filingDate", []), recent.get("primaryDocument", [])
                    items = []
                    count = 0
                    for i in range(min(len(forms), 20)):
                        f = forms[i].upper()
                        if f in ("8-K", "6-K", "10-Q", "10-K", "S-1", "S-1/A", "424B4", "DEF 14A"):
                            items.append(f"{forms[i]} ({dates[i]})")
                            count += 1
                            if count >= 5:
                                break
                    if items:
                        sec_summary = "; ".join(items)
        except Exception:
            pass

        signal_row["sec_filings"] = sec_summary

        from llm.client import HarbingerLLM
        llm = HarbingerLLM("http://127.0.0.1:4096")
        if not llm.health():
            self._json_response({"ok": False, "error": "LLM server not reachable at localhost:4096"})
            return

        analysis = llm.deepdive(ticker, signal_row)
        _deepdive_cache[ticker] = {"result": analysis, "ts": datetime.now()}
        self._json_response({"ok": True, "ticker": ticker, "analysis": analysis, "cached": False})

    def _serve_info(self):
        scripts = []
        csv_dir = os.path.join(HERE, "run-history")
        for f in sorted(os.listdir(csv_dir)) if os.path.isdir(csv_dir) else []:
            pass
        # return info about available commands
        self._json_response({"_running": len(_running), "processes": list(_running.keys())})

    def _serve_chart(self, query):
        from urllib.parse import parse_qs
        params = parse_qs(query)
        ticker = (params.get("ticker") or [None])[0]
        if not ticker:
            self._json_response({"ok": False, "error": "Missing ticker"})
            return
        import yfinance as yf
        try:
            hist = yf.download(ticker, period="6mo", interval="1d", progress=False)
            if hist.empty:
                self._json_response({"ok": False, "error": "No data"})
                return
            # Flatten multi-level columns if present
            if hasattr(hist.columns, "get_level_values") and hist.columns.nlevels > 1:
                hist.columns = hist.columns.get_level_values(0)
            data = []
            for idx, row in hist.iterrows():
                dt = idx
                if hasattr(dt, "strftime"):
                    dt = dt.strftime("%Y-%m-%d")
                data.append({
                    "date": str(dt),
                    "open": round(float(row.get("Open", 0)), 2),
                    "high": round(float(row.get("High", 0)), 2),
                    "low": round(float(row.get("Low", 0)), 2),
                    "close": round(float(row.get("Close", 0)), 2),
                    "volume": int(row.get("Volume", 0)),
                })
            self._json_response({"ok": True, "ticker": ticker, "data": data})
        except Exception as e:
            self._json_response({"ok": False, "error": str(e)})

    def _handle_run(self, req):
        action = req.get("action", "")
        opts = req.get("opts", {})
        cmd = []

        if action == "full-scan":
            universe = opts.get("universe", "sp600+ipos")
            cmd = [sys.executable, "main.py", f"--universe={universe}"]
            if not opts.get("llm", True):
                cmd.append("--skip-llm")
            if opts.get("top_n"):
                cmd.append(f"--top-n={opts['top_n']}")
            label = f"Full scan ({universe})"

        elif action == "quick-scan":
            tickers = opts.get("tickers", "")
            cmd = [sys.executable, "main.py", f"--tickers={tickers}"]
            if not opts.get("llm", True):
                cmd.append("--skip-llm")
            if opts.get("top_n"):
                cmd.append(f"--top-n={opts['top_n']}")
            label = f"Quick scan ({tickers})"

        elif action == "backtest-track":
            cmd = [sys.executable, "backtest.py", "track"]
            label = "Backtest tracker"

        elif action == "backtest-simulate":
            cmd = [sys.executable, "backtest.py", "simulate"]
            label = "Backtest simulation"

        elif action == "analytics-rebuild":
            cmd = [sys.executable, "track.py", "analytics", "rebuild"]
            label = "Rebuild analytics"

        elif action == "history-rebuild":
            cmd = [sys.executable, "track.py", "history", "rebuild"]
            label = "Rebuild history"

        elif action == "check-outcomes":
            cmd = [sys.executable, "-c", "from tracking.outcomes import check_outcomes; n = check_outcomes(); print(f'Updated {n} outcomes')"]
            label = "Check outcomes"

        else:
            self._json_response({"error": f"Unknown action: {action}"})
            return

        run_id = _start_cmd(cmd, label)
        self._json_response({
            "id": run_id,
            "label": label,
            "cmd": " ".join(cmd),
            "status": "started",
        })


def _start_cmd(cmd, label):
    run_id = str(uuid.uuid4())[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=HERE,
    )
    _running[run_id] = {
        "id": run_id,
        "status": "running",
        "cmd": " ".join(cmd),
        "label": label,
        "started": now,
        "output": "",
        "process": proc,
        "returncode": None,
    }

    def _reader(p, rid):
        try:
            for line in iter(p.stdout.readline, ""):
                _running[rid]["output"] += line + "\n"
                if len(_running[rid]["output"]) > 100_000:
                    _running[rid]["output"] = _running[rid]["output"][-50_000:]
        except Exception:
            pass
        _running[rid]["status"] = "done"
        _running[rid]["returncode"] = p.poll()

    threading.Thread(target=_reader, args=(proc, run_id), daemon=True).start()
    return run_id


def main():
    os.makedirs(RUNS_DIR, exist_ok=True)
    print(f"  harbinger UI → http://localhost:{PORT}")
    print(f"  runs directory: {RUNS_DIR}")
    print(f"  press Ctrl+C to stop")
    HTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
