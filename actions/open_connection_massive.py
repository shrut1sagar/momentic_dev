#!/usr/bin/env python3  # run with system Python 3
"""Standalone Massive check: fetch real JSON for a ticker (default 'AA') and persist status."""  # purpose

from __future__ import annotations  # future annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOTENV = ROOT / ".env"
STATE = ROOT / "state"
OUT = STATE / "connections.json"
DEFAULT_TICKER = "AA"


def _load_dotenv() -> dict[str, str]:
    print(f"[env] loading {DOTENV}")
    env: dict[str, str] = {}
    if DOTENV.exists():
        for raw in DOTENV.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'").strip('"')
    env.update(os.environ)
    return env


def _build_probe_path(ticker: str) -> str:
    return f"/v3/reference/tickers?ticker={ticker}&limit=1"


def _with_key(base: str, path: str, key: str) -> str:
    sep = "&" if "?" in path else "?"
    return f"{base.rstrip('/')}{path}{sep}apiKey={key}"


def _get_json(url: str) -> dict:
    print(f"[http] GET {url}")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "momentic/0.0.1",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=6.0, context=ctx) as response:
            raw = response.read()
            body = json.loads(raw.decode() or "{}") if raw else {}
            print(f"[http] OK {response.status}")
            return {"ok": response.status < 400, "code": response.status, "body": body}
    except urllib.error.HTTPError as error:
        try:
            body = json.loads((error.read() or b"").decode())
        except Exception:
            body = {}
        print(f"[http] HTTP {error.code}")
        return {"ok": False, "code": error.code, "body": body}
    except Exception as exc:
        print(f"[http] ERROR {type(exc).__name__}: {exc}")
        return {"ok": False, "code": None, "body": {"error": f"{type(exc).__name__}: {exc}"}}


def _finish(payload: dict, success: bool) -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"[action] wrote {OUT}")
    print(json.dumps(payload, indent=2))
    return 0 if success else 1


def main() -> int:
    ticker = DEFAULT_TICKER
    if len(sys.argv) > 1 and sys.argv[1].strip():
        ticker = sys.argv[1].strip().upper()
    print(f"[action] Massive connection check (ticker={ticker}) starting")
    env = _load_dotenv()
    base = (env.get("MASSIVE_BASE_URL") or "https://api.massive.com").strip()
    if not base.startswith(("http://", "https://")):
        base = "https://" + base
    key = (env.get("MASSIVE_API_KEY") or "").strip()
    if not key:
        print("[action] ERROR: MASSIVE_API_KEY missing")
        return _finish({"massive": {"status": "error", "error": "MASSIVE_API_KEY missing"}}, False)

    print(f"[action] base_url = {base}")
    tail = key[-4:] if len(key) >= 4 else ""
    print(f"[action] key = ****{tail}")

    probe_path = _build_probe_path(ticker)
    url = _with_key(base, probe_path, key)
    probe = _get_json(url)
    payload = {
        "massive": {
            "base_url": base,
            "ticker": ticker,
            "probe": {"path": probe_path, **probe},
            "status": "ok" if probe["ok"] else "degraded",
        }
    }
    print(f"[action] status = {payload['massive']['status']}")
    return _finish(payload, success=True)


if __name__ == "__main__":
    sys.exit(main())
