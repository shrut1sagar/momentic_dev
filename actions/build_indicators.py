#!/usr/bin/env python3
"""Action: compute moving-average features from raw Massive CSVs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analytics.calculate_indicators import build_moving_average_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build moving-average indicator CSVs from data/raw/*.csv."
    )
    parser.add_argument("--tickers", required=True, help="Comma-separated ticker symbols.")
    parser.add_argument(
        "--windows",
        default="50,120,280",
        help="Comma-separated moving-average windows (default: 50,120,280).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [sym.strip().upper() for sym in args.tickers.split(",") if sym.strip()]
    if not symbols:
        print("[features] No valid tickers provided.", file=sys.stderr)
        return 1

    raw_dir = ROOT / "data" / "raw"
    processed_dir = ROOT / "data" / "processed"
    windows = [int(token.strip()) for token in args.windows.split(",") if token.strip()]

    for symbol in symbols:
        try:
            output = build_moving_average_csv(symbol, raw_dir, processed_dir, windows)
        except Exception as exc:
            print(f"[features] {symbol}: ERROR {exc}", file=sys.stderr)
            continue
        print(f"[features] {symbol}: wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
