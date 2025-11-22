#!/usr/bin/env python3  # allow this action to run via `python actions/fetch_history_massive.py`
"""Fetch Massive OHLCV for tickers and store canonical CSVs under data/raw/."""  # concise docstring

from __future__ import annotations  # enable future-style annotations

import argparse  # parse CLI flags
import sys  # tweak import path + emit exit codes
from datetime import datetime  # default end-date fallback
from pathlib import Path  # build portable filesystem paths

ROOT = Path(__file__).resolve().parents[1]  # compute repo root (parent of actions/)
SRC = ROOT / "src"  # library modules live under src/
if str(SRC) not in sys.path:  # guarantee src/ is importable regardless of CWD
    sys.path.insert(0, str(SRC))

from config.secrets import massive_credentials  # type: ignore  # load Massive BASE_URL + API key
from data.fetch_history import (  # type: ignore  # generic CSV helpers
    extract_dates,
    load_raw_rows,
    merge_rows,
    write_raw_csv,
)
from data.fetch_history_massive import fetch_daily_ohlcv  # type: ignore  # Massive-specific fetcher


def _parse_args() -> argparse.Namespace:
    """Create the CLI parser and return parsed arguments."""
    parser = argparse.ArgumentParser(
        description="Download Massive daily bars and write data/raw/{SYMBOL}.csv.",
        epilog="Example: python actions/fetch_history_massive.py --symbols TQQQ --start 2024-01-01 --end 2024-03-01",
    )
    parser.add_argument("--symbols", required=True, help="Comma-separated tickers (e.g. TQQQ,SQQQ).")
    parser.add_argument("--start", help="Inclusive start date (YYYY-MM-DD). Optional.")
    parser.add_argument("--end", help="Inclusive end date (YYYY-MM-DD). Defaults to today.")
    return parser.parse_args()


def _has_coverage(existing_dates: set[str], start: str, end: str) -> bool:
    """Return True when the CSV already includes the requested start/end window."""
    if not existing_dates:  # no historical data yet
        return False
    ordered = sorted(existing_dates)  # sort strings (ISO format keeps chronological order)
    min_date, max_date = ordered[0], ordered[-1]  # oldest + newest dates we have
    return (
        min_date <= start <= max_date
        and min_date <= end <= max_date
        and start in existing_dates
        and end in existing_dates
    )


def _resolve_window(existing_dates: set[str], requested_start: str | None, requested_end: str | None) -> tuple[str | None, str]:
    """Decide which start/end to fetch based on CLI input and existing history."""
    today = datetime.utcnow().strftime("%Y-%m-%d")  # default end is “today”
    end = (requested_end or today).strip()  # prefer CLI override else today
    if requested_start and requested_start.strip():  # if user passed --start use it
        return requested_start.strip(), end
    latest = max(existing_dates) if existing_dates else None  # otherwise use last known date
    return latest, end


def main() -> int:
    """CLI entry point: fetch missing Massive data per ticker and persist CSVs."""
    args = _parse_args()  # parse CLI flags
    symbols = [part.strip().upper() for part in args.symbols.split(",") if part.strip()]  # normalize tickers
    if not symbols:  # ensure we have something to do
        print("[fetch] No valid symbols provided.", file=sys.stderr)
        return 1

    base_url, api_key = massive_credentials()  # read Massive credentials (fails fast if missing)
    raw_dir = ROOT / "data" / "raw"  # canonical location for raw OHLCV CSVs
    raw_dir.mkdir(parents=True, exist_ok=True)  # create folder tree if needed

    for symbol in symbols:  # loop over each requested ticker
        csv_path = raw_dir / f"{symbol}.csv"  # this symbol’s CSV location
        existing_rows = load_raw_rows(csv_path)  # load any pre-existing rows (if file exists)
        existing_dates = extract_dates(existing_rows)  # build quick lookup set
        start, end = _resolve_window(existing_dates, args.start, args.end)  # infer fetch window
        if not start:  # no historical data and user omitted --start
            print(f"[fetch] {symbol}: history missing; provide --start for initial backfill.", file=sys.stderr)
            continue
        if _has_coverage(existing_dates, start, end):  # skip fetch when already covered
            print(f"[fetch] {symbol}: already has {start} → {end}; skipping Massive call.")
            continue

        print(f"[fetch] {symbol}: fetching {start} → {end} from Massive.")  # log intent
        try:
            rows = fetch_daily_ohlcv(symbol, start, end, base_url, api_key)  # call Massive helper
        except Exception as error:  # Massive call failed; report and continue
            print(f"[fetch] {symbol}: ERROR {error}", file=sys.stderr)
            continue

        combined_rows = merge_rows(existing_rows, rows)  # union new + old data
        write_raw_csv(combined_rows, csv_path)  # overwrite CSV with merged canonical rows
        print(f"[fetch] {symbol}: wrote {csv_path} ({len(rows)} new rows).")  # log success

    return 0  # exiting 0 signals success (errors already reported inline)


if __name__ == "__main__":  # when invoked directly
    raise SystemExit(main())  # exit with the code returned by main()
