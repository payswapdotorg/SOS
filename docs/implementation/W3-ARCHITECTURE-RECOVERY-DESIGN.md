# W3 Architecture Recovery Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W3-architecture-recovery.md`
**Dependencies:** W2 merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9`

W3 recovers an existing software repository into the authoritative W2
`SystemState` / `ArchitectureGraph` boundary **without pretending static
repository evidence proves runtime reality**. It introduces a recovery read
boundary; it does not implement runtime telemetry, causal memory, candidate
search, assurance, experimentation, promotion or rollback.

## Governing principle

Static repository evidence is a real, observable fact about the *codebase*; it
is **not** evidence about runtime behavior, deployed topology, or live
environment. W3 represents each recovered fact at exactly the confidence its
source warrants:

- directly-read static facts (file existence, manifest contents, parsed
  dependencies) become `SUCCESS` W2 graph/state facts with exact source-path +
  revision provenance;
- runtime / deployment / environment facts that no static read can establish
  become explicit `UNKNOWN` / `UNAVAILABLE` truthful state, each with an
  explanatory detail — never an empty success.

## Recovery boundary

`recover_repository(root, revision, traceability) -> RecoveryResult` is a pure
function: no network, no subprocess, no writes to the recovered repository,
no randomness. Identical repository bytes plus the same supplied revision
produce byte-identical semantic output (deterministic ids are content-addressed
via SHA-256 of the revision and provenance parts; iteration is sorted).

### Inventory

`inventory_repository` walks the root deterministically, skipping build/dep/VCS
caches (`.git`, `node_modules`, `__pycache__`, `dist`, `build`, `.venv`, …) and
classifying each artifact conservatively into one of `FileClassification`:
source / manifest / config / deployment / policy / documentation / binary /
unclassified. Documentation, binary and unclassified files are recorded in the
inventory (provenance preserved) but do **not** become architecture nodes.

### Static → graph mapping

| Classification | W2 node type | Notes |
|---|---|---|
| source | `component` | `attributes.language` from suffix |
| manifest | `component` | `attributes.kind = manifest` |
| deployment (Dockerfile, compose, `.github/workflows/*`) | `deployment` | static artifact, not runtime topology |
| config / policy | `policy` | static configuration artifact |

No `boundary_contracts` are synthesized — static recovery does not establish
interface boundary contracts (truthful: empty tuple).

### Dependency extraction (only when directly resolvable)

Only manifests with a directly-supported parser produce dependency edges:

- `pyproject.toml` — `[project.dependencies]` (PEP-621), parsed via `tomllib`;
- `requirements.txt` — one specifier per line (comments/blank lines skipped);
- `package.json` — `dependencies`, `devDependencies`, `peerDependencies`,
  `optionalDependencies`.

Each parsed dependency becomes an `external_dependency` node (deduplicated by
name) plus a `dependency` edge from its manifest component. A manifest that is
recognised but unparseable is **not** silently empty: the file is still
recovered as an inventory fact (existence is observable), while the failed
extraction is recorded as an `UnresolvedFact` with `FAILED`/`UNKNOWN` truthful
state and an explanatory detail.

## System State reference population (the truthfulness contract)

| Reference | Truth state | Rationale |
|---|---|---|
| `implementation_ref` | `SUCCESS(revision)` | the exact repo revision is directly observable |
| `configuration_ref` | `SUCCESS` (count) when ≥1 static config recovered, else `UNKNOWN` | static config is observable; runtime/deployed config is not |
| `policy_ref` | `SUCCESS` (count) when ≥1 policy artifact recovered, else `UNKNOWN` | static policy is observable |
| `deployment_ref` | `UNAVAILABLE` | runtime deployment topology is **not** observable from static recovery |
| `environment_ref` | `UNAVAILABLE` | runtime environment is **not** observable from static recovery |

The runtime gaps that a static read cannot close are also enumerated as
`RecoveryResult.unresolved_facts` (`runtime-deployment`,
`runtime-environment`, `runtime-configuration`, and any per-manifest extraction
failure), each carrying a non-`SUCCESS` `TruthfulValue` with a detail.

## Traceability

The recovered `ArchitectureGraph` and `SystemState` carry the caller-supplied
W1 `Traceability` (constitution / mission / value-model / context). Recovery
refuses to run with a `Traceability` missing value/context refs — the W2 graph
contract requires them, and W3 threads W1 authority through W2 unchanged.

## Determinism

- file walk: `sorted(root.rglob("*"))`;
- ids: `sha256(":".join(provenance_parts))[:16]`, prefixed by kind
  (`node-`, `dep-`, `edge-`, `arch-`, `state-`, `recovered-rev-`);
- no `uuid4`, no `dict`-order dependence, no wall-clock in artifact identity.

Different supplied revisions produce different artifact identities; the same
revision on byte-identical trees produces byte-identical serialized output.

## Verification scope

Tests cover: invalid-root rejection, file-as-root rejection, empty-revision
rejection, missing-traceability rejection, valid W2 SystemState/Graph
production, frozen node/edge vocabulary adherence, source-path + revision
provenance on every recovered file, W1 traceability carried through, directly
resolvable dependency extraction, unparseable-manifest truthfulness (FAILED not
empty), runtime refs remain UNAVAILABLE and unresolved facts never SUCCESS,
determinism (byte-identical output across two byte-identical trees), revision
sensitivity, no-runtime-side-effects (network blocked; repo bytes unchanged;
no active experiments), cache exclusion, deterministic inventory ordering, and
W2 subgraph-replacement boundary rejection on the recovered graph.

## Explicit exclusions (unchanged from Work Order)

No runtime telemetry, no live environment access, no causal inference or
architecture memory, no candidate generation/search or graph mutation, no
assurance/experimentation/promotion/rollback, no autonomous authority or action
execution, no modification of frozen architecture / W1 / W2 semantics.
