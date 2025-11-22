"""Common math helpers reused across analytics, strategies, and backtesting."""

from __future__ import annotations

import math  # lightweight numerical helpers
from datetime import datetime
from typing import Iterable, List, Sequence, Tuple


def moving_average(series: Sequence[Tuple[datetime, float]], window: int) -> List[Tuple[datetime, float | None]]:
    """
    Compute a simple moving average over a `(date, price)` sequence.

    The result preserves the date order; the first `window-1` entries will have `None`
    for the moving-average value because there are not enough prior observations yet.
    """
    if window <= 0:
        raise ValueError("window must be a positive integer")
    if not series:
        return []

    values: List[Tuple[datetime, float | None]] = []
    rolling_sum = 0.0
    buffer: List[float] = []

    for date, price in series:
        buffer.append(price)
        rolling_sum += price
        if len(buffer) > window:
            rolling_sum -= buffer.pop(0)
        avg = rolling_sum / window if len(buffer) == window else None
        values.append((date, avg))
    return values


def sigmoid(x: float) -> float:
    """Logistic sigmoid function σ(x) = 1 / (1 + e^{-x})."""
    return 1.0 / (1.0 + math.exp(-x))


def percentage_change(current: float, previous: float) -> float:
    """
    Compute the relative change between two observations.

    Defined as (current - previous) / previous; caller should guard against division by zero.
    """
    if previous == 0:
        raise ZeroDivisionError("previous value must be non-zero for normalized velocity")
    return (current - previous) / previous


def logistic_spread_scaled(numerator: float, denominator: float, scale: float) -> float:
    """
    Compute sigmoid((n - m) / (m * k)).

    Args:
        numerator: First observation (n).
        denominator: Second observation (m), must be non-zero.
        scale: Scalar multiplier (k).

    Returns:
        Sigmoid-transformed scaled spread.
    """
    if denominator == 0 or scale == 0:
        raise ZeroDivisionError("denominator and scale must be non-zero")
    spread = (numerator - denominator) / (denominator * scale)
    return sigmoid(spread)


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a numeric value between inclusive bounds."""
    return max(lower, min(value, upper))


def daily_returns(prices: Sequence[float]) -> List[float]:
    """Convert a price series into simple returns."""
    returns: List[float] = []
    for idx in range(1, len(prices)):
        previous = prices[idx - 1]
        current = prices[idx]
        if previous == 0:
            returns.append(0.0)
        else:
            returns.append((current / previous) - 1.0)
    return returns


def rolling_std(values: Sequence[float], window: int) -> List[float]:
    """Compute a simple rolling standard deviation."""
    if window <= 0:
        raise ValueError("window must be positive")
    result: List[float] = []
    buffer: List[float] = []
    for value in values:
        buffer.append(value)
        if len(buffer) > window:
            buffer.pop(0)
        if len(buffer) == window:
            mean = sum(buffer) / window
            variance = sum((x - mean) ** 2 for x in buffer) / window
            result.append(math.sqrt(variance))
    return result


def annualized_volatility(prices: Sequence[float], window: int = 63, trading_days: int = 252) -> float:
    """Return the latest annualized realized volatility."""
    returns = daily_returns(prices)
    if len(returns) < window:
        return 0.0
    std_values = rolling_std(returns, window)
    if not std_values:
        return 0.0
    return std_values[-1] * math.sqrt(trading_days)


def drawdown_vs_peak(values: Sequence[float]) -> List[float]:
    """Compute cumulative drawdown series (value / max - 1)."""
    drawdowns: List[float] = []
    peak = float("-inf")
    for value in values:
        peak = max(peak, value)
        drawdowns.append((value / peak) - 1.0 if peak > 0 else 0.0)
    return drawdowns
