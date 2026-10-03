"""Replay-protected signed-callback validation (PUB-06 primitive; directive
§16-A "callback validation"; SECURITY callback rules).

The provider-facing callback ENDPOINT is PUB-08's surface (contract §D
PUB-08: "signed callback endpoint on the API"); this module is the
job-layer validation primitive that endpoint will call. Binding rules
(implemented here, verbatim from the contract §C.3 / §SECURITY):

- bodies are HMAC-signed envelopes (``X-SOS-Signature``-style hex digest);
- replay-protected: a nonce may be used exactly once (coordination-plane
  single-use store) within the timestamp window;
- the timestamp window is enforced BEFORE any signature comparison leaks
  timing or state, and every check happens BEFORE any state mutation —
  a rejected callback mutates nothing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

# The accepted clock-skew window for callback timestamps (seconds).
DEFAULT_CALLBACK_WINDOW_SECONDS = 300


class CallbackRejected(Exception):
    """A callback envelope failed validation — NOTHING was mutated."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def sign_callback_envelope(
    *, secret: str, timestamp: str, nonce: str, body: str
) -> str:
    """The canonical HMAC-SHA256 hex signature over ``timestamp.nonce.body``.

    Signing helper (used by tests and by the DemoProvider handoff); the
    API never signs — providers do.
    """
    material = f"{timestamp}.{nonce}.{body}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"), material, hashlib.sha256
    ).hexdigest()


def verify_signed_callback(
    *,
    secret: str | None,
    timestamp: str,
    nonce: str,
    signature: str,
    body: str,
    coordination: Any,
    window_seconds: int = DEFAULT_CALLBACK_WINDOW_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Validate one signed callback envelope; return the parsed JSON body.

    Order of checks (fail-closed, no state mutation on any failure):

    1. a callback secret MUST be configured (fail-closed: unsigned
       acceptance is forbidden — PUB-08 §Forbidden);
    2. the timestamp must be within ``window_seconds`` of now (replay
       window);
    3. the HMAC-SHA256 hex signature over ``timestamp.nonce.body`` must
       match (constant-time compare);
    4. the nonce must be single-use (coordination-plane
       ``idempotency_remember`` — TTL covers the window twice over).

    Raises :class:`CallbackRejected` on any failure.
    """
    if not secret:
        raise CallbackRejected(
            "callback verification is not configured (SOS_JOB_CALLBACK_"
            "SECRET missing) — fail-closed: unsigned callbacks are never "
            "accepted"
        )
    now = time.time() if now is None else now
    try:
        ts_value = float(timestamp)
    except (TypeError, ValueError) as exc:
        raise CallbackRejected(f"invalid timestamp {timestamp!r}") from exc
    if abs(now - ts_value) > window_seconds:
        raise CallbackRejected(
            f"callback timestamp outside the ±{window_seconds}s window"
        )
    expected = sign_callback_envelope(
        secret=secret, timestamp=timestamp, nonce=nonce, body=body
    )
    if not hmac.compare_digest(expected, (signature or "").lower()):
        raise CallbackRejected("callback signature mismatch")
    if not nonce:
        raise CallbackRejected("callback nonce is required")
    remembered = coordination.idempotency_remember(
        f"callback-nonce:{nonce}", str(int(ts_value))
    )
    if not remembered:
        raise CallbackRejected(
            "callback nonce already used (replay protection)"
        )
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise CallbackRejected("callback body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise CallbackRejected("callback body must be a JSON object")
    return payload
