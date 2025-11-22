#!/usr/bin/env python3  # run with system Python 3
"""Minimal Massive client: stdlib HTTPS ping only, tiny and reusable."""  # module purpose

from __future__ import annotations  # future annotations

import json  # parse responses
import ssl  # TLS context
import urllib.error  # handle HTTP errors
import urllib.request  # perform HTTPS requests

HEALTH_PATHS = ("/v1/health", "/health", "/status", "/")  # common health endpoints to try


class MassiveClient:  # tiny API client
    def __init__(self, base_url: str, api_key: str, timeout: float = 5.0):  # constructor
        self.u = base_url.rstrip("/")  # store normalized base URL
        self.k = api_key  # store bearer token
        self.t = timeout  # store timeout seconds
        self.ctx = ssl.create_default_context()  # TLS context for HTTPS
        print(f"[massive] client for {self.u} ready")  # echo client setup

    def _get(self, path: str) -> dict:  # internal GET helper → normalized dict
        url = f"{self.u}{path}"  # build full URL
        req = urllib.request.Request(  # construct request with headers
            url,
            headers={
                "Authorization": f"Bearer {self.k}",  # auth header
                "Accept": "application/json",  # ask for JSON
                "User-Agent": "momentic/0.0.1",  # simple UA
            },
        )
        try:  # attempt HTTPS call
            with urllib.request.urlopen(req, timeout=self.t, context=self.ctx) as resp:
                raw = resp.read()  # read response bytes
                body = json.loads(raw.decode() or "{}") if raw else {}  # parse JSON or empty
                return {"ok": resp.status < 400, "code": resp.status, "body": body, "url": url}
        except urllib.error.HTTPError as err:  # HTTP error with status code
            try:
                body = json.loads((err.read() or b"").decode())
            except Exception:
                body = {}
            return {"ok": False, "code": err.code, "body": body, "url": url}
        except Exception as exc:  # network/SSL/timeout etc.
            return {
                "ok": False,
                "code": None,
                "body": {"error": f"{type(exc).__name__}: {exc}"},
                "url": url,
            }

    def ping(self) -> dict:  # public health check method
        print("[massive] ping: trying health endpoints…")  # echo start
        last = None  # track last attempt
        for path in HEALTH_PATHS:  # iterate possible endpoints
            print(f"[massive] GET {path}")  # echo which path we try
            last = self._get(path)  # perform GET
            if last["ok"]:  # if succeeded
                print(f"[massive] OK {last['code']} via {path}")  # echo success
                return {"status": "ok", "probe": last}  # return ok result
        print("[massive] no endpoint responded; marking as degraded")  # echo failure
        return {"status": "degraded", "probe": last or {}}  # return degraded with last probe
