"""Daily signal engine that follows the documented 10-step workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

from analytics import risk_metrics
from data import io as data_io
from utils.math import clamp

# ---------------------------------------------------------------------------
# Simple containers for clarity
# ---------------------------------------------------------------------------


@dataclass
class SignalResult:
    """Small structure returned to the CLI and report writer."""

    date: str
    regime: str
    trend: str
    score_up: float
    score_dn: float
    take_long: bool
    take_short: bool
    long_weight: float
    short_weight: float
    cash_weight: float
    notes: List[str]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


VERBOSE = True


def run_signal_engine(
    csv_path: Path,
    settings_path: Path | None = None,
    report_path: Path | None = None,
    signal_date: str | None = None,
) -> SignalResult:
    """
    Execute the end-to-end signal engine.

    Steps mirror the spec exactly:
    1. Load data/settings.
    2. Compute risk metrics (volatility/drawdown/cooldown).
    3. Prepare features & scores.
    4. Apply entry/exit gates.
    5. Size positions, resolve conflicts, and emit a report.
    """
    settings = data_io.load_settings(settings_path)
    rows = data_io.read_csv(csv_path)
    normalized_rows = [_normalize_row(row) for row in rows]

    dated_rows = [
        (datetime.strptime(row["date"], "%Y-%m-%d").date(), row) for row in normalized_rows
    ]
    latest_available = max(date for date, _ in dated_rows)
    if signal_date:
        target_date = datetime.strptime(signal_date, "%Y-%m-%d").date()
        if target_date > latest_available:
            raise ValueError(
                f"Requested date {signal_date} exceeds latest available {latest_available}"
            )
    else:
        target_date = latest_available

    filtered = [(date, row) for date, row in dated_rows if date <= target_date]
    if not filtered:
        raise ValueError("No data available on or before requested date.")

    filtered.sort(key=lambda pair: pair[0])
    closes = [row["close"] for _, row in filtered]
    dates = [date for date, _ in filtered]

    vol_today = risk_metrics.realized_volatility(closes)
    drawdowns = risk_metrics.drawdowns(closes)
    last_stop_idx = risk_metrics.last_stop_index(drawdowns, settings["max_drawdown_stop"])
    cooldown_active, days_since_stop = risk_metrics.cooldown_active(
        dates,
        last_stop_idx,
        settings["cooldown_days"],
    )

    latest = filtered[-1][1]
    trend = _trend_label(latest)
    regime = "LOW_VOL" if vol_today <= settings["vol_threshold"] else "HIGH_VOL"
    thresholds = settings["entry_thresholds"][regime]

    features = _prepare_features(latest)
    score_up = _score(features["up"], settings["weights"]["up"])
    score_dn = _score(features["down"], settings["weights"]["down"])
    long_term_down = features["long_term_down"]

    gate = _apply_gates(
        score_up,
        score_dn,
        regime,
        long_term_down,
        cooldown_active,
        thresholds,
        settings["exit_threshold"],
    )

    long_weight, short_weight, vol_note = _size_positions(
        vol_today,
        regime,
        gate["take_long"],
        gate["take_short"],
        settings["target_vol"],
    )

    long_weight, short_weight = _resolve_conflict(
        long_weight,
        short_weight,
        score_up - thresholds["long"],
        score_dn - thresholds["short"],
    )
    cash_weight = clamp(1.0 - (long_weight + short_weight), 0.0, 1.0)

    notes = _build_notes(
        regime=regime,
        vol=vol_today,
        cooldown_active=cooldown_active,
        days_since_stop=days_since_stop,
        gate=gate,
        long_weight=long_weight,
        short_weight=short_weight,
        vol_note=vol_note,
        vol_threshold=settings["vol_threshold"],
        score_up=score_up,
        score_dn=score_dn,
        long_term_down=long_term_down,
        trend=trend,
        asset_vol=vol_today * 3,
    )

    result = SignalResult(
        date=latest["date"],
        regime=regime,
        trend=trend,
        score_up=score_up,
        score_dn=score_dn,
        take_long=gate["take_long"],
        take_short=gate["take_short"],
        long_weight=long_weight,
        short_weight=short_weight,
        cash_weight=cash_weight,
        notes=notes,
    )

    if report_path is not None:
        data_io.write_report(
            report_path,
            _format_report(
                result=result,
                source_path=csv_path,
                vol_threshold=settings["vol_threshold"],
            ),
        )
    return result


# ---------------------------------------------------------------------------
# Helpers (each heavily commented to stay human readable)
# ---------------------------------------------------------------------------


def _normalize_row(row: dict) -> dict:
    """
    Normalize column names and convert strings to floats.

    Missing engineered features are set to 0.5 (neutral) as per the spec.
    """
    mapping = {key.lower(): value for key, value in row.items()}

    def to_float(key: str, default: float | None = None) -> float:
        value = mapping.get(key)
        if value in (None, "", "NA"):
            if default is None:
                raise ValueError(f"Missing required column {key}")
            return default
        return float(value)

    normalized = {
        "date": mapping.get("date"),
        "close": to_float("close"),
        "ma_50": mapping.get("ma_50"),
        "ma_120": mapping.get("ma_120"),
        "ma_280": mapping.get("ma_280"),
        "logistic_ma_spread_50_120": to_float("logistic_ma_spread_50_120", 0.5),
        "logistic_ma_spread_50_280": to_float("logistic_ma_spread_50_280", 0.5),
        "logistic_return_scaled_21": to_float("logistic_return_scaled_21", 0.5),
        "momentum_positive_bonus": to_float("momentum_positive_bonus", 0.5),
        "logistic_ma_spread_50_120_complement": mapping.get("logistic_ma_spread_50_120_complement"),
        "logistic_ma_spread_50_280_complement": mapping.get("logistic_ma_spread_50_280_complement"),
        "logistic_return_scaled_21_complement": mapping.get("logistic_return_scaled_21_complement"),
        "momentum_positive_bonus_complement": mapping.get("momentum_positive_bonus_complement"),
        "long_term_down": mapping.get("long_term_down"),
    }
    return normalized


def _trend_label(row: dict) -> str:
    """Derive the trend label based on moving averages or feature fallbacks."""
    ma50 = _maybe_float(row.get("ma_50"))
    ma120 = _maybe_float(row.get("ma_120"))
    ma280 = _maybe_float(row.get("ma_280"))
    if None not in (ma50, ma120, ma280):
        if ma50 > ma120 > ma280:
            return "UPTREND"
        if ma50 < ma120 < ma280:
            return "DOWNTREND"
        return "SIDEWAYS"
    rel = row["logistic_ma_spread_50_280"]
    vel = row["logistic_return_scaled_21"]
    if rel >= 0.55 and vel >= 0.55:
        return "UPTREND"
    if rel <= 0.45 and vel <= 0.45:
        return "DOWNTREND"
    return "SIDEWAYS"


def _prepare_features(row: dict) -> dict:
    """Create bullish and bearish feature dictionaries plus the long-term flag."""
    up = {
        "logistic_ma_spread_50_120": row["logistic_ma_spread_50_120"],
        "logistic_ma_spread_50_280": row["logistic_ma_spread_50_280"],
        "logistic_return_scaled_21": row["logistic_return_scaled_21"],
        "momentum_positive_bonus": row["momentum_positive_bonus"],
    }
    down = {
        key: _feature_down(key, row, value)
        for key, value in up.items()
    }
    long_term_down_value = row.get("long_term_down")
    if long_term_down_value in (None, "", "NA"):
        long_term_down = 1 if up["logistic_ma_spread_50_280"] < 0.5 else 0
    else:
        long_term_down = int(float(long_term_down_value))
    return {"up": up, "down": down, "long_term_down": long_term_down}


def _feature_down(key: str, row: dict, value: float) -> float:
    """Use provided complement columns when available; otherwise mirror."""
    complement_key = f"{key}_complement"
    complement_value = row.get(complement_key)
    if complement_value not in (None, "", "NA"):
        return float(complement_value)
    return 1.0 - value


def _score(features: Dict[str, float], weights: Dict[str, float]) -> float:
    """Dot-product helper for weighted sums."""
    return sum(weights[name] * features[name] for name in weights)


def _apply_gates(
    score_up: float,
    score_dn: float,
    regime: str,
    long_term_down: int,
    cooldown_active: bool,
    thresholds: dict,
    exit_threshold: float,
) -> dict:
    """Apply entry/exit thresholds and cooldown overrides."""
    take_long = score_up >= thresholds["long"]
    if regime == "HIGH_VOL" and score_up < 0.70:
        take_long = False
    take_short = score_dn >= thresholds["short"]
    if regime == "HIGH_VOL" and not (long_term_down or score_dn >= 0.80):
        take_short = False
    if take_long and score_up < exit_threshold:
        take_long = False
    if take_short and score_dn < exit_threshold:
        take_short = False
    if cooldown_active:
        take_long = False
        take_short = False
    return {"take_long": take_long, "take_short": take_short}


def _size_positions(
    vol_today: float,
    regime: str,
    take_long: bool,
    take_short: bool,
    target_vol: float,
) -> tuple[float, float, str]:
    """Size positions using volatility targeting heuristics."""
    asset_vol = vol_today * 3  # approximation for TQQQ/SQQQ
    if asset_vol <= 0:
        return 0.0, 0.0, "σ63 unavailable"
    weight = min(target_vol / asset_vol, 1.0)
    if regime == "HIGH_VOL":
        weight *= 0.5
    long_weight = weight if take_long else 0.0
    short_weight = weight if take_short else 0.0
    return long_weight, short_weight, f"σ63={vol_today * 100:.2f}%"


def _resolve_conflict(
    long_weight: float,
    short_weight: float,
    margin_long: float,
    margin_short: float,
) -> tuple[float, float]:
    """Ensure only one side is active when both qualify."""
    if long_weight > 0 and short_weight > 0:
        if margin_long >= margin_short:
            short_weight = 0.0
        else:
            long_weight = 0.0
    return long_weight, short_weight


def _build_notes(
    regime: str,
    vol: float,
    cooldown_active: bool,
    days_since_stop: int,
    gate: dict,
    long_weight: float,
    short_weight: float,
    vol_note: str,
    vol_threshold: float,
    score_up: float,
    score_dn: float,
    long_term_down: int,
    trend: str,
    asset_vol: float,
) -> List[str]:
    """Collect human-readable commentary for the report."""
    return [
        f"- Regime: {regime} ({vol_note}, threshold={vol_threshold * 100:.2f}%)",
        f"- Cooldown active: {'yes' if cooldown_active else 'no'} (days since stop: {days_since_stop})",
        f"Scores: up={score_up:.3f}, down={score_dn:.3f}, long_term_down={bool(long_term_down)}, regime={trend}",
        _action_line(gate, long_weight, short_weight, asset_vol),
    ]


def _action_line(gate: dict, long_weight: float, short_weight: float, asset_vol: float) -> str:
    """Describe which side (if any) is taken along with approximate asset vol."""
    asset_vol_pct = asset_vol * 100
    if gate["take_long"] and long_weight > 0:
        return f"- Taking LONG (TQQQ) at {long_weight * 100:.2f}% (σ≈{asset_vol_pct:.2f}%)"
    if gate["take_short"] and short_weight > 0:
        return f"- Taking SHORT (SQQQ) at {short_weight * 100:.2f}% (σ≈{asset_vol_pct:.2f}%)"
    return "- Staying in cash (no qualifying signal)"


def _format_report(
    result: SignalResult,
    source_path: Path,
    vol_threshold: float,
) -> List[str]:
    """Convert the SignalResult into the requested report layout."""
    header = [
        f"Source file: {source_path}",
        f"Date: {result.date}",
        f"Trend regime: {result.trend}",
        "",
        f"TQQQ target: {result.long_weight * 100:.2f}%",
        f"SQQQ target: {result.short_weight * 100:.2f}%",
        f"CASH target: {result.cash_weight * 100:.2f}%",
        "",
        "Notes:",
    ]
    return header + result.notes


def _maybe_float(value: str | float | None) -> float | None:
    """Convert strings into floats when possible."""
    if value in (None, "", "NA"):
        return None
    return float(value)
    if VERBOSE:
        print("[signal-debug]")
        print("  regime:", regime)
        print("  vol_today:", f"{vol_today:.4f}")
        print("  cooldown_active:", cooldown_active)
        print("  days_since_stop:", days_since_stop)
        print("  gate:", gate)
        print("  long_weight:", f"{long_weight:.4f}")
        print("  short_weight:", f"{short_weight:.4f}")
        print("  vol_note:", vol_note)
        print("  vol_threshold:", settings["vol_threshold"])
        print("  score_up:", f"{score_up:.3f}")
        print("  score_dn:", f"{score_dn:.3f}")
        print("  long_term_down:", long_term_down)
        print("  trend:", trend)
        print("  asset_vol:", f"{vol_today * 3:.4f}")
