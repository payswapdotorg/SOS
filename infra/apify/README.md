# SOS Bounded Execution Actor — SKELETON (PUB-03)

Apify actor project skeleton for the SOS public deployment's bounded
execution/ingestion lane (directive §3 Apify lane, §9 execution providers,
§16-C Worker C). **This is a skeleton delivered by PUB-03, not a working
actor.**

## Scope discipline (what lands when)

| Piece | Status | Owner |
|---|---|---|
| Package metadata (`.actor/actor.json`) | ✅ PUB-03 | Worker C |
| Bounded input schema (`.actor/input_schema.json`) | ✅ PUB-03 | Worker C |
| Stub entry (`src/main.py`) — validates input invariants, emits an explicitly-marked stub acknowledgment | ✅ PUB-03 | Worker C |
| Dependency manifest (`requirements.txt`) | ✅ PUB-03 (metadata only) | Worker C |
| **Dockerfile** | ❌ PUB-08 (contract §A.7: must NOT land in PUB-03) | Worker C |
| Real bounded execution, resource-limit enforcement, artifact upload, signed callback emission | ❌ PUB-08 | Worker C |
| `execution/adapters/apify.py` (W11 substrate mapping) + signed callback endpoint | ❌ PUB-08 | Worker C |

The stub's acknowledgment is explicitly marked `"status": "stub"` — it is
**not an execution receipt**, and nothing downstream may treat it as one
(no false SUCCESS — contract §A.6 truth-state discipline).

## The bounded input contract (why this shape)

The schema encodes directive §9's bounded-request rules and the security
gate (§19 / PUBLIC-DEPLOYMENT-SECURITY.md):

- **exact source revision** — 40-hex commit SHA only; mutable refs like
  "latest main" are rejected (S11);
- **one allowed operation** from a closed enum — the actor executes within
  it or refuses;
- **hard resource limits** — time/memory/output-size maxima (S14); a run
  that exceeds them aborts FAILED, never reports success;
- **signed callback target** — url/nonce/timestamp/signature envelope;
  validated by the API BEFORE any state mutation (S10);
- **no self-authorization** — `authorizedAction` is what the SOS authority
  layer already decided; the actor carries it, never grants it (S12);
- **request hash** — the receipt echoes the dispatched request's SHA-256 so
  the API can verify the run matched the job exactly.

## Local skeleton check (no Apify account, no SDK needed)

```bash
echo '{
  "jobId": "job-demo-0001",
  "tenantId": "ws-demo",
  "authorizedAction": "architecture_recovery",
  "sourceRevision": {"kind": "github_commit", "url": "https://github.com/example/repo", "revision": "0123456789abcdef0123456789abcdef01234567"},
  "allowedOperation": "repository_analysis",
  "limits": {"timeLimitSeconds": 300, "maxMemoryMb": 1024, "maxOutputArtifactMb": 20},
  "callbackTarget": {"url": "https://sos-api.onrender.com/api/v1/providers/apify/callback", "nonce": "nonce-0123456789abcdef", "timestamp": "2026-10-03T00:00:00Z", "signature": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"},
  "requestHash": "a" * 64
}' | python3 src/main.py
```

Expected: a JSON acknowledgment with `"status": "stub"`, `"accepted": true`,
exit code 0. An input with, e.g., a mutable revision or missing limits is
rejected with exit code 1 (fail-closed, before any work).

## Free-tier budget (directive §3)

Apify free plan: $5 platform usage, up to 5 concurrent runs, $0.20/CU
compute. The actor is therefore **asynchronous and selective** — dispatched
only for bounded execution/ingestion jobs, never per page load. The
dispatcher additionally holds a low-concurrency semaphore
(`SOS_APIFY_MAX_CONCURRENT=2`, S14).
