# Upstash Redis — coordination plane (PUB-03 setup runbook)

Operator runbook for the ephemeral coordination layer (directive §3 Upstash
lane, §13 rate limits, §20 environments). Upstash Redis **Free**: 256 MB,
500K commands/month, 10 GB/month bandwidth, scale-to-zero.

**What Upstash holds (ephemeral only):** request rate limiting, idempotency
keys, short-lived job state, orchestration locks, API/session cache,
polling state, duplicate-job suppression. **Redis is NEVER the primary
event store** — jobs are durable in Neon/SQLite (directive §3; contract §D
PUB-06 "Forbidden").

## Ownership boundaries (contract lanes)

| Concern | Owner |
|---|---|
| Infrastructure provisioning/verification (this runbook + `setup.py`) | PUB-03 (Worker C) |
| Coordination adapter + LOCAL in-process parity (`providers/upstash/**`) | PUB-06 (Worker A) |
| Job model, idempotency semantics, §13 limiter buckets | PUB-06 (Worker A) |
| `SOS_REDIS_URL` naming | `infra/environment.example` (naming authority) |

## Operator steps (console-first, idempotent verification)

1. Create a free Redis database at console.upstash.com:
   - Name: `sos-coordination`; Region: closest to the Render service
     (`oregon`); TLS: **on** (the app contract expects `rediss://`).
   - Copy the **UPSTASH REDIS URL** (`rediss://default:<password>@…:6379`).
2. Verify it (native RESP PING over TLS — stdlib, no client deps):

   ```bash
   export SOS_REDIS_URL='rediss://default:<password>@<endpoint>:6379'
   python3 infra/upstash/setup.py
   # → [ok] RESP PING → PONG (…, TLS)
   ```

   The script reuses the APPLICATION variable name (`SOS_REDIS_URL`) on
   purpose: what you verified is exactly what you wire.

   Alternative (REST verification): export `UPSTASH_REDIS_REST_URL` +
   `UPSTASH_REDIS_REST_TOKEN` instead; the script PINGs via the REST API
   and reminds you to set the `rediss://` form for the app.

3. Copy `SOS_REDIS_URL` into the **Render dashboard** (service `sos-api` →
   Environment).
4. Optional convenience (creation via management API instead of console):

   ```bash
   export UPSTASH_OWNER_EMAIL=<email> UPSTASH_OWNER_API_KEY=<key>
   python3 infra/upstash/setup.py --create
   ```

   The v2 API response does not include the database password/REST token —
   the script says so and points you to the console (no guessed values).

5. Plan-only / offline modes (what CI can honestly run):

   ```bash
   python3 infra/upstash/setup.py --dry-run    # offline plan, no network
   python3 infra/upstash/setup.py --selftest   # offline known-answer tests
   ```

## Rate-limit budgeting (directive §13, Stage C)

The §13 buckets (anonymous 60/min, user 240/min, write 30/min, job 10/hour,
recovery 2/hour — see `infra/environment.example` and the Render env
wiring) are designed so a single free-tier Redis stays well inside 500K
commands/month at Stage A/B traffic levels. At Stage C, watch the Upstash
console usage graphs and tighten `SOS_RATE_*` on Render before approaching
the quota — do not silently disable limiting.

## Why console-first

Upstash free-tier provisioning is most reliably done through the console
(password/REST-token retrieval included); the script's `--create` path is a
convenience only. Verification (the part worth automating) works against
whatever you created — that is the idempotent guarantee.
