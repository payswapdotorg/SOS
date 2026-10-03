"""Upstash Redis cloud adapter (PUB-06) — the coordination seam over Upstash.

Implements the same semantics as the LOCAL in-process adapter
(:class:`providers.upstash.local.InProcessCoordination`):

- locks: ``SET key holder EX ttl NX`` (mutual exclusion across processes;
  TTL bounds the lease so a crashed holder cannot deadlock the plane);
- idempotency keys: ``SET key value EX ttl NX`` (first write wins, TTL
  bounded — the DURABLE idempotency truth is the ``jobs`` unique index in
  the persistence seam; this is the duplicate-suppression fast path);
- rate limiting: epoch-aligned fixed windows (``INCR`` + ``EXPIRE`` on a
  window-scoped key) — decision fields identical to the LOCAL limiter;
- ephemeral job state + pending-job registry: TTL-bounded keys/lists
  (directive §3 — Redis is NEVER the primary event store; durable job
  truth lives in Neon/SQLite).

Transport: the Upstash REST API over HTTPS using ONLY the standard library
(``urllib.request``) — no new runtime dependency is required (the frozen
pyproject ``[api]`` group stays untouched; the PUB-05 precedent keeps
optional drivers out of the hermetic default suite). ``rediss://`` URLs are
mapped to the REST endpoint of the same Upstash instance (the Upstash REST
token is the Redis password); ``https://`` REST URLs (optionally with an
embedded ``:token@`` authority) are accepted verbatim. Invalid or missing
URLs abort boot FAIL-CLOSED with a precise message (never a silent fallback
to the LOCAL adapter).

The transport callable is injectable for deterministic tests (the PUB-06
adapter suite runs the command semantics against a scripted fake transport —
no network, no credentials).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .seam import LockHandle, RateDecision, SeamHealth

# Key prefixes (single namespace per deployment; one SOS instance per
# Upstash database is the assumed topology).
_LOCK_PREFIX = "sos:lock:"
_IDEM_PREFIX = "sos:idem:"
_RATE_PREFIX = "sos:rl:"
_JOB_STATE_PREFIX = "sos:jobstate:"
_PENDING_KEY = "sos:pending"

# Idempotency keys are remembered for one week (duplicate-suppression
# fast path; the durable truth is the persistence unique index).
IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600

_HTTP_TIMEOUT_SECONDS = 5.0

TransportFn = Callable[[str, dict[str, str], bytes, float], bytes]


class UpstashConfigError(Exception):
    """Raised when the Upstash Redis URL is missing or unparsable."""


class UpstashUnavailableError(Exception):
    """Raised when the Upstash REST endpoint cannot be reached / errors."""


def _parse_redis_url(redis_url: str) -> tuple[str, str]:
    """Validate + translate ``SOS_REDIS_URL`` into (rest_base_url, token).

    Accepted forms (both name the SAME Upstash instance — the REST token is
    the Redis password):

    - ``rediss://[user]:password@host[:port]``  → ``https://host`` + password
    - ``https://[:token@]host[:port][/path]``   → ``https://host`` + token

    Anything else (including missing values) fails CLOSED with a message that
    names the PUB-06 adapter and the accepted forms.
    """
    raw = (redis_url or "").strip()
    lowered = raw.lower()
    try:
        if lowered.startswith("rediss://") or lowered.startswith("redis://"):
            rest = raw.split("://", 1)[1]
            authority = rest.split("/", 1)[0].split("@", 1)
            if len(authority) != 2:
                raise ValueError("missing credentials")
            userinfo, hostport = authority
            password = userinfo.split(":", 1)[1] if ":" in userinfo else ""
            host = hostport.split(":", 1)[0]
            if not host:
                raise ValueError("missing host")
            if not password:
                raise ValueError("missing password")
            return f"https://{host}", password
        if lowered.startswith("https://"):
            rest = raw[len("https://"):]
            authority = rest.split("/", 1)[0]
            if "@" in authority:
                userinfo, hostport = authority.rsplit("@", 1)
                token = (
                    userinfo.split(":", 1)[1]
                    if ":" in userinfo else userinfo
                )
            else:
                userinfo, hostport = "", authority
                token = ""
            host = hostport.split(":", 1)[0]
            if not host:
                raise ValueError("missing host")
            if not token:
                raise ValueError(
                    "REST URL without an embedded token"
                )
            return f"https://{host}", token
    except ValueError as exc:
        raise UpstashConfigError(
            f"SOS_REDIS_URL is invalid for the PUB-06 Upstash Redis adapter "
            f"({exc}). Accepted forms: rediss://default:<password>@<host>:6379 "
            "(the Upstash Redis URL — the REST token is the same password) or "
            "https://[:<token>@]<host> (the Upstash REST URL). fail-closed: "
            "no silent fallback to the LOCAL in-process adapter is permitted."
        ) from exc
    raise UpstashConfigError(
        "SOS_REDIS_URL is required for SOS_COORDINATION=upstash and must be "
        "either rediss://default:<password>@<host>:6379 (the Upstash Redis "
        "URL) or https://[:<token>@]<host> (the Upstash REST URL). The "
        "PUB-06 Upstash adapter refuses to boot without a valid URL "
        "(fail-closed: no silent fallback to the LOCAL adapter). Got: "
        f"{redis_url!r}"
    )


def _default_transport(
    url: str, headers: dict[str, str], body: bytes, timeout: float
) -> bytes:
    """POST ``body`` (a JSON command array) to the Upstash REST endpoint.

    Standard library only. Network/HTTP failures raise
    :class:`UpstashUnavailableError` so callers fail CLOSED (the middleware
    already maps coordination failures to 503 PROVIDER_UNAVAILABLE; the
    health probe reports the seam's true state).
    """
    request = urllib.request.Request(
        url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.reason or "http error"
        raise UpstashUnavailableError(
            f"upstash rest responded {exc.code} ({detail})"
        ) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpstashUnavailableError(
            f"upstash rest unreachable: {exc}"
        ) from exc


def _ttl_int(ttl_seconds: float) -> int:
    return max(1, int(ttl_seconds + 0.999))


class UpstashRestEngine:
    """A tiny Upstash REST command engine (commands as JSON arrays).

    A custom ``transport`` callable (url, headers, body, timeout) -> bytes
    makes the engine deterministic in tests without any network.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        transport: TransportFn | None = None,
        timeout: float = _HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._transport: TransportFn = (
            transport or _default_transport
        )
        self._timeout = timeout

    def execute(self, command: list[str]) -> Any:
        """Run ONE command (e.g. ``["SET","k","v","EX","60","NX"]``).

        Posted as a flat JSON array — the Upstash REST convention for a
        single command (arrays-of-arrays are pipelines)."""
        return self._post(json.dumps(command))

    def pipeline(self, commands: list[list[str]]) -> list[Any]:
        """Run commands atomically-in-order (Upstash REST pipeline)."""
        return self._post(json.dumps([list(c) for c in commands]))

    def _post(self, payload: str) -> Any:
        body = payload.encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        try:
            raw = self._transport(
                self._base_url, headers, body, self._timeout
            )
        except UpstashUnavailableError:
            raise
        except Exception as exc:
            # Transport contracts: return bytes or raise. Any failure maps
            # to UpstashUnavailableError so callers fail CLOSED uniformly.
            raise UpstashUnavailableError(
                f"upstash rest transport failed: {exc}"
            ) from exc
        text = raw.decode("utf-8")
        try:
            return json.loads(text)
        except ValueError as exc:
            raise UpstashUnavailableError(
                f"upstash rest returned a non-JSON body: {text[:120]!r}"
            ) from exc


class _RedisLockHandle:
    """A lock acquired via ``SET ... NX EX``; released with ``DEL``.

    Release is best-effort compare-then-delete: the orchestration lock is
    NOT the authoritative single-execution guard (the durable job status
    transition is); a release race after TTL expiry can at worst delete a
    re-acquired lock, costing efficiency — never correctness.
    """

    def __init__(
        self, engine: UpstashRestEngine, key: str, holder: str,
        acquired: bool,
    ):
        self._engine = engine
        self.key = key
        self._holder = holder
        self.acquired = acquired

    def release(self) -> None:
        if not self.acquired:
            return
        self.acquired = False
        try:
            current = self._engine.execute(["GET", self.key])
            if current == self._holder:
                self._engine.execute(["DEL", self.key])
        except UpstashUnavailableError:
            # The lease expires on its own (EX TTL); losing the release
            # round-trip delays re-acquisition at most until TTL elapses.
            pass

    def __enter__(self) -> "_RedisLockHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class UpstashRedisCoordination:
    """The Upstash Redis implementation of the coordination seam.

    Selected by ``SOS_COORDINATION=upstash`` (``SOS_REDIS_URL`` required,
    fail-closed). Semantics are identical to
    :class:`providers.upstash.local.InProcessCoordination` — the PUB-06
    parity suite runs the same decision assertions against both.
    """

    mode = "upstash"
    implementation = "upstash-redis-rest"

    def __init__(self, engine: UpstashRestEngine) -> None:
        self._engine = engine

    # -- construction -------------------------------------------------------

    @classmethod
    def from_url(
        cls, redis_url: str, *, transport: TransportFn | None = None
    ) -> "UpstashRedisCoordination":
        base_url, token = _parse_redis_url(redis_url)
        return cls(UpstashRestEngine(base_url, token, transport=transport))

    # -- health ---------------------------------------------------------------

    def health_check(self) -> SeamHealth:
        try:
            pong = self._engine.execute(["PING"])
        except UpstashUnavailableError as exc:
            return SeamHealth(
                status="UNAVAILABLE",
                detail=f"upstash redis unreachable: {exc}",
            )
        if str(pong).upper() == "PONG":
            return SeamHealth(
                status="SUCCESS", detail="upstash redis ok (rest ping)"
            )
        return SeamHealth(
            status="UNAVAILABLE",
            detail=f"upstash redis ping returned {pong!r} (expected PONG)",
        )

    # -- locks ----------------------------------------------------------------

    def acquire_lock(self, key: str, *, ttl_seconds: float) -> LockHandle:
        full_key = _LOCK_PREFIX + key
        holder = f"holder-{time.time_ns()}"
        result = self._engine.execute(
            ["SET", full_key, holder, "EX", str(_ttl_int(ttl_seconds)), "NX"]
        )
        acquired = result == "OK"
        return _RedisLockHandle(self._engine, full_key, holder, acquired)

    # -- idempotency keys -------------------------------------------------------

    def idempotency_remember(self, key: str, value: str) -> bool:
        result = self._engine.execute(
            [
                "SET", _IDEM_PREFIX + key, value,
                "EX", str(IDEMPOTENCY_TTL_SECONDS), "NX",
            ]
        )
        return result == "OK"

    def idempotency_lookup(self, key: str) -> str | None:
        return self._engine.execute(["GET", _IDEM_PREFIX + key])

    # -- rate limiting (epoch-aligned fixed windows) ------------------------------

    def rate_limit(
        self, bucket: str, key: str, *, limit: int, window_seconds: int
    ) -> RateDecision:
        now = time.time()
        window_seconds = max(1, int(window_seconds))
        window_id = int(now // window_seconds)
        window_key = (
            f"{_RATE_PREFIX}{bucket}:{key}:{window_id}"
        )
        count, _ = self._engine.pipeline(
            [
                ["INCR", window_key],
                ["EXPIRE", window_key, str(window_seconds + 30)],
            ]
        )
        count = int(count or 0)
        allowed = count <= limit
        window_end = (window_id + 1) * window_seconds
        retry_after = 0
        if not allowed:
            retry_after = max(1, int(window_end - now) + 1)
        return RateDecision(
            allowed=allowed,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after,
        )

    # -- ephemeral job state -------------------------------------------------------

    def job_state_get(self, job_id: str) -> str | None:
        return self._engine.execute(["GET", _JOB_STATE_PREFIX + job_id])

    def job_state_set(self, job_id: str, value: str,
                      *, ttl_seconds: float) -> bool:
        result = self._engine.execute(
            [
                "SET", _JOB_STATE_PREFIX + job_id, value,
                "EX", str(_ttl_int(ttl_seconds)), "NX",
            ]
        )
        return result == "OK"

    def job_state_put(self, job_id: str, value: str,
                      *, ttl_seconds: float) -> None:
        self._engine.execute(
            [
                "SET", _JOB_STATE_PREFIX + job_id, value,
                "EX", str(_ttl_int(ttl_seconds)),
            ]
        )

    # -- pending-job registry ---------------------------------------------------------

    def pending_job_add(self, tenant_id: str, job_id: str,
                        *, ttl_seconds: float) -> None:
        entry = f"{tenant_id}::{job_id}"
        self._engine.pipeline(
            [
                ["RPUSH", _PENDING_KEY, entry],
                ["EXPIRE", _PENDING_KEY, str(_ttl_int(ttl_seconds) + 3600)],
            ]
        )

    def pending_job_remove(self, tenant_id: str, job_id: str) -> None:
        try:
            self._engine.execute(
                ["LREM", _PENDING_KEY, "1", f"{tenant_id}::{job_id}"]
            )
        except UpstashUnavailableError:
            # Registry entries are advisory (TTL-bounded); the durable job
            # status is the truth. A lost removal costs one re-scan.
            pass

    def pending_jobs(self) -> list[tuple[str, str]]:
        entries = self._engine.execute(
            ["LRANGE", _PENDING_KEY, "0", "-1"]
        )
        pairs: list[tuple[str, str]] = []
        for entry in entries or []:
            parts = str(entry).split("::", 1)
            if len(parts) == 2:
                pairs.append((parts[0], parts[1]))
        return pairs


def build_upstash_coordination(
    redis_url: str, *, transport: TransportFn | None = None
) -> UpstashRedisCoordination:
    """Build the Upstash coordination adapter from ``SOS_REDIS_URL``.

    Construction performs NO network I/O (URL validation only) so app boot
    never depends on the coordination plane being up; the first actual
    command (health probe / first request) reports the true state.
    """
    return UpstashRedisCoordination.from_url(redis_url, transport=transport)
