"""Generic helpers for working with canonical OHLCV CSV files."""

from __future__ import annotations

import csv  # write/read canonical CSVs
from pathlib import Path  # portable filesystem paths
from typing import Iterable, List

RAW_HEADER = ["Symbol", "Date", "Close/Last", "Volume", "Open", "High", "Low"]  # canonical header


def write_raw_csv(rows: Iterable[dict], target: Path) -> None:
    """
    Persist rows to data/raw/ in canonical order (newest date at the top).

    Provider-specific scripts (Massive, Alpaca, etc.) call this helper so every CSV
    is formatted identically no matter where the data originated.
    """
    ordered = sorted(rows, key=lambda row: row.get("Date", ""), reverse=True)  # newest → oldest
    target.parent.mkdir(parents=True, exist_ok=True)  # ensure directory exists
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_HEADER)
        writer.writeheader()
        for row in ordered:  # stream rows so large fetches stay memory-light
            writer.writerow(row)


def load_raw_rows(csv_path: Path) -> List[dict]:
    """
    Read an existing canonical CSV into memory.

    Returns an empty list when the file does not exist yet. Callers can reuse the
    returned rows regardless of which provider originally produced them.
    """
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [_normalize_row(row) for row in reader if row]


def merge_rows(existing_rows: Iterable[dict], new_rows: Iterable[dict]) -> List[dict]:
    """
    Combine historical rows with newly fetched rows, preferring the newest data.

    Rows are de-duplicated by `date`, allowing actions to backfill overlapping ranges
    without creating duplicate entries.
    """
    merged = {row["Date"]: row for row in existing_rows if row.get("Date")}
    for row in new_rows:
        merged[row["Date"]] = row  # overwrite older values with fresh data
    return [merged[key] for key in sorted(merged)]  # ascending order; writer handles reversal


def extract_dates(rows: Iterable[dict]) -> set[str]:
    """Return a set of ISO dates contained in the provided rows."""
    return {row.get("Date", "") for row in rows if row.get("Date")}


def _normalize_row(row: dict) -> dict:
    """Map mixed-case legacy headers into the canonical schema."""
    return {
        "Symbol": row.get("Symbol") or row.get("symbol") or row.get("ticker") or "",
        "Date": row.get("Date") or row.get("date") or "",
        "Close/Last": row.get("Close/Last") or row.get("close") or row.get("Close") or "",
        "Volume": row.get("Volume") or row.get("volume") or "",
        "Open": row.get("Open") or row.get("open") or "",
        "High": row.get("High") or row.get("high") or "",
        "Low": row.get("Low") or row.get("low") or "",
    }
