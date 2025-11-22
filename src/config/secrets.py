#!/usr/bin/env python3  # use system Python 3
"""Load secrets from the repo-root .env (gitignored) or process env."""  # module purpose

from __future__ import annotations  # future annotations
import os  # access process environment variables
from pathlib import Path  # build portable paths

ROOT = Path(__file__).resolve().parents[2]  # go from src/config/ to repo root
DOTENV = ROOT / ".env"  # expected path of the gitignored .env file


def _parse_dotenv(path: Path) -> dict[str, str]:  # minimal KEY=VALUE parser
    print(f"[secrets] reading {path}")  # echo which file we’ll read
    env: dict[str, str] = {}  # hold parsed keys
    if not path.exists():  # if there is no .env file
        print("[secrets] .env not found; will use process env only")  # echo fallback
        return env  # return empty dict
    for raw in path.read_text().splitlines():  # iterate lines
        line = raw.strip()  # trim whitespace
        if not line or line.startswith("#") or "=" not in line:  # skip blanks/comments/bad lines
            continue  # ignore
        k, v = line.split("=", 1)  # split KEY=VALUE once
        env[k.strip()] = v.strip().strip("'").strip('"')  # store dequoted value
    print(f"[secrets] .env keys: {', '.join(env) or 'none'}")  # echo which keys were found
    return env  # return parsed mapping


def massive_credentials() -> tuple[str, str]:  # return (base_url, api_key) for Massive
    env = {**_parse_dotenv(DOTENV), **os.environ}  # merge .env then overlay with process env
    base = (env.get("MASSIVE_BASE_URL") or "https://api.massive.example").strip()  # read base URL with default
    if not base.startswith(("http://", "https://")):  # ensure scheme
        base = "https://" + base  # prefix https when missing
    key = (env.get("MASSIVE_API_KEY") or "").strip()  # read API key
    if not key:  # enforce presence
        raise ValueError("MASSIVE_API_KEY missing in .env or environment")  # clear remediation
    print(f"[secrets] MASSIVE_BASE_URL = {base}")  # echo base URL
    tail = key[-4:] if len(key) >= 4 else ""  # mask key tail
    print(f"[secrets] MASSIVE_API_KEY  = ****{tail}")  # echo masked key tail
    return base.rstrip("/"), key  # normalize base URL and return tuple
