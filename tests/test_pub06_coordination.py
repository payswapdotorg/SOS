"""PUB-06 — the coordination seam: Upstash Redis adapter command semantics
(scripted fake transport — no network, no credentials), the LOCAL
in-process adapter, and the LOCAL↔PUBLIC PARITY of limiter/lock/idempotency
semantics (contract §D PUB-06 acceptance). Hermetic."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip(
    "fastapi",
    reason=(
        "PUB-06 API tests require the 'api' dependency group "
        "(pyproject [project.optional-dependencies].api); the frozen 'tests' "
        "CI workflow runs the dependency-free baseline suite only"
    ),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
for _entry in (str(REPO_ROOT / "src"), str(REPO_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from providers.upstash.cloud import (  # noqa: E402
    UpstashConfigError,
    UpstashRedisCoordination,
    UpstashRestEngine,
    UpstashUnavailableError,
    _parse_redis_url,
    build_upstash_coordination,
)
from providers.upstash.local import InProcessCoordination  # noqa: E402


# ---------------------------------------------------------------------------
# URL validation (fail-closed construction)
# ---------------------------------------------------------------------------

def test_redis_url_accepts_rediss_and_rest_forms() -> None:
    assert _parse_redis_url(
        "rediss://default:secret@us1-x.upstash.io:6379"
    ) == ("https://us1-x.upstash.io", "secret")
    assert _parse_redis_url(
        "rediss://:pw@cache.example.com:6379"
    ) == ("https://cache.example.com", "pw")
    assert _parse_redis_url(
        "https://:rest-token@us1-x.upstash.io"
    ) == ("https://us1-x.upstash.io", "rest-token")


@pytest.mark.parametrize(
    "url",
    [
        "",
        "None",
        "rediss://no-credentials.example.com:6379",
        "rediss://default:@host:6379",
        "https://no-token.example.com",
        "postgres://something-else",
    ],
)
def test_redis_url_invalid_fails_closed_with_pub06_message(url: str) -> None:
    with pytest.raises(UpstashConfigError) as excinfo:
        build_upstash_coordination(url)
    message = str(excinfo.value)
    assert "PUB-06" in message
    assert "fail-closed" in message


def test_upstash_construction_performs_no_network_io() -> None:
    # Building the adapter must not touch the network (app boot never
    # depends on the coordination plane being up; health reports truth).
    def _boom(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("construction must not call the transport")

    adapter = build_upstash_coordination(
        "rediss://default:pw@host.example.com:6379", transport=_boom
    )
    assert adapter.mode == "upstash"
    assert adapter.implementation == "upstash-redis-rest"


# ---------------------------------------------------------------------------
# A scripted fake transport (deterministic Upstash REST responses)
# ---------------------------------------------------------------------------

class FakeUpstash:
    """An in-memory Upstash REST endpoint: records every request verbatim
    and answers with real Redis-compatible semantics (SET NX, GET, DEL,
    INCR, EXPIRE, RPUSH, LRANGE, LREM, PING)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.requests: list[dict] = []
        self.fail = False

    def __call__(self, url, headers, body, timeout) -> bytes:
        import json as _json

        self.requests.append(
            {
                "url": url,
                "authorization": headers.get("Authorization"),
                "commands": _json.loads(body.decode("utf-8")),
                "timeout": timeout,
            }
        )
        if self.fail:
            raise OSError("connection refused (fault injection)")
        commands = self.requests[-1]["commands"]
        pipeline = all(isinstance(c, list) for c in commands)
        commands = commands if pipeline else [commands]
        results = [self._run_one(cmd) for cmd in commands]
        if pipeline:
            response = _json.dumps(results).encode("utf-8")
        else:
            response = _json.dumps(results[0]).encode("utf-8")
        return response

    def _run_one(self, cmd: list) -> object:
        name = cmd[0].upper()
        if name == "PING":
            return "PONG"
        if name == "SET":
            key, value = cmd[1], cmd[2]
            ttl, nx = None, False
            index = 3
            while index < len(cmd):
                flag = str(cmd[index]).upper()
                if flag == "EX":
                    ttl = int(cmd[index + 1])
                    index += 2
                elif flag == "NX":
                    nx = True
                    index += 1
                else:
                    index += 1
            if nx and key in self.store:
                return None
            self.store[key] = value
            if ttl is not None:
                self.ttls[key] = ttl
            return "OK"
        if name == "GET":
            return self.store.get(cmd[1])
        if name == "DEL":
            existed = cmd[1] in self.store
            self.store.pop(cmd[1], None)
            self.ttls.pop(cmd[1], None)
            return 1 if existed else 0
        if name == "INCR":
            key = cmd[1]
            value = int(self.store.get(key, "0")) + 1
            self.store[key] = str(value)
            return value
        if name == "EXPIRE":
            self.ttls[cmd[1]] = int(cmd[2])
            return 1
        if name == "RPUSH":
            key = cmd[1]
            entries = self.store.get(key, "")
            parts = [p for p in entries.split("|") if p] if entries else []
            parts.append(cmd[2])
            self.store[key] = "|".join(parts)
            return len(parts)
        if name == "LRANGE":
            entries = self.store.get(cmd[1], "")
            parts = [p for p in entries.split("|") if p] if entries else []
            start, stop = int(cmd[2]), int(cmd[3])
            return parts[start:] if stop == -1 else parts[start: stop + 1]
        if name == "LREM":
            key, count, value = cmd[1], int(cmd[2]), cmd[3]
            entries = self.store.get(key, "")
            parts = [p for p in entries.split("|") if p] if entries else []
            for _ in range(count if count > 0 else 1):
                if value in parts:
                    parts.remove(value)
                else:
                    break
            self.store[key] = "|".join(parts)
            return 1
        raise AssertionError(f"unexpected command {cmd!r}")


def _upstash(fake: FakeUpstash) -> UpstashRedisCoordination:
    return UpstashRedisCoordination(
        UpstashRestEngine(
            "https://cache.example.com", "test-token", transport=fake
        )
    )


# ---------------------------------------------------------------------------
# Command semantics over the fake transport
# ---------------------------------------------------------------------------

def test_upstash_lock_set_nx_ex_and_release() -> None:
    fake = FakeUpstash()
    coordination = _upstash(fake)
    lock = coordination.acquire_lock("job-1", ttl_seconds=120)
    assert lock.acquired is True
    set_request = fake.requests[0]
    assert set_request["url"] == "https://cache.example.com"
    assert set_request["authorization"] == "Bearer test-token"
    assert set_request["commands"][0] == "SET"
    assert set_request["commands"][1] == "sos:lock:job-1"
    assert set_request["commands"][3:6] == ["EX", "120", "NX"]
    # mutual exclusion: a second acquire on the same key loses
    loser = coordination.acquire_lock("job-1", ttl_seconds=60)
    assert loser.acquired is False
    with lock:
        pass  # context exit releases
    assert lock.acquired is False
    # release issued GET (holder check) + DEL
    assert fake.requests[-2]["commands"][0] == "GET"
    assert fake.requests[-1]["commands"][0] == "DEL"
    assert fake.requests[-1]["commands"][1] == "sos:lock:job-1"
    # and the lock is re-acquirable after release
    again = coordination.acquire_lock("job-1", ttl_seconds=30)
    assert again.acquired is True


def test_upstash_lock_release_skips_delete_when_lease_reassigned() -> None:
    fake = FakeUpstash()
    coordination = _upstash(fake)
    first = coordination.acquire_lock("k", ttl_seconds=60)
    # simulate lease expiry + re-acquire by another holder
    fake.store["sos:lock:k"] = "holder-other"
    first.release()
    # the compare-then-delete saw a foreign holder: no DEL was issued
    assert all(
        r["commands"][0][0] != "DEL" for r in fake.requests
    )


def test_upstash_idempotency_first_write_wins() -> None:
    fake = FakeUpstash()
    coordination = _upstash(fake)
    assert coordination.idempotency_remember("job:ws:key", "job-1") is True
    assert coordination.idempotency_remember("job:ws:key", "job-2") is False
    assert coordination.idempotency_lookup("job:ws:key") == "job-1"
    set_commands = fake.requests[0]["commands"]
    assert set_commands[1] == "sos:idem:job:ws:key"
    assert set_commands[4] == "604800"  # 7-day TTL (ephemeral, bounded)


def test_upstash_rate_limit_pipeline_shape() -> None:
    fake = FakeUpstash()
    coordination = _upstash(fake)
    decision = coordination.rate_limit(
        "provider", "demo", limit=2, window_seconds=60
    )
    assert (decision.allowed, decision.limit, decision.remaining) == (
        True, 2, 1
    )
    pipeline = fake.requests[0]["commands"]
    assert pipeline[0][0] == "INCR"
    assert pipeline[0][1].startswith("sos:rl:provider:demo:")
    assert pipeline[1][0] == "EXPIRE"
    decision = coordination.rate_limit(
        "provider", "demo", limit=2, window_seconds=60
    )
    assert decision.allowed is True  # second request still within the limit
    decision = coordination.rate_limit(
        "provider", "demo", limit=2, window_seconds=60
    )
    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.retry_after_seconds >= 1


def test_upstash_job_state_and_pending_registry() -> None:
    fake = FakeUpstash()
    coordination = _upstash(fake)
    assert coordination.job_state_set("j1", '{"attempts":0}', ttl_seconds=60)
    assert coordination.job_state_set("j1", '{"attempts":9}', ttl_seconds=60) is False
    assert coordination.job_state_get("j1") == '{"attempts":0}'
    coordination.job_state_put("j1", '{"attempts":2}', ttl_seconds=60)
    assert coordination.job_state_get("j1") == '{"attempts":2}'
    coordination.pending_job_add("ws-1", "j1", ttl_seconds=3600)
    coordination.pending_job_add("ws-1", "j1", ttl_seconds=3600)
    coordination.pending_job_add("ws-2", "j2", ttl_seconds=3600)
    pending = coordination.pending_jobs()
    assert ("ws-1", "j1") in pending and ("ws-2", "j2") in pending
    assert len(pending) == 3  # duplicates tolerated (consumers dedup)
    coordination.pending_job_remove("ws-1", "j1")
    # LREM count=1 drops ONE registration: one ws-1::j1 duplicate remains
    assert coordination.pending_jobs() == [("ws-1", "j1"), ("ws-2", "j2")]
    coordination.pending_job_remove("ws-1", "j1")
    assert coordination.pending_jobs() == [("ws-2", "j2")]


def test_upstash_health_truthful_success_and_unavailable() -> None:
    fake = FakeUpstash()
    coordination = _upstash(fake)
    health = coordination.health_check()
    assert health.status == "SUCCESS"
    assert "upstash redis ok" in health.detail
    fake.fail = True
    degraded = coordination.health_check()
    assert degraded.status == "UNAVAILABLE"
    assert "unreachable" in degraded.detail


def test_upstash_engine_maps_transport_errors() -> None:
    fake = FakeUpstash()
    fake.fail = True
    coordination = _upstash(fake)
    with pytest.raises(UpstashUnavailableError):
        coordination.idempotency_lookup("k")


# ---------------------------------------------------------------------------
# LOCAL in-process adapter (the PUB-01 baseline, PUB-06 semantics)
# ---------------------------------------------------------------------------

def test_local_lock_mutual_exclusion_and_release() -> None:
    coordination = InProcessCoordination()
    lock = coordination.acquire_lock("job-x", ttl_seconds=60)
    assert lock.acquired is True
    loser = coordination.acquire_lock("job-x", ttl_seconds=60)
    assert loser.acquired is False
    with lock:
        pass
    again = coordination.acquire_lock("job-x", ttl_seconds=60)
    assert again.acquired is True


def test_local_idempotency_and_job_state() -> None:
    coordination = InProcessCoordination()
    assert coordination.idempotency_remember("k", "v1") is True
    assert coordination.idempotency_remember("k", "v2") is False
    assert coordination.idempotency_lookup("k") == "v1"
    assert coordination.job_state_set("j", '{"a":1}', ttl_seconds=60)
    assert coordination.job_state_set("j", '{"a":2}', ttl_seconds=60) is False
    coordination.job_state_put("j", '{"a":3}', ttl_seconds=60)
    assert coordination.job_state_get("j") == '{"a":3}'
    assert coordination.job_state_get("missing") is None


def test_local_pending_registry_snapshot_and_expiry() -> None:
    coordination = InProcessCoordination()
    coordination.pending_job_add("ws", "j1", ttl_seconds=0.05)
    assert coordination.pending_jobs() == [("ws", "j1")]
    time.sleep(0.08)
    assert coordination.pending_jobs() == []  # TTL-bounded (ephemeral)
    coordination.pending_job_add("ws", "j2", ttl_seconds=60)
    coordination.pending_job_remove("ws", "j2")
    assert coordination.pending_jobs() == []


# ---------------------------------------------------------------------------
# LOCAL ↔ Upstash PARITY (contract §D PUB-06 acceptance)
# ---------------------------------------------------------------------------

def test_rate_limiter_parity_local_vs_upstash() -> None:
    """Identical decision sequences for the same request pattern: the
    LOCAL and Upstash limiters implement one semantic (epoch-aligned fixed
    windows, same decision fields, same retry_after formula)."""
    fake = FakeUpstash()
    adapters = [InProcessCoordination(), _upstash(fake)]
    original_time = time.time
    fixed_now = 100_000.5
    try:
        time.time = lambda: fixed_now  # type: ignore[assignment]
        decisions = []
        for coordination in adapters:
            sequence = [
                coordination.rate_limit(
                    "provider", "demo", limit=3, window_seconds=60
                )
                for _ in range(5)
            ]
            decisions.append(sequence)
    finally:
        time.time = original_time  # type: ignore[assignment]
    for local_decision, upstash_decision in zip(*decisions):
        assert local_decision == upstash_decision
    allowed = [d.allowed for d in decisions[0]]
    assert allowed == [True, True, True, False, False]
    assert decisions[0][0].remaining == 2
    assert decisions[0][3].retry_after_seconds >= 1


def test_rate_limiter_epoch_window_reset_parity() -> None:
    fake = FakeUpstash()
    adapters = [InProcessCoordination(), _upstash(fake)]
    original_time = time.time
    try:
        time.time = lambda: 100_079.9  # type: ignore[assignment]
        for coordination in adapters:
            for _ in range(3):
                coordination.rate_limit("ip", "c", limit=2, window_seconds=60)
            assert coordination.rate_limit(
                "ip", "c", limit=2, window_seconds=60
            ).allowed is False
        # the epoch window boundary at 100_080 resets BOTH identically
        time.time = lambda: 100_080.1  # type: ignore[assignment]
        for coordination in adapters:
            assert coordination.rate_limit(
                "ip", "c", limit=2, window_seconds=60
            ).allowed is True
    finally:
        time.time = original_time  # type: ignore[assignment]


def test_lock_and_idempotency_parity() -> None:
    fake = FakeUpstash()
    for coordination in (InProcessCoordination(), _upstash(fake)):
        lock = coordination.acquire_lock("shared", ttl_seconds=30)
        assert lock.acquired is True
        assert coordination.acquire_lock(
            "shared", ttl_seconds=30
        ).acquired is False
        lock.release()
        assert coordination.acquire_lock(
            "shared", ttl_seconds=30
        ).acquired is True
        assert coordination.idempotency_remember("k", "v") is True
        assert coordination.idempotency_remember("k", "v") is False
        assert coordination.idempotency_lookup("k") == "v"
