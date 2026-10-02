# infra/ — Free-tier infrastructure (Public Deployment Overlay)

Operator-facing infrastructure for the SOS public deployment (directive §3,
§4, §20, §21; contract §B/§D PUB-03). Nothing here contains credentials:
every setup script reads operator-held values from the shell and every
deployment secret is entered in the provider dashboard (security gate S2).

| Path | What it is | Owner |
|---|---|---|
| `render.yaml` | Render Blueprint for the `sos-api` FastAPI service (free plan, Python runtime, rootDir `services/api`, health check `/api/v1/health`, env wiring per `environment.example`, spin-down notes) — FINAL, supersedes the PUB-00 skeleton | PUB-03 |
| `environment.example` | The environment variable naming authority for the ENTIRE overlay (app runtime names + web client names + operator setup-shell names) | PUB-00 created; PUB-01/PUB-03 extend additively |
| `vercel/` | Vercel project config template (`vercel.json`) + operator runbook for the `apps/web` public tier | PUB-03 |
| `neon/` | Neon PostgreSQL setup: idempotent `setup.py` + runbook (durable relational state) | PUB-03 |
| `upstash/` | Upstash Redis setup: idempotent `setup.py` + runbook (ephemeral coordination plane) | PUB-03 |
| `r2/` | Cloudflare R2 setup: verification `setup.py` (stdlib S3 SigV4) + runbook (private evidence/artifact storage) | PUB-03 |
| `apify/` | Apify bounded-execution actor SKELETON (package metadata + input schema + stub entry; **no Dockerfile by contract §A.7** — it lands with PUB-08) | PUB-03 skeleton, PUB-08 implementation |

## Deployment docs

Operator runbooks live in `docs/deployment/`:

- `deployment-runbook.md` — Stage A (private) → B (public read/demo) →
  C (authenticated beta), with the operator-held credential inputs per
  stage and truthful verification legs;
- `preview-environments.md` — Vercel preview + Neon branch guidance;
- `ci-gates.md` — the `pub` workflow (this overlay's §G gate matrix) and
  its relationship to the frozen `tests` workflow.

## Local/offline verification (honest, no credentials)

```bash
python3 infra/neon/setup.py --dry-run && python3 infra/neon/setup.py --selftest
python3 infra/upstash/setup.py --dry-run && python3 infra/upstash/setup.py --selftest
python3 infra/r2/setup.py --dry-run && python3 infra/r2/setup.py --selftest
echo '{…bounded job input…}' | python3 infra/apify/src/main.py   # see infra/apify/README.md
```

Live provisioning/verification (Neon project creation, RESP/REST PING,
R2 round-trip) requires operator-held credentials and is an operator-input
step in the Stage A runbook — never fabricated as done.
