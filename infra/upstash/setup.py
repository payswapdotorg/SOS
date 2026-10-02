#!/usr/bin/env python3
"""Upstash Redis provisioning/verification script — SOS Public Deployment (PUB-03).

Operator-executed (directive §3 Upstash lane, §13 rate limits, §20
environments). Idempotent and console-first: creation is OPTIONAL
(``--create``); the default mode VERIFIES existing infrastructure.

Reads (operator shell — NEVER from Git, NEVER written anywhere):

  SOS_REDIS_URL                rediss://…:6379 (the app contract name) — verify target
  UPSTASH_REDIS_REST_URL       optional — REST verification target instead
  UPSTASH_REDIS_REST_TOKEN     optional — REST auth (pair with the REST URL)
  UPSTASH_OWNER_EMAIL          optional — only for --create
  UPSTASH_OWNER_API_KEY        optional — only for --create

What it does:
  * default: PINGs the instance (native RESP over TLS via SOS_REDIS_URL, or
    the Upstash REST API when the REST pair is given) and prints the
    SOS_REDIS_URL wiring for the Render dashboard;
  * --create: finds (or creates) a free-tier database named ``sos-coordination``
    through the Upstash v2 management API. The response does NOT include the
    database password/REST token — those are fetched from the console; the
    script says so honestly instead of guessing.

Honesty notes:
  * Redis is the EPHEMERAL coordination plane only (rate limits, idempotency
    keys, locks, short-lived job state) — never the primary event store
    (directive §3; jobs are durable in Neon/SQLite). PUB-06 owns the
    coordination adapter semantics (``providers/upstash``); this script owns
    infrastructure only.
  * Live verification needs operator credentials; ``--dry-run`` and
    ``--selftest`` run fully offline (what CI/sandbox verification exercises).

Usage:
  python3 infra/upstash/setup.py --dry-run            # offline plan
  python3 infra/upstash/setup.py                      # verify (needs SOS_REDIS_URL or REST pair)
  python3 infra/upstash/setup.py --create             # create-if-missing (needs owner creds)
  python3 infra/upstash/setup.py --selftest           # offline known-answer tests
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_DATABASE_NAME = "sos-coordination"
MANAGEMENT_API_BASE = "https://api.upstash.com"
TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Offline self-tests (no network, no secrets)
# ---------------------------------------------------------------------------

def _selftest() -> int:
    failures = []

    # RESP PING request framing
    if build_ping_command() != b"PING\r\n":
        failures.append("build_ping_command framing wrong")

    # RESP simple-string reply parsing
    if parse_reply(b"+PONG\r\n") != "PONG":
        failures.append("parse_reply(+PONG) wrong")
    if parse_reply(b"-ERR bad\r\n") != "ERR bad":
        failures.append("parse_reply(-ERR) wrong")

    # rediss:// URL parsing
    parsed = parse_redis_url("rediss://user:pass@cache-abc.upstash.io:6379")
    if parsed != ("cache-abc.upstash.io", 6379, True):
        failures.append(f"parse_redis_url rediss wrong: {parsed!r}")
    parsed = parse_redis_url("redis://localhost:6379")
    if parsed != ("localhost", 6379, False):
        failures.append(f"parse_redis_url redis wrong: {parsed!r}")

    # the app contract requires TLS for Upstash (rediss://)
    try:
        parse_redis_url("https://not-a-redis-url.example.com")
        failures.append("parse_redis_url accepted a non-redis scheme")
    except SystemExit:
        pass

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("selftest: OK (RESP framing, reply parsing, URL policy)")
    return 0


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def build_ping_command() -> bytes:
    """RESP inline PING command (the simplest valid framing)."""
    return b"PING\r\n"


def parse_reply(data: bytes) -> str:
    """Parse a RESP simple-string (+) or error (-) reply payload."""
    if not data:
        raise SystemExit("empty reply from Redis")
    kind, _, rest = data.partition(b"\r\n")
    text = kind[1:].decode(errors="replace")
    return text


def parse_redis_url(url: str) -> tuple[str, int, bool]:
    """Parse redis:// / rediss:// URLs → (host, port, tls)."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("redis", "rediss"):
        raise SystemExit(
            "SOS_REDIS_URL must be redis:// or rediss:// (Upstash is rediss:// — TLS) — "
            f"got scheme {parsed.scheme!r}"
        )
    if not parsed.hostname:
        raise SystemExit("SOS_REDIS_URL has no host")
    return parsed.hostname, parsed.port or 6379, parsed.scheme == "rediss"


def resp_ping(host: str, port: int, *, tls: bool) -> str:
    """Native RESP PING over a socket (stdlib only)."""
    raw = socket.create_connection((host, port), timeout=TIMEOUT_SECONDS)
    try:
        sock = raw
        if tls:
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(raw, server_hostname=host)
        sock.sendall(build_ping_command())
        reply = b""
        while b"\r\n" not in reply:
            chunk = sock.recv(64)
            if not chunk:
                break
            reply += chunk
        return parse_reply(reply)
    finally:
        raw.close()


def rest_ping(rest_url: str, rest_token: str) -> str:
    """PING through the Upstash REST API (JSON pipeline form)."""
    req = urllib.request.Request(
        rest_url.rstrip("/"),
        data=json.dumps([["PING"]]).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {rest_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Upstash REST error {exc.code}: {exc.read().decode(errors='replace')[:300]}") from exc
    result = payload[0].get("result") if isinstance(payload, list) and payload else payload.get("result")
    if result != "PONG":
        raise SystemExit(f"unexpected REST PING reply: {payload!r}")
    return "PONG"


# ---------------------------------------------------------------------------
# Optional creation path (management API, basic auth)
# ---------------------------------------------------------------------------

def management_request(path: str, owner_email: str, owner_key: str, *,
                       method: str = "GET", body: dict | None = None) -> object:
    token = base64.b64encode(f"{owner_email}:{owner_key}".encode()).decode()
    req = urllib.request.Request(
        f"{MANAGEMENT_API_BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Basic {token}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Upstash management API error {exc.code} on {method} {path}: "
                         f"{exc.read().decode(errors='replace')[:300]}") from exc


def ensure_database(owner_email: str, owner_key: str, name: str, *, dry_run: bool) -> dict:
    listing = management_request("/v2/redis", owner_email, owner_key)
    if isinstance(listing, list):
        for db in listing:
            if db.get("database_name") == name or db.get("name") == name:
                print(f"[ok] database exists: {name} ({db.get('database_id') or db.get('id')})")
                return db
    if dry_run:
        print(f"[dry-run] would POST /v2/redis to create database: {name}")
        return {}
    print(f"[create] database: {name}")
    return management_request("/v2/redis", owner_email, owner_key, method="POST", body={
        "name": name,
        "region": "global",
        "primary_region": "us-east-1",
        "tls": True,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotent Upstash setup for the SOS public deployment (PUB-03).")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan only; print what would run, touch nothing (offline)")
    parser.add_argument("--create", action="store_true",
                        help="also create the database if missing (needs UPSTASH_OWNER_EMAIL + UPSTASH_OWNER_API_KEY)")
    parser.add_argument("--selftest", action="store_true",
                        help="run offline known-answer tests and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    redis_url = os.environ.get("SOS_REDIS_URL", "").strip()
    rest_url = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip()
    rest_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
    owner_email = os.environ.get("UPSTASH_OWNER_EMAIL", "").strip()
    owner_key = os.environ.get("UPSTASH_OWNER_API_KEY", "").strip()

    if args.create:
        if not (owner_email and owner_key):
            if args.dry_run:
                print("[dry-run] --create planned but owner credentials not set — nothing to do")
            else:
                raise SystemExit("--create needs UPSTASH_OWNER_EMAIL and UPSTASH_OWNER_API_KEY")
        else:
            db = ensure_database(owner_email, owner_key, DEFAULT_DATABASE_NAME, dry_run=args.dry_run)
            if db and not args.dry_run:
                endpoint = db.get("endpoint") or ""
                port = db.get("port") or 6379
                print("\n--- Created/verified database (console-first for credentials) ---")
                print(f"endpoint: {endpoint}:{port}")
                print("The management API response does NOT include the database password")
                print("or REST token — fetch both from console.upstash.com (database page),")
                print("then build: SOS_REDIS_URL=rediss://default:<password>@{}:{}".format(endpoint, port))
                print("(Upstash free tier: 256 MB, 500K commands/month, 10 GB/month bandwidth;")
                print(" Redis is the EPHEMERAL coordination plane only — never the event store.)")
                return 0

    if args.dry_run:
        print("[dry-run] verification plan:")
        if redis_url:
            host, port, tls = parse_redis_url(redis_url)
            print(f"  RESP PING over {'TLS' if tls else 'plain socket'} → {host}:{port}")
        elif rest_url and rest_token:
            print(f"  REST PING → {rest_url}")
        else:
            print("  nothing to verify (no SOS_REDIS_URL / REST pair set)")
        print("[dry-run] No network calls were made.")
        return 0

    if redis_url:
        host, port, tls = parse_redis_url(redis_url)
        reply = resp_ping(host, port, tls=tls)
        if reply != "PONG":
            raise SystemExit(f"unexpected PING reply: {reply!r}")
        print(f"[ok] RESP PING → PONG ({host}:{port}, {'TLS' if tls else 'plain'})")
        print("\n--- Operator wiring (already correct — copy into the Render dashboard) ---")
        print(f"SOS_REDIS_URL = {redis_url}")
    elif rest_url and rest_token:
        rest_ping(rest_url, rest_token)
        print(f"[ok] REST PING → PONG ({rest_url})")
        print("\n[note] Set SOS_REDIS_URL (rediss:// form) on Render for the app;")
        print("       the REST pair is only the verification/Upstash-side credential.")
    else:
        raise SystemExit(
            "nothing to verify: set SOS_REDIS_URL (rediss://…, the app contract name) "
            "or UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN"
        )

    print("\nNotes:")
    print("  * Upstash is the ephemeral coordination plane (rate limits, idempotency,")
    print("    locks, short-lived job state) — never the primary event store;")
    print("    jobs stay durable in Neon (directive §3; PUB-06 owns the adapter).")
    print("  * Free tier: 256 MB / 500K commands/month / 10 GB bandwidth — the §13")
    print("    limiter design keeps command volume bounded; watch usage at Stage C.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
