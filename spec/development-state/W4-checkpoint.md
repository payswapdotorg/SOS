# W4 Implementation Checkpoint

**Work Order:** `spec/work-orders/W4-evidence-observability.md`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w4-evidence-observability`
**Base SHA:** `c2c73b3452333b4bded335a3139c97c7fba21999`
**Latest implementation SHA:** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Dependency proof

W2 is merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9` and W3 is
merged as `6541441bb706ef1f27b2c38b9eb930433641b14b` (true merge: parents
`ac61765` + `57c5633`). No unmerged sibling dependency is used. W4 depends
authoritatively only on W2 (per roadmap); W5 remains BLOCKED until W4 is
authoritatively merged.

## Scope implemented

- `Evidence` record with the frozen meta-model fields (id, kind, source_ref,
  subject_ref, timestamp, environment, result, provenance, confidence,
  availability, traceability) and construction-time validation;
- frozen 13-kind `EvidenceKind` vocabulary (observation, test, static-analysis,
  simulation, replay, shadow, canary, experiment, deployment, user-outcome,
  business-outcome, incident, rollback);
- `EvidenceProvenance` with exact source, observed subject, timestamp,
  environment and implementation_revision (None when not supplied — truthful);
- deterministic, content-addressed identity (SHA-256 over kind/source/subject/
  result/provenance) — identical evidence ⇒ identical id; no uuid4, no wall-clock;
- `EvidenceGraph` with deterministic ordering, dedup-by-id ingestion, and
  by-subject indexing;
- truthful state separation: SUCCESS/FAILED/UNKNOWN/UNAVAILABLE/EMPTY never
  conflated (reuses W1 `TruthState`/`TruthfulValue` — no competing truth
  authority); UNAVAILABLE availability + SUCCESS result rejected as conflation;
- `StaticEvidenceAdapter` (test results, static observations, explicit
  unavailable runtime observations) — does NOT fabricate runtime facts;
- `OpenTelemetryShapedAdapter` (spans, metrics, logs) — no live collector;
  missing runtime fields stay UNKNOWN/UNAVAILABLE, never fabricated SUCCESS;
- subject linkage to recovered W2/W3 System State / Architecture Graph entities
  by id string, without mutating the recovered graph (no semantic authority
  change); optional `known_subject_ids` validation rejects unknown subjects;
- full W1 Mission/Value/Context traceability threaded through evidence records;
- JSON round-trip via the existing W1 `JsonModelStore` (no new serialization
  authority);
- W4 invariant tests and repository-resident evidence.

## Explicit exclusions

No causal inference or causal confidence (W5); no architecture memory/priors
(W5); no candidate generation/search or graph mutation (W6); no assurance
verdicts or safety gates (W7); no experimentation/promotion/rollback (W8); no
autonomy/action/ASK execution (W9); no modification of the frozen architecture,
the architecture lock, requirements, roadmap, W1/W2/W3 semantics,
`implementation-state.json`, or `current-state.md`.

## Requirement → implementation → test mapping

| Requirement | Acceptance criterion | Implementation | Tests |
|---|---|---|---|
| R9, R24 | C1 deterministic identity + exact provenance | `Evidence`, `EvidenceProvenance`, `_evidence_id` | `test_evidence_has_deterministic_identity_and_exact_provenance`, `test_identical_evidence_inputs_produce_identical_identity` |
| R9 | C2 subject linkage without semantic authority change | `Evidence.subject_ref` (string); graph never mutated | `test_evidence_references_recovered_subjects_without_mutating_graph` |
| R21 | C3 truthful states distinct | reuses W1 `TruthState`/`TruthfulValue`; availability/result conflation rejected | `test_truthful_states_remain_distinct`, `test_success_requires_value_and_non_success_rejects_value` |
| R21 | C4 no runtime fabrication from static evidence | `StaticEvidenceAdapter.unavailable_runtime_observation`; static evidence carries revision but not runtime claims | `test_static_evidence_does_not_claim_runtime_reality`, `test_unavailable_runtime_observation_is_explicit_not_synthesized` |
| R23 | C5 W1 traceability preserved | `traceability.validate(require_value=True, require_context=True)` | `test_evidence_carries_w1_traceability`, `test_evidence_rejects_traceability_missing_context` |
| R24 | C6 deterministic duplicate ingestion | `EvidenceGraph.ingest` dedup by content-addressed id; sorted ordering | `test_repeated_identical_ingestion_is_deterministic`, `test_evidence_graph_orders_records_deterministically` |
| R24 | C7 invalid subjects / malformed evidence rejected | `Evidence.__post_init__` + `validate(known_subject_ids=...)` | `test_invalid_subject_reference_rejected`, `test_malformed_evidence_rejected`, `test_out_of_range_confidence_rejected` |
| R24 | C8 evidence-only boundary | structural: no causal/candidate/assurance/experiment/promotion/rollback/autonomy symbols exported | `test_w4_introduces_evidence_only_no_downstream_semantics` |
| R9 | OTel ingestion boundary (no fabrication, no live collector) | `OpenTelemetryShapedAdapter` | `test_otel_span_ingestion_preserves_truth_and_provenance`, `test_otel_ingestion_does_not_fabricate_runtime_when_fields_missing` |
| R24 | serialization round trip | W1 `JsonModelStore` reuse | `test_evidence_graph_round_trips_through_json` |

## Verification

CI workflow: `.github/workflows/test.yml` (runs on push and PR).

Deterministic verification commands (run from repo root):

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results (recorded in the PR description at push time):

```text
$ python -m pytest
59 passed in 0.25s
  tests/test_w1_models.py  ........   (8)
  tests/test_w2_graph.py   ........   (8)
  tests/test_w3_recovery.py .................... (20)
  tests/test_w4_evidence.py .......................  (23)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

## Known limitations

1. **No causal confidence machinery.** `Evidence.confidence` is an optional
   calibrated probability in `[0,1]`, None when not supplied. Causal confidence
   updates and intervention-vs-observation distinction belong to W5; W4 records
   the evidence fact and its provenance only.
2. **OTel ingestion is shaped, not spec-complete.** The adapter accepts the
   common span/metric/log fields directly supplied as mappings. It does not
   implement the full OTel collector protocol, resource attributes, or
   exponential histograms — those are out of W4's bounded scope. Missing fields
   stay UNKNOWN/UNAVAILABLE (truthful), not fabricated.
3. **Subject validation is optional.** `Evidence.validate(known_subject_ids=...)`
   rejects unknown subjects only when a known set is supplied. Evidence may be
   constructed without a known set (e.g. before a recovered graph exists); the
   subject_ref is still required to be a non-empty string.
4. **Evidence does not establish runtime reality.** A static observation with
   `kind=OBSERVATION` and `availability=SUCCESS` means "this observation was
   captured"; it does not assert the subject's runtime behavior. Runtime facts
   not directly observed remain UNKNOWN/UNAVAILABLE by design (criterion 4).
5. **No live collector.** The OTel adapter ingests supplied mappings only; it
   does not open a network port or poll a collector.

## Risk / rollback

- **Risk:** low-to-moderate semantic. Evidence contracts become inputs to later
  assurance/causal stages. W4 introduces no runtime service, no production data
  migration, and touches no frozen artifact.
- **Rollback:** ordinary Git revert of the W4 PR. No running services to drain.

## Architect disposition requested

Review the exact PR head and CI result against the W4 Work Order. On approval,
merge the reviewed head and reconcile canonical state to W5 eligibility (W5
depends on W4). Worker state: `WAITING_FOR_ARCHITECT`. No merge, no
self-approval, no successor Work Order creation by this session.
