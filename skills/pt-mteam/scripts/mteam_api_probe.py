#!/usr/bin/env python3
"""Minimal M-Team API probe with guardrails + conservative rate limiting.

Usage:
  python3 scripts/mteam_api_probe.py --base https://api.m-team.cc --api-key xxx --method POST --path /api/member/profile --json '{}'
  python3 scripts/mteam_api_probe.py --base https://api.m-team.cc --api-key xxx --method POST --path /api/torrent/search --json '{"keyword":"test"}'
"""

from __future__ import annotations

import argparse
import fcntl
import json
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BLOCKED_PREFIXES = ("/api/admin/", "/admin/")
BLOCKED_EXACT = {"/api/login", "/login", "/api/apikey", "/apikey"}
DEFAULT_USER_AGENT = "Mozilla/5.0"
STATE_FILE = Path.home() / ".cache" / "pt-mteam-rate.json"
LOCK_FILE = Path.home() / ".cache" / "pt-mteam-rate.lock"


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_sleep: float = 0.8
    jitter: float = 0.4


def normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return path


def assert_allowed(path: str) -> None:
    p = normalize_path(path)
    if p in BLOCKED_EXACT or any(p.startswith(pref) for pref in BLOCKED_PREFIXES):
        raise ValueError(f"Blocked endpoint by policy: {p}")


def request_once(
    base: str,
    api_key: str,
    method: str,
    path: str,
    body: Optional[str],
    timeout: int,
    user_agent: str,
):
    url = base.rstrip("/") + normalize_path(path)
    data = body.encode("utf-8") if body is not None else None

    req = urllib.request.Request(url=url, method=method.upper(), data=data)
    req.add_header("x-api-key", api_key)
    req.add_header("accept", "application/json")
    req.add_header("user-agent", user_agent or DEFAULT_USER_AGENT)
    if data is not None:
        req.add_header("content-type", "application/json")

    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
        return resp.status, text, int((time.time() - started) * 1000)


def _bucket_for_path(path: str) -> str:
    p = normalize_path(path)
    if p.startswith("/api/torrent/search") or p.startswith("/torrent/search"):
        return "torrent_search"
    if p.startswith("/api/torrent/detail") or p.startswith("/torrent/detail"):
        return "torrent_detail"
    return "default"


def _interval_for_bucket(bucket: str, args) -> float:
    if bucket == "torrent_search":
        return max(0.0, float(args.search_interval))
    if bucket == "torrent_detail":
        return max(0.0, float(args.detail_interval))
    return max(0.0, float(args.min_interval))


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False))


def enforce_rate_limit(path: str, args) -> None:
    bucket = _bucket_for_path(path)
    interval = _interval_for_bucket(bucket, args)
    if interval <= 0:
        return

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        state = _load_state(STATE_FILE)
        now = time.time()
        last = float(state.get(bucket, 0) or 0)
        wait = interval - (now - last)
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        state[bucket] = now
        _save_state(STATE_FILE, state)
        fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="e.g. https://api.m-team.cc")
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--method", default="GET", choices=["GET", "POST", "PUT", "DELETE"])
    ap.add_argument("--path", required=True, help="e.g. /api/member/profile")
    ap.add_argument("--json", default=None, help="raw JSON string for request body")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="HTTP User-Agent header")
    ap.add_argument("--min-interval", type=float, default=1.0, help="default min interval seconds")
    ap.add_argument("--detail-interval", type=float, default=36.0, help="/torrent/detail min interval seconds")
    ap.add_argument("--search-interval", type=float, default=90.0, help="/torrent/search min interval seconds")
    args = ap.parse_args()

    try:
        assert_allowed(args.path)
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2

    if args.json is not None:
        try:
            json.loads(args.json)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"invalid --json: {e}"}, ensure_ascii=False))
            return 2

    policy = RetryPolicy(max_retries=max(0, args.max_retries))

    # Cross-process rate limit (conservative defaults from public guidance)
    enforce_rate_limit(args.path, args)

    for attempt in range(policy.max_retries + 1):
        try:
            status, text, elapsed_ms = request_once(
                base=args.base,
                api_key=args.api_key,
                method=args.method,
                path=args.path,
                body=args.json,
                timeout=args.timeout,
                user_agent=args.user_agent,
            )
            print(json.dumps({"ok": True, "status": status, "elapsedMs": elapsed_ms}, ensure_ascii=False))
            print(text)
            return 0
        except urllib.error.HTTPError as e:
            code = e.code
            payload = e.read().decode("utf-8", errors="replace")
            retriable = code in (429, 500, 502, 503, 504)
            auth_err = code in (401, 403)

            if auth_err:
                print(json.dumps({"ok": False, "status": code, "error": "auth/permission error", "body": payload}, ensure_ascii=False))
                return 3

            if retriable and attempt < policy.max_retries:
                sleep_s = policy.base_sleep * (2 ** attempt) + random.uniform(0, policy.jitter)
                time.sleep(sleep_s)
                continue

            print(json.dumps({"ok": False, "status": code, "body": payload}, ensure_ascii=False))
            return 1
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < policy.max_retries:
                sleep_s = policy.base_sleep * (2 ** attempt) + random.uniform(0, policy.jitter)
                time.sleep(sleep_s)
                continue
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
