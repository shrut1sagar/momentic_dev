"""Build indicator CSVs (moving averages + logistic spreads + velocity)."""

from __future__ import annotations

from data import io as data_io  # centralized CSV helpers
from datetime import datetime  # convert string dates to datetime objects
from pathlib import Path  # filesystem helpers
from typing import Dict, List, Sequence, Tuple  # type annotations

from utils.math import (
    logistic_spread_scaled,
    moving_average,
    percentage_change,
    sigmoid,
)  # shared math helpers

# Configuration constants for clarity and reuse.
RAW_HEADER = ["Symbol", "Date", "Close/Last", "Volume", "Open", "High", "Low"]
FEATURE_HEADER = [
    "Date",
    "Close",
    "MA_50",
    "MA_120",
    "MA_280",
    "logistic_ma_spread_50_120",
    "logistic_ma_spread_50_280",
    "logistic_return_scaled_21",
    "momentum_positive_bonus",
    "logistic_ma_spread_50_120_complement",
    "logistic_ma_spread_50_280_complement",
    "logistic_return_scaled_21_complement",
    "momentum_positive_bonus_complement",
    "long_term_down",
]
REQUIRED_WINDOWS = {50, 120, 280}
LOGISTIC_K1 = 0.05
LOGISTIC_K2 = 0.08
VELOCITY_LOOKBACK = 21
VELOCITY_SCALE = 0.07
MOMENTUM_SCALE = 0.10


def build_moving_average_csv(
    ticker: str,
    raw_dir: Path,
    processed_dir: Path,
    windows: Sequence[int] = (50, 120, 280),
) -> Path:
    """Read data/raw/{ticker}.csv and write data/processed/{ticker}_indicators.csv."""
    raw_path = raw_dir / f"{ticker}.csv"  # raw Massive CSV path
    output_path = processed_dir / f"{ticker}_indicators.csv"  # processed output path
    rows = data_io.read_csv(raw_path)  # newest-first rows
    if not rows:
        raise FileNotFoundError(f"No data found at {raw_path}")  # fail fast for missing data
    closes = _parse_closes(rows)  # sorted (oldest→newest) tuples
    missing = REQUIRED_WINDOWS - set(windows)  # ensure all mandatory MAs exist
    if missing:
        raise ValueError(f"Missing required windows: {missing}")
    ma_by_window = _compute_moving_averages(closes, windows)  # cache MA results
    processed_rows: List[List[str | float]] = []
    for idx in reversed(range(len(closes))):  # iterate newest→oldest for output
        processed_rows.append(_build_feature_row(closes, idx, ma_by_window))
    data_io.write_csv(output_path, FEATURE_HEADER, processed_rows)
    return output_path


def _parse_closes(rows: List[dict]) -> List[Tuple[datetime, float]]:
    """Convert raw rows into `(datetime, close)` tuples sorted oldest→newest."""
    return sorted(
        [(_parse_date(row["Date"]), _parse_close(row["Close/Last"])) for row in rows],
        key=lambda item: item[0],
    )


def _compute_moving_averages(
    closes: List[Tuple[datetime, float]],
    windows: Sequence[int],
) -> Dict[int, List[Tuple[datetime, float | None]]]:
    """Return moving-average results per window using the shared math helper."""
    return {window: moving_average(closes, window) for window in windows}


def _build_feature_row(
    closes: List[Tuple[datetime, float]],
    index: int,
    ma_by_window: Dict[int, List[Tuple[datetime, float | None]]],
) -> List[str | float]:
    """Assemble columns in canonical order (Date, Close, MAs, spreads, velocity)."""
    date_obj, close = closes[index]
    ma50 = ma_by_window[50][index][1]
    ma120 = ma_by_window[120][index][1]
    ma280 = ma_by_window[280][index][1]
    logistic_50_120 = _logistic_spread(ma50, ma120, LOGISTIC_K1)
    logistic_50_280 = _logistic_spread(ma50, ma280, LOGISTIC_K2)
    logistic_return = _logistic_return(closes, index, VELOCITY_LOOKBACK, VELOCITY_SCALE)
    momentum_bonus = _momentum_positive_bonus(
        closes,
        index,
        VELOCITY_LOOKBACK,
        MOMENTUM_SCALE,
    )
    long_term_down = _long_term_down(logistic_50_280)
    return [
        date_obj.strftime("%Y-%m-%d"),
        close,
        _cell(ma50),
        _cell(ma120),
        _cell(ma280),
        _cell(logistic_50_120),
        _cell(logistic_50_280),
        _cell(logistic_return),
        _cell(momentum_bonus),
        _complement(logistic_50_120),
        _complement(logistic_50_280),
        _complement(logistic_return),
        _complement(momentum_bonus),
        long_term_down,
    ]


def _parse_date(date_str: str) -> datetime:
    """Parse dates in several expected formats (ISO or DD/MM/YYYY, etc.)."""
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str.strip(), pattern)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {date_str!r}")


def _parse_close(value: str) -> float:
    """Convert 'Close/Last' string (e.g., '$100.21') into float."""
    return float(value.strip().replace("$", "").replace(",", ""))


def _logistic_spread(a: float | None, b: float | None, scale: float) -> float | None:
    """Compute logistic spread when both inputs are present."""
    if a is None or b is None or b == 0 or scale == 0:
        return None
    return logistic_spread_scaled(a, b, scale)


def _logistic_return(
    closes: List[Tuple[datetime, float]],
    index: int,
    lookback: int,
    scale: float,
) -> float | None:
    """Compute sigmoid((close_t - close_{t-L}) / close_{t-L} / scale); blank when insufficient history."""
    if index < lookback:
        return None
    _, past_close = closes[index - lookback]
    if past_close == 0 or scale == 0:
        return None
    relative_change = (closes[index][1] - past_close) / past_close
    return sigmoid(relative_change / scale)


def _momentum_positive_bonus(
    closes: List[Tuple[datetime, float]],
    index: int,
    lookback: int,
    scale: float,
) -> float | None:
    """Compute momentum bonus based on normalized velocity changes."""
    # Need two full lookback periods (current and prior).
    if index < lookback * 2 or scale == 0:
        return None

    # Current and previous 21-day returns using percentage change.
    current_close = closes[index][1]
    prev_close = closes[index - lookback][1]
    earlier_close = closes[index - lookback][1]
    earlier_prev_close = closes[index - lookback * 2][1]

    # Avoid division-by-zero scenarios.
    if prev_close == 0 or earlier_prev_close == 0:
        return None

    current_return = percentage_change(current_close, prev_close)
    previous_return = percentage_change(earlier_close, earlier_prev_close)

    # Momentum change scaled by K4.
    momentum_change = (current_return - previous_return) / scale
    score = (sigmoid(momentum_change) - 0.5) * 2
    return max(score, 0.0)


def _long_term_down(logistic_spread: float | None) -> int | str:
    """Return 1 when the logistic MA 50 vs 280 spread is below 0.5, else 0 (blank when missing)."""
    if logistic_spread is None:
        return ""
    return 1 if logistic_spread < 0.5 else 0


def _cell(value: float | None) -> float | str:
    """Return numeric value when available, otherwise blank string for CSV."""
    return value if value is not None else ""


def _complement(value: float | None) -> float | str:
    """Return 1 - value when numeric, otherwise blank."""
    return (1.0 - value) if value is not None else ""
