#!/usr/bin/env python3
import sys
from tracking.watchlist import cli as watchlist_cli
from tracking.history import cli as history_cli
from tracking.analytics import cli as analytics_cli


def main():
    if len(sys.argv) < 2:
        print("Usage: python track.py <watchlist|history|analytics> ...")
        print("  watchlist add <ticker> [--reason ...] [--signals ...]")
        print("  watchlist remove <ticker>")
        print("  watchlist decision <ticker> --action <buy|sell|skip|add|trim> [--size N] [--price N] [--notes ...]")
        print("  watchlist list")
        print("  history rebuild")
        print("  history show [ticker]")
        print("  analytics rebuild")
        return

    cmd = sys.argv[1]
    rest = sys.argv[2:] if len(sys.argv) > 2 else []

    if cmd == "watchlist":
        watchlist_cli(["watchlist"] + rest)
    elif cmd == "history":
        history_cli(["history"] + rest)
    elif cmd == "analytics":
        analytics_cli(["analytics"] + rest)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
