# W7 Implementation Checkpoint

**Work Order:** `spec/work-orders/W7-assurance-impact-analysis.md`
**State:** `WAITING_FOR_ARCHITECT` (review iteration 2)
**Branch:** `work/w7-assurance-impact-analysis`
**Base SHA:** `79736603f68e6602db49507aef548abbedf7033c`
**Reviewed head (iteration 1):** `9c28942773647e1d613f3245d10b894538558b58`
**Latest implementation SHA (iteration 2):** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Architect review (iteration 1) — two HIGH findings

Reviewed exact head `9c28942773647e1d613f3245d10b894538558b58`. Scope was five
allowed files, base matched the dispatched W7 base, and exact-head CI run #144
succeeded. Two HIGH findings blocked merge; both are resolved in iteration 2 on
the same PR.

### SOS-W7-F01 — HIGH — reversibility/containment asserted without governed evidence/policy, and does not constrain assurance — RESOLVED

Finding: `assure_candidate()` inferred `rollback_available` from whether a
free-form risk string contained "rollback"; otherwise it unconditionally set
`containment_policy="documented-containment-required"` and stated that containment
applies — with no rollback/recovery evidence record or documented containment
policy supplied or validated. `ReversibilityAssessment` was not represented as an
assurance gate, so a candidate could reach overall PASS while having neither
demonstrated rollback/recovery nor a governed containment exception — conflicting
with W7 C7 and the frozen invariant that live candidates require rollback/
equivalent governed recovery unless a documented risk policy provides
higher-order containment.

Resolution: reversibility/containment is now truthfully evidence/policy-backed:
- `assure_candidate()` accepts caller-supplied `rollback_evidence_ids` (real W4
  evidence records) and/or `containment_policy_ref` (a documented containment
  exception reference). Governance is no longer inferred from a risk-name
  substring.
- `ReversibilityAssessment` now carries `rollback_evidence_ids` and
  `containment_policy_ref`; `rollback_available=True` requires non-empty
  `rollback_evidence_ids` (enforced at construction).
- Reversibility is now an `AssuranceGate` ("reversibility-containment"): PASS only
  when rollback evidence is present + SUCCESS-validated, or a documented
  containment exception is supplied; BLOCKED when neither is present. Assurance
  cannot report PASS when the reversibility gate is BLOCKED (it participates in
  the overall-status aggregation).

Regression tests: `test_missing_rollback_and_containment_blocks_pass`,
`test_valid_documented_containment_exception_allows_reversibility_pass`,
`test_valid_rollback_evidence_allows_reversibility_pass`,
`test_risk_name_substring_does_not_infer_rollback`.

### SOS-W7-F02 — HIGH — causal PASS not evidence-traceable to the intervention evidence that proves the gate — RESOLVED

Finding: the causal gate's `evidence_ids` was populated from
`candidate.reasoning_evidence_ids`, not the actual `support.evidence_id` used to
establish PASS. So the gate could claim PASS while its recorded evidence
references omitted the evidence responsible for that status — violating C2/C6
traceability and making the justification non-auditable.

Resolution: the causal gate now collects the exact intervention-grade
`support.evidence_id` values (from referenced W5 hypotheses whose support is
`SupportKind.INTERVENTION` backed by a W4 record whose `EvidenceKind` is
intervention-grade) and records them in the gate's `evidence_ids`. The records
are validated before PASS. The gate's `evidence_ids` now contains only the actual
supporting W4 intervention record(s) — not the candidate's full reasoning set.

Regression test: `test_causal_gate_evidence_ids_are_the_actual_intervention_records`
— proves the causal gate's evidence_ids contain the actual intervention-grade
record and exclude observational evidence that was not used to establish PASS.

## Dependency proof

W6 is merged on `main` as `b5171f70ca5ce85ca0be07cfdb3abf034c03c32f` (true merge:
parents `771a190` + `4ffaf0d`). W5 merged as `2bfd0f8…`, W3 merged as `6541441…`,
W4 merged as `26060db…`, W2 merged as `587201d3…`. No unmerged sibling dependency
is used. W7 depends authoritatively only on W6 (per roadmap); W8 remains BLOCKED
until W7 is authoritatively merged.

## Scope implemented

- `AssuranceStatus` (PASS/FAIL/UNKNOWN/BLOCKED) — truthful result/gate states;
  PASS is never the default;
- `AssuranceGate` (name, status, evidence_ids, detail) — a single evidence-backed
  check with a truthful status;
- `BlastRadius` + `ImpactAnalysis` — bounded impact: affected nodes (candidate's
  declared target subgraph), affected edges (single-hop), boundary interfaces
  (declared), dependency reach (single-hop adjacency — no unbounded traversal),
  deterministic blast-radius level;
- `RiskItem` (severity, uncertainty — never SUCCESS, mitigation/residual) +
  `RiskAssessment` — risk without false certainty;
- `ReversibilityAssessment` — records whether rollback evidence exists or a
  containment policy applies; does NOT execute rollback (W8 territory);
- `AssuranceResult` (frozen, construction-validated, content-addressed SHA-256 id)
  binding to exact candidate id + base graph id/revision + provenance revision +
  W1 traceability; carries gates, impact, risk, reversibility, preserved W6
  objectives (no scalar score);
- `assure_candidate(...)` — deterministic, bounded, non-authorizing evaluation
  engine: evidence-availability gate, hard-constraint gate (FAIL on violation,
  not offset by objectives), causal-qualification gate (PASS only with
  intervention-grade W4 evidence; observational alone cannot PASS), reversibility
  assessment, risk assessment, multi-objective preservation;
- truthful aggregation: overall FAIL if any gate FAILs; BLOCKED if any BLOCKs;
  UNKNOWN if any UNKNOWN; PASS only if all gates PASS;
- JSON round-trip via the existing W1 `JsonModelStore` (no new persistence
  authority);
- W7 invariant tests and repository-resident evidence.

## Explicit exclusions

No experiment execution/shadow/canary/controlled experiments/promotion/rollout/
rollback execution/deployment mutation (W8); no autonomy/ASK/user-authorization/
decision execution (W9); no personalization/platform adapters (W10); no
greenfield/brownfield realization (W11/W12); no self-evolution/meta-adaptation
(W13); no production writes/live mutation/network orchestration/deployment
control; no second evidence/cause/architecture authority; no scalarized
architecture quality as the sole gate; no LLM-derived proof/confidence-only
safety/unsupported causal certainty.

## Requirement → implementation → test mapping

| Requirement | Acceptance criterion | Implementation | Tests |
|---|---|---|---|
| R23, R24 | C1 candidate binding + provenance | `AssuranceResult` binds candidate id + graph id/revision + provenance + W1 traceability; mismatch rejected | `test_assurance_result_binds_to_exact_candidate_and_graph`, `test_assurance_rejects_graph_id_mismatch` |
| R9, R21 | C2 evidence-backed gate evaluation | `AssuranceGate` + `_evidence_to_gate_status` + `_aggregate_gate_status` (no PASS from non-PASS; **gate evidence_ids are the actual supporting records** per SOS-W7-F02) | `test_gate_records_evidence_references_and_truthful_status`, `test_unknown_evidence_cannot_become_pass`, `test_unavailable_evidence_cannot_become_pass`, `test_causal_gate_evidence_ids_are_the_actual_intervention_records` (F02) |
| R23 | C3 impact + blast radius | `ImpactAnalysis` + `BlastRadius` (bounded single-hop) | `test_impact_identifies_affected_nodes_and_boundary_and_blast_radius`, `test_impact_is_bounded_no_unbounded_traversal` |
| R13, R21 | C4 hard-constraint enforcement | hard-constraint gate FAILs on violation; not offset by objectives | `test_hard_constraint_violation_blocks_assurance`, `test_hard_constraint_cannot_be_offset_by_objectives` |
| R21 | C5 risk representation | `RiskItem` (uncertainty never SUCCESS) + `RiskAssessment` | `test_risk_preserves_severity_likelihood_uncertainty_and_mitigation` |
| R10, R21 | C6 causal qualification | causal gate PASS only with intervention-grade W4 evidence; **gate evidence_ids are the exact support.evidence_id(s)** (SOS-W7-F02) | `test_observational_evidence_cannot_become_intervention_proof`, `test_intervention_evidence_can_pass_causal_gate`, `test_causal_gate_evidence_ids_are_the_actual_intervention_records` (F02) |
| R14 | C7 reversibility / containment | `ReversibilityAssessment` + reversibility-containment **gate** (evidence/policy-backed, blocks PASS when absent; SOS-W7-F01) | `test_reversibility_records_whether_rollback_available`, `test_reversibility_does_not_execute_rollback`, `test_missing_rollback_and_containment_blocks_pass` (F01), `test_valid_documented_containment_exception_allows_reversibility_pass` (F01), `test_valid_rollback_evidence_allows_reversibility_pass` (F01), `test_risk_name_substring_does_not_infer_rollback` (F01) |
| R12, R15 | C8 multi-objective integrity | W6 objectives preserved; no scalar score | `test_assurance_preserves_objectives_without_scalar_authority` |
| R24 | C9 deterministic bounded evaluation | `assure_candidate` pure function; bounded single-hop | `test_assurance_is_deterministic` |
| R21, R24 | C10 explicit rejection / truthful failures | `ModelValidationError` for missing inputs; truthful aggregation | `test_missing_candidate_rejected`, `test_missing_graph_rejected`, `test_unknown_evidence_id_in_candidate_rejected` |
| R24 | C11 traceability + persistence | W1 `JsonModelStore` round-trip | `test_assurance_result_round_trips_through_json` |
| R24 | C12 bounded surface / non-authorization | no W8+ symbols; no authorization flag | `test_w7_introduces_no_w8_plus_symbols`, `test_assurance_result_cannot_authorize_execution` |

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
138 passed in 0.37s
  tests/test_w1_models.py  ........   (8)
  tests/test_w2_graph.py   ........   (8)
  tests/test_w3_recovery.py .................... (20)
  tests/test_w4_evidence.py .........................  (25)
  tests/test_w5_causal.py  ..........................  (26)
  tests/test_w6_candidates.py ........................  (24)
  tests/test_w7_assurance.py ...........................  (27)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

Iteration 1 (head `9c28942`) was 133 tests (22 W7); iteration 2 adds 5 F01/F02
regression tests -> 138 total (27 W7). CI on iteration 1 ran `pytest` -> `success`
(run #144); iteration 2 CI re-runs on the corrected head.

## Known limitations

1. **Hard-constraint checking is name-containment-based.** A hard constraint is
   treated as violated if any target node id appears in the constraint string.
   Real W7 would parse constraint semantics; this bounded slice uses conservative
   containment. Extending to structured constraint parsing is a pure addition.
2. **Risk severity is static ("medium") and likelihood is UNKNOWN.** W7 represents
   risk truthfully (never SUCCESS) but does not compute calibrated severity or
   likelihood. Calibrated risk is later work.
3. **Impact is single-hop.** Dependency reach is direct adjacency only (no
   transitive closure). Bounded by design (C3); deeper reach analysis is later
   work.
4. **Causal gate checks intervention-grade evidence kind only.** It does not
   verify the W5 hypothesis's `confirmed` status (that requires the evidence-
   backed `with_status` path); it checks whether intervention-grade W4 evidence
   backs any referenced hypothesis. This is conservative (a `confirmed` hypothesis
   already required intervention evidence to reach that status).
5. **Non-authorizing.** No result authorizes execution, promotion, or autonomy.
   W7 feeds W8 (experimentation) but does not replace it.
6. **No execution side effects.** Assurance is read-only; no deployment mutation,
   no network, no rollback execution.

## Risk / rollback

- **Risk:** semantic, potentially high — W7 feeds later promotion and autonomy
  work. The implementation is read-only/non-authorizing and has no deployment
  side effects.
- **Rollback:** ordinary Git revert of the W7 PR. No running service, no data
  migration.

## Architect disposition requested

Review the exact PR head (iteration 2) and CI result against the W7 Work Order
and the two iteration-1 findings (SOS-W7-F01 + SOS-W7-F02 — both resolved). On
approval, merge the reviewed head and reconcile canonical state to W8
eligibility (W8 depends on W7). Worker state: `WAITING_FOR_ARCHITECT`. No merge,
no self-approval, no successor Work Order creation by this session.
