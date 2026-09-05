# W6 Implementation Checkpoint

**Work Order:** `spec/work-orders/W6-candidate-generation-search.md`
**State:** `WAITING_FOR_ARCHITECT`
**Branch:** `work/w6-candidate-generation-search`
**Base SHA:** `771a1903321ff2e30cef0f67af49c8e870b3e485`
**Latest implementation SHA:** recorded as the PR `head.sha` (authoritative review head per `ARCHITECT-REVIEW-PROTOCOL §2`)

## Dependency proof

W3 is merged on `main` as `6541441bb706ef1f27b2c38b9eb930433641b14b` and W5 is
merged as `2bfd0f89da129c6b3347d88b0d8da1b79dd04127` (true merges). W2 merged as
`587201d3…`, W4 merged as `26060db…`. No unmerged sibling dependency is used. W6
depends authoritatively on W3 + W5 (both complete, per roadmap); W7 remains
BLOCKED until W6 is authoritatively merged.

## Scope implemented

- `SubgraphMutation` (frozen, construction-validated) — bounded declarative
  mutation referencing the base graph by id; validates against a recovered
  `ArchitectureGraph` **without mutating it** (boundary interfaces are preserved-
  by contracts, adjacent to the target subgraph);
- `MutationKind` vocabulary (subgraph-replace, add-node, remove-node, add-edge,
  remove-edge, retype-node);
- `CandidateObjective` (name, direction, predicted_value, uncertainty — never
  SUCCESS) + `ObjectiveDirection` (maximize, minimize, maintain);
- `CandidateEvaluation` — multi-objective evaluation with `dominates()` Pareto
  relation; no scalar quality field;
- `CandidateProposal` (frozen, construction-validated, content-addressed SHA-256
  id) referencing base graph + revision, mutation, objectives, rationale, W1
  `TruthfulValue` uncertainty (never SUCCESS), W4 evidence ids + W5 hypothesis
  ids, risks, full W1 traceability;
- `SearchBounds` (max_candidates, max_depth, max_iterations — positive integers);
- `CandidateSpace` (finite: base graph + revision + traceability + reasoning
  refs + finite `available_replacements`);
- `ParetoFrontier` — deterministic non-dominated set, sorted by id;
  `from_candidates()` classmethod;
- `SearchEngine` — bounded, deterministic search; pure function of (space, bounds);
  no network, no wall-clock, no unbounded recursion;
- truthfulness: candidate uncertainty never SUCCESS (predictions, not proven
  facts); predicted objective values carry non-SUCCESS uncertainty;
- full traceability: every candidate records base graph ref + revision +
  provenance revision + W4 evidence ids + W5 hypothesis ids + W1 traceability;
  `validate(known_graph=, known_evidence_ids=, known_hypothesis_ids=)` resolves
  references against actual W2/W4/W5 records;
- JSON round-trip via the existing W1 `JsonModelStore` (no new persistence
  authority);
- W6 invariant tests and repository-resident evidence.

## Explicit exclusions

No assurance verdicts/impact/risk/safety gates (W7); no experiments/canary/shadow/
promotion/rollback (W8); no autonomy/ASK/user-authorization (W9); no contextual
personalization/platform (W10); no greenfield/brownfield realization (W11/W12);
no SOS self-evolution (W13); no mutation of the canonical W2/W3 graph or production
system; no replacement evidence or causal stores; no silent optimization away of
hard constraints/privacy/safety/fairness/legal; no rewrite of Constitution/Mission/
Value Model/System State/Evidence/Causal Knowledge/frozen architecture/requirements/
roadmap/Work Orders; no use of LLM narrative or candidate score as evidence of
correctness/authorization/safety/causal efficacy.

## Requirement → implementation → test mapping

| Requirement | Acceptance criterion | Implementation | Tests |
|---|---|---|---|
| R11, R24 | C1 candidate identity + provenance | `_candidate_id` (SHA-256 over graph+mutation+objectives+reasoning) | `test_identical_candidates_produce_identical_identity`, `test_differing_mutation_produces_distinct_identity` |
| R8, R24 | C2 bounded mutation; canonical immutable | `SubgraphMutation.validate(graph)` (no mutation) | `test_candidate_mutation_validates_against_graph_without_mutating_it`, `test_candidate_mutation_rejects_unknown_target_nodes`, `test_candidate_mutation_rejects_unknown_boundary_node` |
| R11, R24 | C3 finite deterministic search | `SearchEngine.search` bounded by `SearchBounds` | `test_search_terminates_within_bounds_and_is_deterministic`, `test_search_rejects_unbounded_or_zero_bounds` |
| R12, R15 | C4 multi-objective/Pareto | `CandidateEvaluation.dominates`, `ParetoFrontier.from_candidates` | `test_pareto_dominance_is_deterministic`, `test_pareto_frontier_excludes_dominated_candidates`, `test_no_single_scalar_quality_becomes_authoritative` |
| R21, R24 | C5 uncertainty/truthfulness | candidate uncertainty never SUCCESS; objectives never SUCCESS | `test_candidate_scores_cannot_upgrade_truth`, `test_candidate_must_not_claim_success_without_intervention_evidence` |
| R9, R23 | C6 evidence/causal traceability | base_graph_ref + revision + reasoning_evidence_ids + reasoning_hypothesis_ids + W1 traceability | `test_candidate_records_graph_evidence_and_causal_references`, `test_candidate_rejects_traceability_missing_context` |
| R24 | C7 deterministic dedup/order | content-addressed id; `ParetoFrontier` sorted by id | `test_repeated_identical_candidates_deduplicate`, `test_frontier_orders_candidates_deterministically` |
| R24 | C8 explicit rejection | construction-time + `validate(known_*)` | `test_candidate_rejects_missing_graph_reference`, `test_candidate_rejects_empty_objectives`, `test_candidate_rejects_empty_mutation_targets` |
| R24 | C9 repository persistence | W1 `JsonModelStore` round-trip | `test_frontier_round_trips_through_json` |
| R24 | C10 bounded surface | no W7+ symbols exported | `test_w6_introduces_no_w7_plus_symbols` |
| R23 | validate against known records | `validate(known_graph=, known_evidence_ids=, known_hypothesis_ids=)` | `test_candidate_validates_reasoning_references_against_known_records` |

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
109 passed in 0.34s
  tests/test_w1_models.py  ........   (8)
  tests/test_w2_graph.py   ........   (8)
  tests/test_w3_recovery.py .................... (20)
  tests/test_w4_evidence.py .........................  (25)
  tests/test_w5_causal.py  ..........................  (26)
  tests/test_w6_candidates.py ......................  (22)
$ python -m compileall -q src tests
(clean, no syntax errors)
```

## Known limitations

1. **Candidate generation is structural, not LLM-driven.** The search engine
   generates candidates from the finite `available_replacements` space (one
   candidate per (target, replacement) pair). LLM-driven candidate generation is
   out of W6's bounded scope — an LLM narrative alone cannot establish correctness
   (§13.4); W6 provides the bounded structural search boundary, not a reasoning
   engine.
2. **Predicted objective values are caller-supplied, not computed.** The default
   objectives are placeholder predictions; real prediction of latency/cost/
   throughput from a candidate mutation is later work. W6 represents the
   multi-objective evaluation boundary, not a predictor.
3. **Pareto dominance is over predicted values only.** No uncertainty-weighted
   dominance (e.g. stochastic dominance) — predictions are compared by point value.
   Uncertainty is preserved on each objective but does not affect dominance
   ordering. Stochastic/uncertainty-aware ranking is deferred.
4. **Search is single-depth by default.** `max_depth` is accepted but the engine
   generates one candidate per replacement (no chained/composed mutations beyond
   depth 1 in this slice). Composed candidate generation is later work.
5. **Non-authorizing.** No candidate authorizes an action, promotion, or
   autonomous decision. W6 feeds assurance (W7) but does not replace it.
6. **No canonical graph mutation.** `SubgraphMutation.validate(graph)` checks
   structural validity against the recovered graph; it never mutates the graph.

## Risk / rollback

- **Risk:** moderate-to-high semantic — W6 feeds assurance (W7). The model is
  kept explicitly untrusted, bounded, multi-objective, traceable, and
  non-authorizing. No production mutation is permitted.
- **Rollback:** ordinary Git revert of the W6 PR. No running service, no data
  migration.

## Architect disposition requested

Review the exact PR head and CI result against the W6 Work Order. On approval,
merge the reviewed head and reconcile canonical state to W7 eligibility (W7
depends on W6). Worker state: `WAITING_FOR_ARCHITECT`. No merge, no
self-approval, no successor Work Order creation by this session.
