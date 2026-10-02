# CI Gates — the `pub` workflow + the frozen `tests` workflow (PUB-03)

## The two workflows and their contract

| Workflow | File | Trigger | Matrix | Owner |
|---|---|---|---|---|
| `tests` (frozen) | `.github/workflows/test.yml` | every push + PR | pytest only (hermetic; API tests skip via `importorskip` when the api group is absent) | W15-era CI (untouched by the overlay; PUB-01 disclosed precedent a956325 for its full-history checkout) |
| `pub` (new, PUB-03) | `.github/workflows/pub.yml` | PRs to `main` touching the overlay roots + `workflow_dispatch` | the full §G gate matrix: pytest **with the api group installed**, compileall, `final_gate_check.py` 12/12, apps/web bun lint/typecheck/test | PUB-03 (Worker C) |

The `tests` workflow's semantics are **byte-untouched** by the overlay
program (contract §D PUB-03 "Forbidden: touching the existing tests
workflow"). The `pub` workflow is a new file that strengthens PR-time
verification for overlay changes; it does not replace anything.

## Why the pub matrix installs `-e ".[api]"`

The frozen `tests` workflow installs only pytest, so PUB-01's API tests
`importorskip` and the frozen suite stays dependency-free by construction.
The pub matrix's job is the **full §G matrix**, which includes the API
adapter tests actually RUNNING — so it installs the `api` dependency group
(fastapi/uvicorn/pydantic/httpx) from the root `pyproject.toml`. Result:
`tests` = fast frozen gate on every push; `pub` = the strong overlay gate
on overlay PRs. Both stay green on every head (contract §G).

## Full-history checkout (both python jobs)

`fetch-depth: 0` mirrors the `tests` workflow: the W15 final-gate
integration test resolves historical SHAs across the whole W0–W15 lineage
through the real Git resolver (a shallow clone leaves pre-merge SHAs
unresolved and fails G04). The pub workflow's `final_gate_check.py` step
depends on the same property.

## Trigger scope (paths)

The pub workflow runs on PRs to `main` that touch:

- the eight overlay roots (contract §A.4): `apps/**`, `services/**`,
  `providers/**`, `execution/**`, `db/**`, `infra/**`, `docs/deployment/**`,
  `spec/deployment/**`;
- the machine state + per-item checkpoints
  (`spec/development-state/public-deployment-state.json`,
  `spec/development-state/PUB-*.md`) — reconciliation PRs get the matrix too;
- the files that drive the matrix itself: `pyproject.toml` (owns the
  dependency groups) and the workflow file.

PRs that touch none of these still run the frozen `tests` workflow — no
verification gap exists. `workflow_dispatch` lets the TL re-run the matrix
at any exact head (anti-fabrication §F: reported numbers are never trusted;
the reviewer re-runs fresh).

## Local equivalents (run before pushing any overlay branch)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[api]" pytest
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q src tests services providers execution
.venv/bin/python tools/final_gate_check.py
cd apps/web && bun install && bun run lint && bun run typecheck && bun test
```

## render.yaml structural validation (documented manual equivalent)

`render blueprint validate` (Render CLI, authenticated) is the official
check. The documented manual equivalent — used in PUB-03 verification when
the CLI is unavailable — is:

1. YAML parses (`python3 -c "import yaml,sys; yaml.safe_load(open('infra/render.yaml'))"`);
2. exactly one `services[]` entry of `type: web`, `runtime: python`,
   `plan: free`, `rootDir: services/api`, `healthCheckPath: /api/v1/health`;
3. `buildCommand`/`startCommand` reference the repo-root pyproject install
   (`-e '../..[api]'`) and `uvicorn services.api.main:app --app-dir ../..`;
4. every `envVars[].key` exists in `infra/environment.example` (the naming
   authority), secrets use `sync: false`, non-secret values match the
   documented defaults.

The PUB-03 checkpoint records this validation honestly (including that the
authenticated Render CLI check is an operator-input step at Stage A).
