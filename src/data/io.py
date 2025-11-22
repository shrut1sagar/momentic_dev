"""Centralized read/write helpers for CSVs and settings files."""

from __future__ import annotations

import json  # fallback parser for settings
from pathlib import Path  # filesystem handling
from typing import Iterable, List, Sequence


def read_csv(path: Path) -> List[dict]:
    """
    Read a CSV file into a list of dictionaries.

    This helper normalizes different newline encodings and leaves column names untouched.
    """
    import csv  # imported lazily to keep module scope minimal

    if not path.exists():
        raise FileNotFoundError(f"CSV not found at {path}")
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """
    Write rows to a CSV file with the provided header.

    The function creates the parent directory automatically and overwrites existing files.
    """
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def write_report(path: Path, lines: Sequence[str]) -> None:
    """Write a plain-text report with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


DEFAULT_SETTINGS = {
    "target_vol": 0.12,
    "vol_threshold": 0.22,
    "max_drawdown_stop": 0.15,
    "cooldown_days": 10,
    "entry_thresholds": {
        "LOW_VOL": {"long": 0.60, "short": 0.65},
        "HIGH_VOL": {"long": 0.70, "short": 0.75},
    },
    "exit_threshold": 0.45,
    "weights": {
        "up": {
            "logistic_ma_spread_50_120": 0.18,
            "logistic_ma_spread_50_280": 0.57,
            "logistic_return_scaled_21": 0.20,
            "momentum_positive_bonus": 0.05,
        },
        "down": {
            "logistic_ma_spread_50_120": 0.12,
            "logistic_ma_spread_50_280": 0.68,
            "logistic_return_scaled_21": 0.15,
            "momentum_positive_bonus": 0.05,
        },
    },
}


def load_settings(path: Path | None) -> dict:
    """
    Load settings from YAML-like text; fall back to defaults when file missing.

    A minimal parser is implemented to avoid additional dependencies. The format accepts
    simple "key: value" pairs (or JSON). Nested dictionaries are expected for entry thresholds.
    """
    settings = DEFAULT_SETTINGS.copy()
    if path is None or not path.exists():
        return settings
    raw_text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
    try:
        data = yaml.safe_load(raw_text) if yaml else json.loads(raw_text)
    except Exception:
        data = _parse_simple_mapping(raw_text)
    _deep_update(settings, data)
    return settings


def _parse_simple_mapping(text: str) -> dict:
    """Parse very simple `key: value` lines into a dictionary."""
    mapping: dict[str, object] = {}
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#") or ":" not in cleaned:
            continue
        key, value = cleaned.split(":", 1)
        mapping[key.strip()] = _coerce(value.strip())
    return mapping


def _coerce(value: str) -> object:
    """Attempt to convert strings into bool/int/float, else leave as string."""
    lowered = value.lower()
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def _deep_update(base: dict, updates: dict | None) -> None:
    """Recursively merge dictionaries (used for settings overrides)."""
    if not updates:
        return
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)  # type: ignore[index]
        else:
            base[key] = value
