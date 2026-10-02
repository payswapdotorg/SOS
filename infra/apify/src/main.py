"""SOS bounded execution actor — STUB ENTRY (PUB-03 skeleton).

This is deliberately a SKELETON, not the implementation. PUB-03 delivers
package metadata (``.actor/actor.json``), the bounded input schema
(``.actor/input_schema.json``) and this stub entry ONLY. The execution
semantics — fetching the exact source revision, running the allowed
operation under the declared resource limits, uploading artifacts per
policy, and emitting the signed callback — land with PUB-08
(contract §D PUB-08), together with the actor's Dockerfile (contract §A.7:
the Dockerfile must NOT land in this item).

What the stub honestly does:
  * parses the input (Apify ``Actor.getInput()`` when running on the Apify
    platform; stdin JSON locally — no SDK required for the skeleton check);
  * validates the BOUNDED-INPUT invariants that are cheap and certain:
    required fields present, exact-revision shape (40-hex, S11), limits
    within the schema maxima (S14), callback envelope shape (S10);
  * emits a structured acknowledgment that is EXPLICITLY marked ``stub`` —
    it is not an execution receipt, and nothing downstream may treat it as
    one (no false SUCCESS: truth-state discipline, contract §A.6);
  * exits 0 only when the input is well-formed.

The provider-authorization boundary (security gate S12): this actor NEVER
decides authorization. The ``authorizedAction`` is what the SOS authority
layer already decided; the actor executes within it or refuses.
"""
from __future__ import annotations

import json
import sys

REQUIRED_TOP_LEVEL = ("jobId", "tenantId", "authorizedAction", "sourceRevision",
                      "allowedOperation", "limits", "callbackTarget")
REQUIRED_LIMITS = ("timeLimitSeconds", "maxMemoryMb", "maxOutputArtifactMb")
LIMIT_MAXIMA = {"timeLimitSeconds": 900, "maxMemoryMb": 2048, "maxOutputArtifactMb": 50}
ALLOWED_OPERATIONS = ("repository_analysis", "bounded_source_extraction",
                      "website_ingestion", "document_ingestion")


class InvalidInput(Exception):
    """Raised when the bounded input violates the schema (fail-closed)."""


def validate_input(raw: object) -> dict:
    """Validate the bounded input invariants (subset checks, fail-closed).

    The full JSON schema lives in ``.actor/input_schema.json``; these are
    the invariants the stub can check with certainty and zero dependencies.
    PUB-08 replaces this with the real validation + execution pipeline.
    """
    if not isinstance(raw, dict):
        raise InvalidInput("input must be a JSON object")
    missing = [k for k in REQUIRED_TOP_LEVEL if k not in raw]
    if missing:
        raise InvalidInput(f"missing required fields: {', '.join(missing)}")

    for key in ("jobId", "tenantId", "authorizedAction"):
        if not isinstance(raw[key], str) or not 1 <= len(raw[key]) <= (64 if key != "authorizedAction" else 128):
            raise InvalidInput(f"{key} must be a non-empty bounded string")

    source = raw["sourceRevision"]
    if not isinstance(source, dict):
        raise InvalidInput("sourceRevision must be an object")
    revision = source.get("revision", "")
    if not isinstance(revision, str) or len(revision) != 40 or not all(c in "0123456789abcdef" for c in revision):
        raise InvalidInput("sourceRevision.revision must be an exact 40-hex commit SHA (S11: no mutable refs)")

    if raw["allowedOperation"] not in ALLOWED_OPERATIONS:
        raise InvalidInput(f"allowedOperation must be one of: {', '.join(ALLOWED_OPERATIONS)}")

    limits = raw["limits"]
    if not isinstance(limits, dict):
        raise InvalidInput("limits must be an object")
    for key in REQUIRED_LIMITS:
        value = limits.get(key)
        if not isinstance(value, int) or not 1 <= value <= LIMIT_MAXIMA[key]:
            raise InvalidInput(f"limits.{key} must be an integer in [1, {LIMIT_MAXIMA[key]}] (S14)")

    callback = raw["callbackTarget"]
    if not isinstance(callback, dict) or not all(k in callback for k in ("url", "nonce", "timestamp", "signature")):
        raise InvalidInput("callbackTarget must carry url/nonce/timestamp/signature (S10)")

    return raw


def read_input() -> object:
    """Read the actor input: Apify platform input when available, else stdin."""
    try:  # Apify runtime (PUB-08 will run here for real)
        from apify import Actor  # type: ignore[import-not-found]

        async def _get() -> object:
            async with Actor:
                return await Actor.get_input()

        import asyncio

        return asyncio.run(_get())
    except ImportError:
        # Local skeleton check: stdin JSON (see README example).
        data = sys.stdin.read().strip()
        if not data:
            raise InvalidInput("no input provided (expected JSON on stdin locally, or the Apify platform input)")
        return json.loads(data)


def main() -> int:
    try:
        parsed = validate_input(read_input())
    except InvalidInput as exc:
        # Fail-closed: an invalid bounded input aborts BEFORE any work.
        print(json.dumps({
            "status": "stub",
            "accepted": False,
            "error": f"invalid bounded input: {exc}",
        }))
        return 1
    print(json.dumps({
        "status": "stub",
        "accepted": True,
        "jobId": parsed["jobId"],
        "allowedOperation": parsed["allowedOperation"],
        "sourceRevision": parsed["sourceRevision"]["revision"],
        "limits": {k: parsed["limits"][k] for k in REQUIRED_LIMITS},
        "note": (
            "PUB-03 skeleton acknowledgment — NOT an execution receipt. The real "
            "bounded execution, artifact policy and signed callback land with "
            "PUB-08 (contract §D PUB-08); the Dockerfile lands with it (§A.7). "
            "No work was executed."
        ),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
