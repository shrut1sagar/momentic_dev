"""Massive-specific helpers for downloading historical OHLCV data."""

from __future__ import annotations

import json  # parse Massive responses
import ssl  # HTTPS context
import urllib.error  # HTTP error handling
import urllib.request  # stdlib HTTP client
from datetime import datetime, timezone  # convert epoch millis to ISO date strings
from typing import List

AGG_TEMPLATE = "/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=50000"


def fetch_daily_ohlcv(symbol: str, start: str, end: str, base_url: str, api_key: str) -> List[dict]:
    """
    Query Massive's aggregate endpoint and return canonical OHLCV rows.

    Each row matches the RAW_HEADER schema defined in src/data/fetch_history.py.
    """
    path = AGG_TEMPLATE.format(symbol=symbol.upper(), start=start, end=end)  # build query path
    url = _attach_key(f"{base_url.rstrip('/')}{path}", api_key)  # add apiKey to query string
    ctx = ssl.create_default_context()  # standard TLS context
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "momentic/0.0.1",  # tiny UA for server logs
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15, context=ctx) as response:
            body = json.loads(response.read().decode() or "{}")  # parse JSON payload
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Massive returned HTTP {error.code} for {symbol}") from error
    except Exception as exc:
        raise RuntimeError(f"Massive request failed for {symbol}: {exc}") from exc

    results = body.get("results") or []  # guard against missing results key
    rows: List[dict] = []
    for entry in results:
        timestamp = entry.get("t")
        rows.append(
            {
                "Symbol": symbol.upper(),
                "Date": _ms_to_date(timestamp) if timestamp is not None else "",
                "Close/Last": entry.get("c"),
                "Volume": entry.get("v"),
                "Open": entry.get("o"),
                "High": entry.get("h"),
                "Low": entry.get("l"),
            }
        )
    if not rows:
        raise RuntimeError(f"No OHLCV data returned for {symbol} {start}→{end}")
    return rows


def _attach_key(url: str, api_key: str) -> str:
    """Append the Massive apiKey query parameter to any URL."""
    return f"{url}&apiKey={api_key}" if "?" in url else f"{url}?apiKey={api_key}"


def _ms_to_date(ms: int) -> str:
    """Convert Massive's millisecond timestamps to ISO YYYY-MM-DD strings."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
