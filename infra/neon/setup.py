#!/usr/bin/env python3
"""Neon provisioning/verification script — SOS Public Deployment (PUB-03).

Operator-executed (directive §3 Neon lane, §20 environments). Idempotent:
every operation is check-then-act by NAME, so re-running is always safe.

Reads (from the operator's shell — NEVER from Git, NEVER written anywhere):

  NEON_API_KEY            required — console.neon.tech → Account → API keys
  SOS_NEON_PROJECT        optional — project name (default: sos-public)
  SOS_NEON_BRANCH         optional — branch to provision/verify (default: main)
  SOS_NEON_API_BASE       optional — Neon API base (default: https://api.neon.tech/v2)

What it does (all idempotent):
  1. finds (or creates) the Neon project by name;
  2. finds (or creates) the requested branch (+ database/role on non-default
     branches), for the PUBLIC database or a PREVIEW branch;
  3. fetches the branch connection URI and prints the exact wiring to set on
     Render (``SOS_DATABASE_URL``).

Honesty notes:
  * This script prints the connection URI to the operator's terminal ONCE —
    that is its purpose (operator copies it into the Render dashboard).
    It never writes credentials to any file.
  * It provisions infrastructure ONLY. Schema migrations are owned by the
    application boot path (``services/api`` applies ``db/migrations`` at
    startup) and the adapter semantics are owned by PUB-05
    (``providers/neon``). This script contains no application logic.
  * Live execution requires operator credentials; ``--dry-run`` (the
    default when no API key is present) and ``--check-plan`` run fully
    offline and are what CI/sandbox verification exercises.

Usage:
  python3 infra/neon/setup.py --dry-run          # offline: show planned calls
  python3 infra/neon/setup.py                    # provision/verify (needs NEON_API_KEY)
  python3 infra/neon/setup.py --verify-only      # no creation, verify + print wiring
  python3 infra/neon/setup.py --selftest        # offline known-answer tests
"""
from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_BASE = "https://api.neon.tech/v2"
DEFAULT_PROJECT = "sos-public"
DEFAULT_BRANCH = "main"
DEFAULT_DATABASE = "neondb"
DEFAULT_ROLE = "neondb"
TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Offline self-tests (honest verification without credentials)
# ---------------------------------------------------------------------------

def _selftest() -> int:
    """Known-answer tests for the pure helpers (no network, no secrets)."""
    failures = []

    # connection-string scheme adaptation: Neon returns postgresql://…, the
    # app contract (infra/environment.example) expects postgresql+asyncpg://…
    raw = "postgresql://user:pass@ep-example-123.us-east-2.aws.neon.tech/neondb?sslmode=require"
    want = "postgresql+asyncpg://user:pass@ep-example-123.us-east-2.aws.neon.tech/neondb?sslmode=require"
    got = to_asyncpg_scheme(raw)
    if got != want:
        failures.append(f"to_asyncpg_scheme: {got!r} != {want!r}")

    # already-asyncpg string passes through unchanged
    if to_asyncpg_scheme(want) != want:
        failures.append("to_asyncpg_scheme: passthrough failed")

    # branch naming policy (Neon: lower-case letters, digits, hyphens — the
    # preview convention is preview-pr-<N>; slashes are rejected)
    for name, ok in (("main", True), ("preview-pr-31", True), ("preview/pr-31", False),
                     ("bad name", False), ("", False), ("-leading", False), ("Upper", False)):
        if valid_branch_name(name) != ok:
            failures.append(f"valid_branch_name({name!r}) != {ok}")

    if failures:
        print("SELFTEST FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("selftest: OK (scheme adaptation, branch-name policy)")
    return 0


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def to_asyncpg_scheme(uri: str) -> str:
    """Adapt a Neon ``postgresql://`` URI to the app contract scheme.

    ``infra/environment.example`` documents ``SOS_DATABASE_URL`` as
    ``postgresql+asyncpg://…`` (the PUB-05 adapter's driver). The Neon API
    returns ``postgresql://``; this converts the scheme prefix and leaves
    everything else byte-identical. A URI already carrying the driver
    scheme passes through unchanged.
    """
    if uri.startswith("postgresql+asyncpg://"):
        return uri
    if uri.startswith("postgresql://"):
        return "postgresql+asyncpg://" + uri[len("postgresql://"):]
    raise ValueError(f"not a postgresql URI: {uri[:32]}…")


def valid_branch_name(name: str) -> bool:
    """Neon branch naming policy: [a-z0-9-], no leading dash, 1-63 chars.

    Slashes are deliberately rejected (conservative superset of Neon's
    documented name rules); the preview convention is ``preview-pr-<N>``.
    """
    if not name or len(name) > 63:
        return False
    if name.startswith("-"):
        return False
    return all(c.isalnum() or c == "-" for c in name) and name == name.lower()


# ---------------------------------------------------------------------------
# Minimal HTTPS JSON client (stdlib only)
# ---------------------------------------------------------------------------

class NeonApi:
    def __init__(self, api_key: str, base: str, *, dry_run: bool):
        self._key = api_key
        self._base = base.rstrip("/")
        self.dry_run = dry_run

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        if self.dry_run:
            # Dry-run responses: never parsed beyond plan printing.
            return {"_dry_run": True}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._key}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise SystemExit(
                f"Neon API error {exc.code} on {method} {path}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"Neon API unreachable ({method} {path}): {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Provisioning steps (idempotent check-then-act)
# ---------------------------------------------------------------------------

def ensure_project(api: NeonApi, project_name: str, *, create: bool) -> dict:
    if api.dry_run:
        print(f"[dry-run] GET /projects → find by name (create via POST /projects if missing): {project_name}")
        return {"id": "<dry-run>", "name": project_name}
    found = [p for p in api._request("GET", "/projects").get("projects", [])
             if p.get("name") == project_name]
    if found:
        print(f"[ok] project exists: {project_name} ({found[0]['id']})")
        return found[0]
    if not create:
        raise SystemExit(f"project not found: {project_name} (run without --verify-only to create it)")
    print(f"[create] project: {project_name}")
    return api._request("POST", "/projects", {"project": {"name": project_name}}).get("project", {})


def ensure_branch(api: NeonApi, project: dict, branch_name: str, *, create: bool) -> dict:
    if api.dry_run:
        print(f"[dry-run] GET /projects/<id>/branches → find by name (create via POST /projects/<id>/branches if missing): {branch_name}")
        return {"id": "<dry-run>", "name": branch_name}
    pid = project["id"]
    branches = api._request("GET", f"/projects/{pid}/branches").get("branches", [])
    found = [b for b in branches if b.get("name") == branch_name]
    if found:
        print(f"[ok] branch exists: {branch_name} ({found[0]['id']})")
        return found[0]
    if not create:
        raise SystemExit(f"branch not found: {branch_name} (run without --verify-only to create it)")
    print(f"[create] branch: {branch_name}")
    branch = api._request("POST", f"/projects/{pid}/branches",
                          {"branch": {"name": branch_name}}).get("branch", {})
    # Non-default branches need an explicit database + role (the default
    # branch gets them at project creation).
    api._request("POST", f"/projects/{pid}/databases",
                 {"database": {"name": DEFAULT_DATABASE, "branch_id": branch["id"]}})
    api._request("POST", f"/projects/{pid}/roles",
                 {"role": {"name": DEFAULT_ROLE, "branch_id": branch["id"]}})
    return branch


def connection_uri(api: NeonApi, project: dict, branch: dict) -> str:
    pid = project["id"]
    query = urllib.parse.urlencode({
        "branch_id": branch["id"],
        "database_name": DEFAULT_DATABASE,
        "role_name": DEFAULT_ROLE,
    })
    payload = api._request("GET", f"/projects/{pid}/connection_uri?{query}")
    uri = payload.get("connection_uri") or payload.get("uri") or ""
    if not uri and not api.dry_run:
        raise SystemExit("Neon returned no connection URI — check branch/database/role names")
    return uri


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idempotent Neon setup for the SOS public deployment (PUB-03).")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan only: print the API calls that would run, touch nothing (offline)")
    parser.add_argument("--verify-only", action="store_true",
                        help="never create anything; verify existence and print wiring")
    parser.add_argument("--selftest", action="store_true",
                        help="run offline known-answer tests and exit")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    api_key = os.environ.get("NEON_API_KEY", "").strip()
    project_name = os.environ.get("SOS_NEON_PROJECT", "").strip() or DEFAULT_PROJECT
    branch_name = os.environ.get("SOS_NEON_BRANCH", "").strip() or DEFAULT_BRANCH
    api_base = os.environ.get("SOS_NEON_API_BASE", "").strip() or DEFAULT_API_BASE

    if not valid_branch_name(branch_name):
        raise SystemExit(f"invalid SOS_NEON_BRANCH {branch_name!r}: lowercase [a-z0-9-] only (no slashes — the preview convention is preview-pr-<N>), no leading dash, 1-63 chars")

    dry_run = args.dry_run or not api_key
    if dry_run and not args.dry_run and api_key == "":
        print("[note] NEON_API_KEY not set — running in --dry-run mode (offline plan only)\n")

    api = NeonApi(api_key or "dry-run", api_base, dry_run=dry_run)
    create = not args.verify_only and not dry_run

    project = ensure_project(api, project_name, create=create)
    branch = ensure_branch(api, project, branch_name, create=create)
    raw_uri = connection_uri(api, project, branch)

    if dry_run:
        print("\n[dry-run] Plan summary: find project → find/create branch → fetch")
        print("[dry-run] connection URI → print SOS_DATABASE_URL wiring. No network")
        print("[dry-run] calls were made, nothing was created, no credentials were read.")
        return 0

    print("\n--- Operator wiring (copy into the Render dashboard) ---")
    print(f"SOS_DATABASE_URL = {to_asyncpg_scheme(raw_uri)}")
    print("\nNotes:")
    print("  * Scheme adapted to postgresql+asyncpg:// per infra/environment.example")
    print("    (the PUB-05 providers/neon adapter's driver).")
    print("  * Schema migrations are applied by the application at boot (db/runner.py);")
    print("    this script owns NO application logic.")
    print("  * For a PREVIEW environment, re-run with SOS_NEON_BRANCH=preview-pr-<N>")
    print("    and point the preview stack at that branch's URI (see")
    print("    docs/deployment/preview-environments.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
