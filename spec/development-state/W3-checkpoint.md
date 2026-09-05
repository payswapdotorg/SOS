# W3 Implementation Checkpoint

**Work Order:** `spec/work-orders/W3-architecture-recovery.md`
**State:** `WAITING_FOR_ARCHITECT` (review iteration 2)
**Branch:** `work/w3-architecture-recovery`
**Base SHA:** `ac6176503fc7417db2e85075db37bad68a8e6bca`
**Reviewed head (iteration 1):** `dfd904c393e47b75393a34312ad1ab994a3c4e5e`
**Latest implementation SHA (iteration 2):** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Architect review (iteration 1) — REQUEST_CHANGES

Reviewed exact head `dfd904c393e47b75393a34312ad1ab994a3c4e5e` against the W3 Work
Order, base `ac6176503fc7417db2e85075db37bad68a8e6bca`. CI was green. Two HIGH
findings were issued; both are resolved in iteration 2 on the same PR.

### SOS-W3-F01 — HIGH — out-of-scope file — RESOLVED

Finding: `.gitignore` is outside the W3 allowed implementation surfaces.

Resolution: removed `.gitignore` from the PR (`git rm`). No scope broadening. The
allowed surfaces remain exactly: `src/sos/` recovery implementation, `tests/` W3
tests, `docs/implementation/W3-ARCHITECTURE-RECOVERY-DESIGN.md`, and this
checkpoint file.

### SOS-W3-F02 — HIGH — missing explicit graph-fact provenance — RESOLVED

Finding: `RecoveredFile` carried source-path + revision provenance, but the
recovered W2 graph/dependency facts (`GraphNode`/`GraphEdge`) did not propagate
that provenance onto themselves.

Resolution: `_build_graph` now threads explicit `source_path` + `revision`
provenance onto every recovered graph fact via the existing W2 `attributes`
extensibility seam (no W2 schema change, no new authority). Concretely:

- file-derived nodes (component/source, component/manifest, deployment, policy)
  carry `attributes.source_path` (the recovered file's posix-relative path) and
  `attributes.revision` (the recovered repository revision);
- external-dependency nodes carry `attributes.source_manifest`,
  `attributes.source_path` (the manifest that declared the dependency) and
  `attributes.revision`;
- dependency edges carry `attributes.source_manifest`, `attributes.source_path`
  and `attributes.revision`.

Deterministic tests assert provenance on representative facts across the
recovered vocabulary (component, deployment, policy, external-dependency nodes
and dependency edges), and confirm provenance is deterministic across
byte-identical inputs.

## Dependency proof

W2 is merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9` (true merge:
parents `f9dc2e5` + `6efda5f`). No unmerged sibling dependency is used. W4 is
independently eligible by roadmap dependency on W2 but is **not** dispatched
in this cycle — W3 is the sole active Work Order.

## Scope implemented

- deterministic repository inventory (`inventory_repository`) with sorted,
  posix-relative paths and exact-revision provenance on every recovered file;
- conservative static classification (`FileClassification`) of source / manifest
  / config / deployment / policy / documentation / binary / unclassified;
- typed W2 `ArchitectureGraph` population (component / external_dependency /
  deployment / policy nodes) with `SUCCESS` graph uncertainty for directly-read
  facts and explicit `UNKNOWN` / `UNAVAILABLE` for runtime gaps;
- **explicit source-path + revision provenance on every recovered W2 graph fact**
  (node and edge `attributes`), in addition to the inventory-level provenance
  (F02 resolution);
- repository-local dependency extraction only when directly resolvable
  (`pyproject.toml` PEP-621, `requirements.txt`, `package.json`), with
  per-manifest parse-failure recorded as `FAILED`/`UNKNOWN` — never empty success;
- W2 `SystemState` with `implementation_ref = SUCCESS(revision)`,
  `deployment_ref = UNAVAILABLE`, `environment_ref = UNAVAILABLE`,
  truthful `configuration_ref`/`policy_ref`;
- explicit `unresolved_facts` enumeration for every runtime/deployment/
  environment gap and every failed dependency extraction;
- full W1 Mission/Value/Context traceability threaded through W2 contracts
  (recovery refuses to run with an incomplete `Traceability`);
- deterministic, content-addressed identifiers (SHA-256 of revision + provenance)
  — no `uuid4`, no wall-clock, sorted iteration → byte-identical output for
  byte-identical input + same revision;
- W3 invariant tests and repository-resident evidence.

## Explicit exclusions

No runtime telemetry or live environment access; no causal inference or
architecture memory (W5); no candidate generation/search or graph mutation
(W6); no assurance, experimentation, promotion or rollback (W7–W8); no
autonomous authority or action execution (W9); no modification of the frozen
architecture, the architecture lock, requirements, roadmap, the W1/W2 semantics,
`implementation-state.json`, or `current-state.md`.

## Requirement → implementation → test mapping

| Requirement | Acceptance criterion | Implementation | Tests |
|---|---|---|---|
| R6, R7, R8 | C1 explicit deterministic root | `inventory_repository` root/revision validation | `test_recovery_rejects_nonexistent_root`, `test_recovery_rejects_file_as_root`, `test_recovery_rejects_empty_revision` |
| R7, R23 | C2 typed W2 graph facts with provenance | `_build_graph` + `RecoveredFile` provenance **+ graph-fact `attributes` provenance (F02)** | `test_recovery_produces_valid_w2_system_state_and_graph`, `test_recovered_facts_carry_source_path_and_revision_provenance`, `test_recovered_graph_facts_carry_explicit_source_path_and_revision_provenance`, `test_recovered_graph_provenance_is_deterministic`, `test_recovered_graph_uses_frozen_node_and_edge_vocab` |
| R8 | C3 dependencies only when resolvable | `_extract_dependencies` (pyproject/requirements/package.json) | `test_repository_local_dependencies_extracted_when_resolvable`, `test_unparseable_manifest_does_not_silently_become_empty_success` |
| R21 | C4 runtime gaps remain UNKNOWN/UNAVAILABLE | `deployment_ref`/`environment_ref` UNAVAILABLE + `UnresolvedFact` | `test_runtime_deployment_environment_facts_remain_unavailable`, `test_no_runtime_facts_disguised_as_success_in_refs` |
| R23 | C5 W1 traceability through W2 | `traceability.validate(require_value=True, require_context=True)` | `test_recovered_state_carries_w1_traceability`, `test_recovery_rejects_traceability_missing_context` |
| R24 | C6 determinism | content-addressed ids + sorted walk | `test_recovery_is_deterministic_same_bytes_same_revision`, `test_different_revision_produces_different_artifact_identity`, `test_recovered_graph_provenance_is_deterministic` |
| R24 | C7 invalid roots/broken refs rejected | validation gates + W2 `SubgraphReplacement.validate` | invalid-root tests + `test_recovered_graph_validates_subgraph_replacement_boundary` |
| R24 | C8 no runtime/candidate/assurance/experiment side effects | pure-read recovery; no W4–W8 code | `test_recovery_has_no_runtime_side_effects` (network blocked, repo bytes unchanged, `active_experiments == ()`) |

## Verification

CI workflow: `.github/workflows/test.yml` (added in W2; runs on push and PR).

Deterministic verification commands (run from repo root):

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results (iteration 2, recorded in the PR description at push time):

```text
$ python -m pytest
36 passed in 0.20s
  tests/test_w1_models.py  ........   (8)
  tests/test_w2_graph.py   ........   (8)
  tests/test_w3_recovery.py .................... (20)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

Iteration 1 (head `dfd904c`) was 34 tests; iteration 2 adds 2 F02 provenance
tests for a total of 36. CI on iteration 1 ran `pytest` → `success` (both
push and PR triggers).

## Known limitations

1. **Dependency extraction covers three manifest kinds** (`pyproject.toml`,
   `requirements.txt`, `package.json`). Other manifests (`go.mod`, `Cargo.toml`,
   `Gemfile`, `pom.xml`, …) are recovered as inventory facts (existence) but
   their dependencies are recorded as `UNKNOWN` (unsupported extractor), not
   silently empty. This is intentionally conservative; extending parsers is a
   pure addition and does not change the boundary.
2. **No boundary contracts are synthesized.** Static recovery does not
   establish interface boundary contracts; `ArchitectureGraph.boundary_contracts`
   is an empty tuple. Boundary recovery is deferred to richer static/dynamic
   analysis in later Work Orders.
3. **Runtime facts are explicitly unresolved.** `deployment_ref`,
   `environment_ref`, and the runtime/deployed configuration are
   `UNAVAILABLE`/`UNKNOWN` — W3 makes no claim about runtime reality. This is
   the central truthfulness contract, not a gap to be "fixed".
4. **Classification is conservative and heuristic.** A file's node type is the
   best deterministic static guess; the architecture graph is, per the frozen
   architecture, a *hypothesis*. Recovered node `GraphUncertainty` is
   `SUCCESS(1.0)` meaning "deterministically recovered from the repository at
   this revision", not "semantically certain to be a `component` in production".
5. **Recovery does not read the live git index.** The revision is a supplied
   parameter (the caller provides the exact repository revision), keeping
   recovery a pure function with no subprocess and no `git` dependency.

## Risk / rollback

- **Risk:** low. W3 is a read/recovery semantic boundary; it does not mutate
  recovered production state, introduces no runtime service, and touches no
  frozen artifact.
- **Rollback:** ordinary Git revert of the W3 PR. No data migration, no running
  services to drain.

## Architect disposition requested

Review the exact PR head (iteration 2) and CI result against the W3 Work Order
and the two iteration-1 findings (F01, F02 — both resolved). On approval, merge
the reviewed head and reconcile canonical state to W4 eligibility (W4 is already
independently eligible by roadmap dependency on W2). Worker state:
`WAITING_FOR_ARCHITECT`. No merge, no self-approval, no successor Work Order
creation by this session.
