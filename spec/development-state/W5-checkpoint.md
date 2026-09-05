# W5 Implementation Checkpoint

**Work Order:** `spec/work-orders/W5-causal-knowledge-memory.md`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w5-causal-knowledge-memory`
**Base SHA:** `0af66c6aaae45e154af4f49bb4175002a17b4543`
**Latest implementation SHA:** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Dependency proof

W4 is merged on `main` as `26060db57c24ba8b36315c1005466046810c5163` (true merge:
parents `c2c73b3` + `cf94ff7`). W2 merged as `587201d3…`, W3 merged as
`6541441…`. No unmerged sibling dependency is used. W5 depends authoritatively
only on W4 (per roadmap); W6 remains BLOCKED until W5 is authoritatively merged.

## Scope implemented

- `CausalHypothesis` (frozen, construction-validated) linking cause/effect
  subjects with frozen `CausalRelationType`, direction, lifecycle status, W1
  `TruthfulValue` uncertainty, supporting W4 evidence references, exact
  `provenance_revision`, and full W1 traceability;
- deterministic, content-addressed identity (SHA-256 over claim semantics +
  sorted supporting evidence ids + support kind) — identical claims with
  identical evidence ⇒ identical id; differing relation/direction/subjects/
  evidence ⇒ distinct ids;
- `EvidenceSupport` referencing W4 evidence ids with explicit `SupportKind`
  (observational vs intervention); intervention support requires explicit
  `InterventionMetadata` (intervention_id, intervention_kind, applied_at,
  revision, environment); observation-only support cannot be encoded as
  intervention;
- `CausalKnowledgeGraph` with deterministic ordering, dedup-by-id ingestion,
  by-subject indexing, and `validate(known_evidence_ids=,
  known_evidence_results=)`;
- truthful uncertainty: unsupported claims carry non-SUCCESS uncertainty (no
  implied truth); when observed result states are supplied, non-SUCCESS evidence
  cannot back a SUCCESS (positive) causal claim; contradictory hypotheses
  coexist with distinct identities;
- status authority gating: `confirmed` (causal certainty) requires
  intervention-grade support (architecture §13.4); observation-only support
  cannot reach `confirmed`;
- `ArchitectureMemory` as a versioned projection referencing the W2/W3 graph by
  id — never mutates the canonical graph, never silently replaces architecture
  truth; `validate(known_graph_id=, …)` rejects graph_ref mismatch;
- JSON round-trip via the existing W1 `JsonModelStore` (no new persistence
  authority);
- W5 invariant tests and repository-resident evidence.

## Explicit exclusions

No candidate generation/search/graph mutation/optimization (W6); no assurance
verdicts/impact/risk/safety gates (W7); no experiments/canary/shadow/promotion/
rollback (W8); no autonomy/ASK/user-authorization (W9); no contextual
personalization/platform semantics (W10); no greenfield/brownfield realization
(W11/W12); no SOS self-evolution (W13); no rewrite of Constitution/Mission/
Value Model/System State/Evidence authority/frozen architecture/requirements/
roadmap/Work Orders; no live telemetry collection or replacement evidence store;
no causal certainty derived from LLM narrative/text/confidence.

## Requirement → implementation → test mapping

| Requirement | Acceptance criterion | Implementation | Tests |
|---|---|---|---|
| R9, R24 | C1 deterministic causal identity | `_hypothesis_id` (SHA-256 over semantics + evidence) | `test_identical_causal_claims_produce_identical_identity`, `test_differing_relation_semantics_produce_distinct_identity`, `test_differing_supporting_evidence_produces_distinct_identity` |
| R9 | C2 evidence-backed support | `validate(known_evidence_ids=…)`; unsupported ⇒ non-SUCCESS uncertainty | `test_causal_claim_must_reference_existing_evidence`, `test_unsupported_claim_must_carry_explicit_hypothesis_state`, `test_unsupported_claim_with_success_uncertainty_is_rejected` |
| R10, R21 | C3 observation vs intervention | `SupportKind` + `InterventionMetadata`; observation≠intervention enforced | `test_observation_only_support_cannot_be_encoded_as_intervention`, `test_intervention_support_requires_intervention_metadata_and_provenance`, `test_intervention_support_without_intervention_metadata_rejected` |
| R21 | C4 truthful uncertainty | `validate(known_evidence_results=…)`; contradictions coexist | `test_unknown_unavailable_failed_evidence_cannot_become_positive_causal_support`, `test_contradictory_hypotheses_coexist` |
| R9 | C5 no authority mutation | `ArchitectureMemory.graph_ref` (string ref); graph never mutated | `test_causal_memory_does_not_mutate_canonical_graph` |
| R24 | C6 deterministic memory behavior | `CausalKnowledgeGraph.ingest` dedup by id; sorted | `test_repeated_identical_ingestion_is_idempotent`, `test_causal_graph_orders_hypotheses_deterministically` |
| R23 | C7 provenance and traceability | `provenance_revision` + evidence ids + `traceability.validate(require_value=True, require_context=True)` | `test_causal_claim_carries_evidence_ids_and_revision_and_traceability`, `test_causal_claim_rejects_traceability_missing_context` |
| R19, R23 | C8 architecture memory is a projection | `ArchitectureMemory` versioned; `graph_ref` mismatch rejected | `test_architecture_memory_is_versioned_projection_not_replacement`, `test_architecture_memory_rejects_graph_ref_mismatch` |
| R24 | C9 repository persistence | W1 `JsonModelStore` round-trip | `test_causal_graph_round_trips_through_json` |
| R24 | C10 bounded surface | no W6+ symbols exported | `test_w5_introduces_no_w6_plus_symbols` |
| R10 | status lifecycle + intervention authority | `with_status("confirmed")` requires intervention support | `test_hypothesis_status_transitions_are_explicit`, `test_intervention_backed_hypothesis_can_reach_confirmed` |

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
83 passed in 0.28s
  tests/test_w1_models.py  ........   (8)
  tests/test_w2_graph.py   ........   (8)
  tests/test_w3_recovery.py .................... (20)
  tests/test_w4_evidence.py .........................  (25)
  tests/test_w5_causal.py  ......................  (22)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

## Known limitations

1. **Causal confidence is qualitative, not calibrated.** `CausalHypothesis`
   carries a W1 `TruthfulValue` uncertainty; calibrated probability estimates
   are out of W5's bounded scope (architecture §3.8 "Uncertainty semantics"
   reserves calibrated confidence for later). W5 represents uncertainty
   truthfully but does not compute calibration.
2. **Evidence-result validation is caller-supplied.** `validate(
   known_evidence_results=…)` enforces the truthful-uncertainty gate only when
   the caller supplies the observed result states. W5 records evidence ids; it
   does not own the W4 evidence records. Callers that ingest a `CausalHypothesis`
   alongside its `EvidenceGraph` should pass the evidence result map to enforce C4.
3. **No causal inference algorithm.** W5 represents and stores causal hypotheses;
   it does not infer new hypotheses from evidence (that is later work). Hypotheses
   are proposed by callers and validated against supplied evidence.
4. **Architecture memory is a projection only.** `ArchitectureMemory` references
   a recovered graph by id and stores hypotheses as priors; it never mutates the
   canonical graph and never replaces recovered architecture facts.
5. **Non-authorizing.** No causal claim authorizes an action, candidate
   promotion, or autonomous decision. W5 is evidence-backed knowledge, not
   authority.

## Risk / rollback

- **Risk:** moderate semantic — W5 becomes the source used by later
  candidate/search (W6) and assurance (W7) stages. The model is kept explicitly
  hypothesis/evidence-backed and non-authorizing.
- **Rollback:** ordinary Git revert of the W5 PR. No running service, no data
  migration.

## Architect disposition requested

Review the exact PR head and CI result against the W5 Work Order. On approval,
merge the reviewed head and reconcile canonical state to W6 eligibility (W6
depends on W3 + W5; both would then be complete). Worker state:
`WAITING_FOR_ARCHITECT`. No merge, no self-approval, no successor Work Order
creation by this session.
