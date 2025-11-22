"""Risk analytics helpers: realized volatility, drawdown, and cooldown logic."""

from __future__ import annotations

from datetime import date
from typing import List, Sequence

from utils.math import annualized_volatility, drawdown_vs_peak


def realized_volatility(prices: Sequence[float], window: int = 63) -> float:
    """
    Compute annualized realized volatility using the provided price series.

    The function delegates the heavy lifting to utils.math.annualized_volatility but adds
    a small guard to ensure the input is long enough for the requested window.
    """
    if len(prices) < window + 1:
        return 0.0
    return annualized_volatility(prices, window=window)


def drawdowns(prices: Sequence[float]) -> List[float]:
    """
    Return a drawdown time series (value / running max - 1).

    Negative values indicate drops from the recent peak. The latest value is today’s drawdown.
    """
    if not prices:
        return []
    return drawdown_vs_peak(prices)


def last_stop_index(drawdown_values: Sequence[float], stop_level: float) -> int | None:
    """
    Locate the most recent index where drawdown breached the negative stop threshold.

    Returns the index of the breach (0-based) or None when no stop has been triggered.
    """
    trigger = -abs(stop_level)
    for idx in range(len(drawdown_values) - 1, -1, -1):
        if drawdown_values[idx] <= trigger:
            return idx
    return None


def cooldown_active(
    dates: Sequence[date],
    last_stop_idx: int | None,
    cooldown_days: int,
) -> tuple[bool, int]:
    """
    Determine whether the cooldown window is still active after a stop.

    Returns a tuple `(active, days_since_stop)` for transparency. If no stop occurred,
    `(False, 0)` is returned.
    """
    if last_stop_idx is None or not dates:
        return False, 0
    days_since = len(dates) - (last_stop_idx + 1)
    return days_since < cooldown_days, days_since
