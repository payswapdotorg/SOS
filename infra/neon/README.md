# Neon — durable relational state (PUB-03 setup runbook)

Operator runbook for the durable system-of-record (directive §3 Neon lane,
§11 data model, §20 environments). Neon PostgreSQL **Free** plan: up to 100
projects, 100 CU-hours/project, 0.5 GB storage/project, 10 branches,
scale-to-zero.

**What Neon holds:** users, workspaces, missions/revisions, value models,
contexts, systems/revisions, architecture graphs, evidence METADATA,
hypotheses, candidates/evaluations, assurance results, decisions,
authorizations, experiments/events, execution receipts, learning records,
architecture-memory indexes, audit trail, jobs/status metadata. **Large
evidence blobs NEVER go in Postgres** — they are R2 objects referenced by
`evidence_artifacts` rows.

## Ownership boundaries (contract lanes)

| Concern | Owner |
|---|---|
| Infrastructure provisioning (this runbook + `setup.py`) | PUB-03 (Worker C) |
| Relational schema + migrations (`db/migrations`, forward-creatable + reversible) | PUB-01 scaffolding, PUB-05 (Worker A) full entity set |
| The persistence adapter (`providers/neon/**`) + LOCAL SQLite parity | PUB-05 (Worker A) |
| `SOS_DATABASE_URL` naming | `infra/environment.example` (naming authority) |

This script provisions/verifies infrastructure ONLY — no schema, no
application logic (thin-lane discipline applies to infra tooling too).

## Operator steps (idempotent — safe to re-run)

1. Create a Neon API key: console.neon.tech → Account settings → API keys.
2. Export it in your shell (never commit it, never paste it into Git/PRs):

   ```bash
   export NEON_API_KEY=<your key>
   ```

3. Plan first (offline, touches nothing):

   ```bash
   python3 infra/neon/setup.py --dry-run
   ```

4. Provision (creates project `sos-public` and branch `main` if missing):

   ```bash
   python3 infra/neon/setup.py
   ```

   Re-running is safe: every step is find-by-name, create-if-missing.
   `--verify-only` never creates (use it in pre-deploy checks).

5. Copy the printed `SOS_DATABASE_URL` value into the **Render dashboard**
   (service `sos-api` → Environment). The script prints the
   `postgresql+asyncpg://…` form the application contract expects.

6. Migrations run automatically at application boot (`db/runner.py` via
   `services/api`); verify after first deploy:

   ```bash
   curl -s https://<render-service>.onrender.com/api/v1/health | python3 -m json.tool
   ```

   The `checks` map must report the persistence adapter truthfully
   (`SUCCESS`, or a real degraded state — never a fake ok).

## Preview branches (PREVIEW environment)

```bash
export SOS_NEON_BRANCH=preview-pr-31
python3 infra/neon/setup.py            # creates branch + database + role if missing
```

Point the preview stack at that branch's URI. Never point a preview at the
production branch (see `docs/deployment/preview-environments.md`). Delete
stale preview branches when their PR closes (console or
`DELETE /projects/{id}/branches/{branch_id}`).

## Variables read (operator shell only — see environment.example)

| Variable | Default | Purpose |
|---|---|---|
| `NEON_API_KEY` | — (required for live runs) | Neon account API key |
| `SOS_NEON_PROJECT` | `sos-public` | project name |
| `SOS_NEON_BRANCH` | `main` | branch to provision/verify |
| `SOS_NEON_API_BASE` | `https://api.neon.tech/v2` | API base (drift safety) |

## Offline verification (what CI/sandbox can honestly check)

```bash
python3 infra/neon/setup.py --selftest   # known-answer tests, no network
python3 infra/neon/setup.py --dry-run    # plan printout, no network
```

Live provisioning requires operator credentials and is recorded as an
operator-input step in the deployment runbook (Stage A) — it is NOT
fabricated as done in any checkpoint.
