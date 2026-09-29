# W11 Implementation Checkpoint (first bounded slice)

**Work Order:** `spec/work-orders/W11-execution-substrate.md` (frozen, authoritative)
**State:** `WAITING_FOR_ARCHITECT` (review iteration 1)
**Branch:** `work/w11-execution-substrate` (from live `main`)
**Base SHA (dispatch commit, live `main` after the W10 merge):**
`f148569447fd162db1bef88a9fe6b5b2ea111992`
**Exact implementation head (contract code, exports, tests):**
`dd4d987f2ca5b75f1e0b5ae93d4c13d89fb4a18d`
**Exact branch tip:** the commit that carries this checkpoint plus
`docs/implementation/W11-EXECUTION-SUBSTRATE-DESIGN.md` (documentation-only
delta from the implementation head above; a commit cannot embed its own SHA —
the authoritative review head is recorded in the worker report
`/home/z/replay2/scripts/worker-reports/98-A-report.md`). The verification
outputs below were re-run at the tip.

## Dependency proof

W1 merged `091d4d10a38922fb2d9cadb103e7ba8caa7a1f20`, W2 merged
`587201d3e12a10ba9fac6da751d663a40c33dfb9`, W9 merged
`203cfb7590bd25244cabf3cc7299dd192b00948d`, W10 merged
`a1778653c35064eeb9d71563f17b30fb174d9429` (all per
`spec/development-state/implementation-state.json` at the dispatch commit
`f148569`, status `W11_DISPATCHED`, frontier `[W11]`). The Work Order's stated
dependency set (W1, W2, W9) is therefore complete on live main; W7/W8 (also
complete) are reused as frozen authorities. No unmerged sibling branch was
treated as a dependency: the PREP artifacts (prep branch
`work/w11-execution-substrate-prep` @ `816f62e`, unmerged by design) were used
as non-authoritative reference material only.

## Scope implemented (exactly the five allowed files)

- `src/sos/execution.py` (NEW, ~640 lines): the promoted contract —
  `ExecutionContractError(ModelValidationError)`, `ExecutionActionScope`,
  `ProviderCapability`, `ExecutionLifecycleState` + frozen transition table +
  `validate_lifecycle_transition`, `SideEffectKind`/`SideEffect`,
  `RollbackReference`, `ExecutionRequest`, `ExecutionReceipt`
  (construction-validated, content-addressed ids),
  `ExecutionProviderPort` (protocol) + `ProviderUnavailableSignal`,
  `ExecutionSubstrate` (core dispatcher, caller-supplied registries),
  `receipt_to_w4_evidence` (verbatim W4 binding). No provider names, no
  network, no subprocess, no clocks.
- `src/sos/__init__.py` (MODIFIED, +16 lines): W11 exports only (15 names);
  zero other changes.
- `tests/test_w11_execution.py` (NEW, ~1100 lines): the 24 PREP contract
  invariants promoted (every invariant name and assertion kept, adapted to the
  real module) + 8 Work-Order-mandated extensions. The two stub providers stay
  local to the test module (injected port objects).
- `docs/implementation/W11-EXECUTION-SUBSTRATE-DESIGN.md` (NEW): design
  reconciled to the implementation, WO-traceable.
- `spec/development-state/W11-checkpoint.md` (NEW): this file.

Zero modifications to W1–W10 sources, frozen specs, roadmap, or Work Order
machinery (verified: `git diff --name-only f148569..HEAD` lists exactly the
four non-checkpoint files above; the fifth is this file).

## Acceptance criteria → implementation → test mapping

| Criterion | Implementation | Tests |
|---|---|---|
| C1 W9 pre-execution authorization | required `w9_decision_id` at construction; submit gates 1–4 (resolve, scope state, provider-not-authorizer, exact refs) | `test_request_without_w9_authorization_reference_is_rejected`, `test_unresolved_w9_reference_is_rejected_before_dispatch`, `test_ask_decision_cannot_authorize_execution`, `test_request_authority_chain_must_match_w9_decision`, `test_provider_cannot_self_authorize`, `test_w9_reject_decision_cannot_authorize_any_scope` |
| C2 DEPLOY assurance binding | submit gate 5 (W7 resolves, PASS, exact graph/revision/provenance chain, experiment bound to the same assurance) | `test_deploy_requires_w7_pass_assurance_bound_to_exact_chain` |
| C3 capability separation | submit steps 8–9 separate from gates; `OUTCOME_UNSUPPORTED` no-run receipt | `test_capability_is_separate_from_authorization`, `test_fully_authorized_request_without_capability_is_unsupported_not_rejected` |
| C4 exact provenance + content addressing | receipt echo fields + `_verify_receipt_provenance`; sha256 ids over own material | `test_receipt_provenance_is_exact`, `test_receipt_id_is_content_addressed_and_deterministic` |
| C5 distinct failure outcomes | receipt validation (EMPTY unlawful; no-run prohibitions; terminal/outcome agreement) | `test_outcomes_remain_distinct`, `test_unavailable_provider_yields_unavailable_receipt`, `test_unknown_provider_id_yields_unavailable_receipt`, `test_empty_is_not_a_lawful_execution_outcome`, `test_no_run_receipts_cannot_claim_side_effects`, `test_terminal_lifecycle_and_outcome_must_agree`, `test_unknown_timeout_yields_outcome_unknown_receipt` |
| C6 governed rollback | DEPLOY/ROLLBACK require bounded `RollbackReference`; reference must equal the experiment's `rollback_ref`; ROLLBACK needs a ROLLBACK-state decision | `test_deploy_request_requires_bounded_rollback_reference`, `test_observe_request_needs_no_rollback_reference`, `test_rollback_reference_must_bind_to_experiment_rollback_ref`, `test_rollback_execution_is_governed` |
| C7 two-provider neutrality | port protocol only in core; two structurally different test-local stub providers | `test_second_provider_implements_the_same_contract`, `test_provider_selection_changes_only_the_provider_field` |
| C8 determinism | single-threaded substrate; clock-free core; content-addressed ids | `test_receipt_id_is_content_addressed_and_deterministic`, `test_unknown_timeout_yields_outcome_unknown_receipt` (resubmission stability), full-suite determinism |
| C9 W1 persistence round-trip | no new persistence; `JsonModelStore` round-trip; idempotent W4 re-ingestion | `test_request_and_receipt_round_trip_through_w1_json_store`, `test_identical_receipt_reingestion_is_idempotent` |
| C10 bounded authority surface | `ExecutionContractError` in the W1 family; authorities referenced by identity; no W12/W13/integration symbols | `test_execution_contract_error_is_anchored_in_w1_validation_family`, `test_w11_introduces_no_w12_w13_or_provider_integration_symbols`, `test_w11_references_frozen_authorities_without_redefining` |

Frozen resolutions honored: stub enum names kept; OBSERVE authorizes under
`GATHER_EVIDENCE` or `ACT` (`test_observe_authorizes_under_gather_evidence_and_act`);
stream refs are opaque provider strings; REQUESTED/REJECTED are explicit enum
states with rejection raising before dispatch; no containment-exception field.

## Verification

```text
python3 -m pytest
python3 -m compileall -q src tests
```

Exact-head results (implementation head `dd4d987`; re-run at the branch tip,
which adds documentation only — identical counts):

```text
$ python3 -m pytest
327 passed in 0.86s
$ python3 -m compileall -q src tests
(exit code 0; no output — clean)
```

Exact pass count: **327** (0 failed, 0 errors, 0 skipped) = 295 baseline
(verified at base `f148569` before any work) + 32 new W11 tests (24 promoted
PREP invariants + 8 extensions). Duration is environment-dependent; counts are
exact. Fully offline: no network, no provider, no wall clock.

## Honest deviations

1. **`ExecutionContractError` base class** — the PREP stub subclassed bare
   `ValueError`; the Work Order (required outcome 2 / PREP design §6.1 item 2)
   mandates the W1 `ModelValidationError` anchor. Implemented as required.
2. **`StubExecutionSubstrate` → `ExecutionSubstrate`** — the stub core
   dispatcher is promoted under its Work-Order-frozen real name; the two stub
   *providers* keep their stub names and stay test-local per required
   outcome 10.
3. **`receipt_to_w4_evidence` lives in core** (`src/sos/execution.py`), not in
   the test module — it is the "`→ Evidence` binding" end of the Work Order's
   mission boundary and the reuse point for the idempotent re-ingestion
   invariant. It reuses the W4 module's package-internal assembly helper
   `_build_evidence` (same reuse the PREP stub performed) so the
   content-addressed evidence identity algorithm exists exactly once; identity
   of every referenced authority is test-asserted.
4. **Two commits** (implementation `dd4d987` + this documentation commit)
   instead of one, following the W10 convention so the checkpoint can record
   an exact implementation head SHA.

No other deviations from the envelope, Work Order, or PREP reference shape.

## Known limitations

1. Contract evidence, not deployment evidence: the substrate is exercised
   exclusively through injected stub providers in deterministic tests (Work
   Order "Evaluation" section — no live provider, credential, or external
   system touched).
2. Registries are caller-supplied in-memory dictionaries; persistence of the
   registries themselves is a later slice (the round-trip test proves the
   requests/receipts persist via W1 `JsonModelStore`).
3. No timeout enforcement in core (clock-free by design): the UNKNOWN timeout
   path is provider-supplied data; a configured deadline rule would be a
   governed later addition.
4. `receipt_to_w4_evidence` maps OBSERVE-scope receipts to `DEPLOYMENT`-kind
   evidence (frozen PREP reference shape; no observation-kind execution
   receipt mapping was specified by the Work Order).
5. REJECTED/REQUESTED lifecycle states are never emitted as receipt
   lifecycles by the core (rejection raises before dispatch; the frozen
   resolution keeps them for state-machine completeness only).

## Risk / rollback

**Risk:** boundary leakage — an execution path that could bypass W9
authorization or render provider output as evidence/truth. The C1–C10
invariants make such leakage mechanically impossible; the promoted tests are
the executable proof. **Rollback:** ordinary Git revert of the merged W11
change. No deployment, network side effect, or data migration in this slice.

## Completion state

`WAITING_FOR_ARCHITECT`. No merge, no push, no successor Work Order, no W12
dispatch, no canonical-state modification. W11 completion requires the
Architect gate, actual Git merge, and canonical reconciliation recording the
W11 merge and the next frontier. Corrections stay on this branch.
