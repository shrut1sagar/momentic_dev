#!/usr/bin/env python3
"""Thin CLI wrapper around the signal engine orchestrator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from orchestration.signal_engine import run_signal_engine


def parse_args() -> argparse.Namespace:
    """Command-line arguments for the signal engine."""
    parser = argparse.ArgumentParser(description="Run the daily signal decision engine.")
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the processed indicators CSV (e.g., data/processed/TQQQ_indicators.csv).",
    )
    parser.add_argument(
        "--settings",
        default=str(ROOT / "config" / "settings.yaml"),
        help="Path to settings YAML file (defaults to config/settings.yaml).",
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "data" / "results" / "signal_report.txt"),
        help="Path to write the human-readable report.",
    )
    parser.add_argument(
        "--date",
        help="Optional signal date (YYYY-MM-DD). Defaults to the latest date in the CSV.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_signal_engine(
        csv_path=Path(args.csv),
        settings_path=Path(args.settings),
        report_path=Path(args.report),
        signal_date=args.date,
    )
    print(
        f"[signal] {result.date} trend={result.trend} regime={result.regime} "
        f"TQQQ={result.long_weight:.2f} SQQQ={result.short_weight:.2f} CASH={result.cash_weight:.2f}"
    )
    print("Notes:")
    for line in result.notes:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
