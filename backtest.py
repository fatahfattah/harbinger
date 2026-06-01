#!/usr/bin/env python3
import sys
import os
HERE = os.path.dirname(__file__)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from backtest import tracker


def main():
    import argparse
    parser = argparse.ArgumentParser(description="harbinger — backtest / performance tracker")
    parser.add_argument("command", nargs="?", default="track",
                        choices=["track", "results", "simulate"],
                        help="track: measure forward returns of past scans (default)")
    args = parser.parse_args()

    if args.command == "track":
        result = tracker.track()
        if result is None:
            print("No data.")
            return
        _print_summary(result)
    elif args.command == "results":
        result = tracker.load_results()
        if result is None:
            print("No results yet. Run `python backtest.py track` first.")
            return
        _print_summary(result)
    elif args.command == "simulate":
        from backtest import simulate
        result = simulate.simulate()
        if result:
            _print_simulation(result)
        return


def _print_summary(result):
    s = result["summary"]
    print()
    print("=" * 74)
    print("  BACKTEST RESULTS")
    print("=" * 74)
    print(f"\n  Runs analyzed: {s['total_runs']}")
    print(f"  Total picks:  {s['total_picks_in_runs']}")
    print(f"  Price data:   {s['total_traded']} ({s['traded_pct']}%)")
    print()

    qs = s.get("quartile", {})
    if qs:
        print(f"  {'Window':<10} {'Q0(bottom)':<18} {'Q1':<18} {'Q2':<18} {'Q3(top)':<18} {'SPY':<12} {'Univ':<12}")
        print(f"  {'-'*8} {'-'*16} {'-'*16} {'-'*16} {'-'*16} {'-'*10} {'-'*10}")
        for w in [14, 30, 60, 90]:
            key = f"ret_{w}d"
            def qv(q):
                d = qs.get(q, {}).get(key, {})
                if d and d.get("avg") is not None:
                    return f"{d['avg']*100:>6.1f}% ({d['positive']*100:>3.0f}%+)"
                return " " * 16
            bench = s.get("benchmark_avg", {}).get(key)
            bench_s = f"{bench*100:>5.1f}%" if bench else " " * 10
            univ = s.get("universe_avg", {}).get(key)
            univ_s = f"{univ*100:>5.1f}%" if univ else " " * 10
            label = f"{w}d"
            print(f"  {label:<10} {qv('Q0')} {qv('Q1')} {qv('Q2')} {qv('Q3')} {bench_s} {univ_s}")

    tvb = s.get("top_vs_bottom", {})
    if tvb:
        print(f"\n  Top Quartile vs Bottom Quartile:")
        for w, d in sorted(tvb.items()):
            if d.get("outperformance") is not None:
                print(f"    {w}: top {d['top_avg']*100:.1f}% vs bottom {d['bottom_avg']*100:.1f}% = +{d['outperformance']*100:.1f}% outperformance")

    print()


def _print_simulation(result):
    s = result
    print()
    print("=" * 74)
    print("  HISTORICAL SIMULATION RESULTS (val + tech signals)")
    print("=" * 74)
    print(f"\n  Simulation dates: {s['total_simulations']}")
    print(f"  Total trades:    {s['total_trades']}")
    print()

    qs = s.get("quartile", {})
    if qs:
        windows = set()
        for q in range(4):
            for k in qs.get(f'Q{q}', {}):
                if k.startswith('ret_'):
                    windows.add(int(k.replace('ret_','').replace('d','')))
        windows = sorted(windows)

        print(f"  {'Window':<10} {'Q0(bottom)':<18} {'Q1':<18} {'Q2':<18} {'Q3(top)':<18}")
        print(f"  {'-'*8} {'-'*16} {'-'*16} {'-'*16} {'-'*16}")
        for w in windows:
            key = f"ret_{w}d"
            def qv(q):
                d = qs.get(q, {}).get(key, {})
                if d and d.get("avg") is not None:
                    return f"{d['avg']*100:>6.1f}% ({d['positive']*100:>3.0f}%+)"
                return " " * 16
            print(f"  {w}d  {qv('Q0')} {qv('Q1')} {qv('Q2')} {qv('Q3')}")

    tvb = s.get("top_vs_bottom", {})
    if tvb:
        print(f"\n  Top Quartile vs Bottom Quartile:")
        for w, d in sorted(tvb.items()):
            if d.get("outperformance") is not None:
                print(f"    {w}: top {d['top_avg']*100:.1f}% vs bottom {d['bottom_avg']*100:.1f}% = +{d['outperformance']*100:.1f}% outperformance")
    print()


if __name__ == "__main__":
    main()
