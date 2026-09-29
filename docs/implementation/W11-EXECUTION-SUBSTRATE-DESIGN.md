# W11 Execution Substrate Design (first bounded slice)

**Status:** IMPLEMENTED — REVIEW REQUIRED (`WAITING_FOR_ARCHITECT`, review iteration 1)
**Work Order:** `spec/work-orders/W11-execution-substrate.md` (frozen; authoritative)
**Dependencies:** W1 merged `091d4d10`; W2 merged `587201d3`; W9 merged `203cfb7`;
W10 merged `a177865` (verified live main at dispatch `f148569447fd162db1bef88a9fe6b5b2ea111992`)
**Base:** `main` @ `f148569447fd162db1bef88a9fe6b5b2ea111992`
**Preparation source (non-authoritative reference):**
`docs/implementation/PREP-W11-EXECUTION-SUBSTRATE-DESIGN.md` (Worker B, prep branch
`work/w11-execution-substrate-prep` @ `816f62e58cffb23ead2208318c36a8f52c0762f7`, TL
joint-review PASS, unmerged by design) and the 24-invariant PREP stub contract
`tests/test_prep_w11_execution_contract.py` (field-for-field reference shape)
**Module:** `src/sos/execution.py`; W11 exports in `src/sos/__init__.py`;
contract tests `tests/test_w11_execution.py`

This document records what was actually built and reconciles the PREP design to
the promoted implementation. Where the two differ, the Work Order resolved the
difference (its "Resolutions of the PREP open questions" section is frozen):

| PREP open question | Frozen W11 resolution | Implementation |
| --- | --- | --- |
| Enum naming | keep the stub names | `ExecutionActionScope` (DEPLOY/ROLLBACK/OBSERVE), `ProviderCapability` (8 members), `ExecutionLifecycleState` (11 states incl. REQUESTED/REJECTED) |
| OBSERVE authorizing states | accepts `GATHER_EVIDENCE` or `ACT` | `_SCOPE_AUTHORIZING_STATES[OBSERVE] = {GATHER_EVIDENCE, ACT}`; DEPLOY requires `ACT`; ROLLBACK requires `ROLLBACK`; ASK and REJECT authorize nothing |
| Stream references | provider-supplied opaque reference strings | `stdout_ref`/`stderr_ref`/`log_ref`: non-empty when supplied, contents never carried |
| REQUESTED/REJECTED enum states | remain explicit for state-machine completeness | both present; rejection raises before dispatch (no receipt exists because nothing was attempted) |
| Containment-exception field | none in this slice — DEPLOY-requires-rollback stands | `DEPLOY`/`ROLLBACK` requests are unconstructible without a `RollbackReference`; a governed exception would need an Architecture Change Request |

## 1. What was promoted (module layout)

`src/sos/execution.py` contains exactly the Work Order's port boundary:

- **Error authority** — `ExecutionContractError(ModelValidationError)`: anchored
  in the W1 validation-error family (PREP stub used a bare `ValueError`
  subclass; the Work Order required outcome 2 mandates the W1 anchor — this is
  the one deliberate contract-level adaptation of the stub).
- **Frozen vocabulary** — `ExecutionActionScope`, `ProviderCapability`,
  `ExecutionLifecycleState`, `SideEffectKind`.
- **Contract types** — `SideEffect`, `RollbackReference`, `ExecutionRequest`,
  `ExecutionReceipt` (all frozen dataclasses, construction-validated,
  content-addressed ids).
- **Governed lifecycle machine** — the frozen FROM→TO transition table plus
  `validate_lifecycle_transition` (W9/W8 transition-contract style).
- **Port protocol** — `ExecutionProviderPort` (`runtime_checkable` `Protocol`:
  `provider_id`, `capabilities`, `execute`) and `ProviderUnavailableSignal`.
  The port exposes no method that grants, mints, or upgrades authorization.
- **Core dispatcher** — `ExecutionSubstrate` (the promoted
  `StubExecutionSubstrate`): caller-supplied registries, authority gates, then
  truthful outcomes.
- **Evidence binding** — `receipt_to_w4_evidence`: receipts convert verbatim
  (observed, not inferred) into W4 `Evidence` of kind `DEPLOYMENT`/`ROLLBACK`.

The two stub providers (`StubWorkspaceExecutionProvider`,
`StubReadOnlyExecutionProvider`) stayed in the test module — injected port
objects, not core code (Work Order required outcome 10). No provider name, SDK,
transport, URL, or credential appears in `src/sos/` (enforced by
`test_w11_introduces_no_w12_w13_or_provider_integration_symbols`, which scans
both the exported symbols and the module source).

## 2. Authority reuse (referenced, never duplicated)

| Contract element | Owning authority (reused) | Binding |
| --- | --- | --- |
| Truth states / truthful values | W1 `TruthState`, `TruthfulValue` | receipt outcome is a `TruthfulValue`; EMPTY is rejected as an execution outcome at construction |
| Traceability | W1 `Traceability` | every request carries it (value + context required) |
| Validation-error family | W1 `ModelValidationError` | `ExecutionContractError` subclasses it |
| Persistence | W1 `JsonModelStore` | requests/receipts round-trip; no new persistence authority |
| Authorization | W9 `AutonomyDecision` + `AutonomyDecisionState` | required `w9_decision_id`; substrate resolves against caller-supplied `known_decisions`; scope/authorizer/chain gates |
| Assurance gate | W7 `AssuranceResult` | DEPLOY re-verifies PASS + exact graph/revision/provenance chain against `known_assurance` |
| Experiment / rollback chain | W8 `Experiment` | DEPLOY/ROLLBACK resolve `known_experiments`; `rollback_reference.reference == experiment.rollback_ref` (SOS-W9-F12 style) |
| Evidence binding | W4 `Evidence`/`EvidenceKind`/`EvidenceProvenance` + the package-internal assembly helper `_build_evidence` | one content-addressing algorithm for evidence identity; `EvidenceGraph.ingest` remains the only evidence-graph authority (idempotent dedup) |
| Deterministic identity | repo-wide content-addressed id pattern | `exec-request-<sha256[:16]>` / `exec-receipt-<sha256[:16]>` over own material; no uuid, no wall clock |

Reuse note (honest, reviewed): `receipt_to_w4_evidence` calls
`sos.evidence._build_evidence`, the W4 module's assembly helper. This is the
same reuse the PREP stub performed, kept so the evidence identity algorithm
exists exactly once (duplicating the digest material would create a competing
evidence authority). The promoted test
`test_w11_references_frozen_authorities_without_redefining` asserts the
identity of every referenced authority symbol against its owning module.

## 3. Submit pipeline (order is normative; identical to the PREP design §2.7)

```
submit(request):
  1. request.validate()                    # construction already required w9_decision_id
  2. resolve W9 reference                  # unresolved -> ExecutionContractError (rejected)
  3. decision state authorizes scope       # ASK/REJECT authorize nothing
  4. provider is not the authorizer        # decision.policy_id != request.provider_id
  5. request refs == decision refs         # w7/w8/promotion bindings
  6. DEPLOY: W7 PASS + exact chain         # known_assurance registry, W8 entry-gate principle
     + W8 experiment chain + experiment.assurance_result_id == request.w7_assurance_id
  7. rollback reference == experiment.rollback_ref
  8. provider lookup: unknown id           # -> UNAVAILABLE no-run receipt
  9. capability check                      # -> UNSUPPORTED no-run receipt (not a rejection)
 10. provider.execute(request)             # ProviderUnavailableSignal -> UNAVAILABLE receipt
 11. receipt.validate() + provenance verified against the request (echo equality)
```

Steps 2–7 are authority gates: violations raise `ExecutionContractError` and
the request is rejected **before any provider call** (the provider stub's
`execute_calls` counter is asserted to stay 0 in every gate test). Steps 8–10
are truthful outcome paths: they produce receipts because something observable
happened (a capability decision, an engagement attempt, an execution).

## 4. Determinism, threading, and clocks

One `ExecutionSubstrate` instance is single-threaded (dict registries; no
locks, no queues, no worker pools — the Work Order's recommended
deterministic policy). Core logic consults no clock, no randomness, and no
network: deadlines and timestamps are caller- or provider-supplied data. The
UNKNOWN timeout path demonstrates the frozen rule — a timeout manifests as
provider-supplied data (`started_at` set, `finished_at` unknown, UNKNOWN
outcome with an explanatory detail); the core invents no deadline of its own.
Identical inputs produce identical results: request/receipt ids are sha256
digests over their own material, and `test_receipt_id_is_content_addressed_and_deterministic`
plus `test_unknown_timeout_yields_outcome_unknown_receipt` assert resubmission
stability.

## 5. Receipt invariants (unchanged from the PREP design §2.4/§5)

- **R1 no-run** — UNAVAILABLE/UNSUPPORTED receipts are unconstructible with
  side effects, changed revisions, stream refs, rollback references, or
  timestamps ("unavailable rendered as successful data" is impossible by type).
- **R2 detail** — non-SUCCESS outcomes carry a non-empty explanatory detail
  (W1 `TruthfulValue` rule).
- **R3 timestamps** — required for terminal ran-states; `started_at` required
  once execution may have run; both `None` for no-run terminals.
- **R4 governed rollback** — ROLLED_BACK requires a governed
  `RollbackReference` with non-empty recovery evidence ids.
- **R5 exact provenance** — all echoes non-empty and verified equal to the
  request at submit (`_verify_receipt_provenance`).
- Terminal lifecycle ↔ outcome agreement (SUCCEEDED→SUCCESS, FAILED→FAILED,
  OUTCOME_UNKNOWN→UNKNOWN, UNAVAILABLE→UNAVAILABLE, UNSUPPORTED→UNSUPPORTED,
  ROLLED_BACK→SUCCESS); EMPTY unlawful; the four non-success outcomes pairwise
  distinct.

## 6. Test promotion and extension

`tests/test_w11_execution.py` is the PREP contract suite promoted to the real
module: **all 24 invariant names and assertions kept** (adapted only to import
the contract surface from `sos` / the real `ExecutionSubstrate` class instead
of local stubs; the two stub providers and the provenance-echo helper stayed
local). Extensions (Work-Order-mandated coverage, extend-never-weaken):

| Extension test | Work Order coverage |
| --- | --- |
| `test_w9_reject_decision_cannot_authorize_any_scope` | "W9 REJECT refusal" (required regression list) |
| `test_unknown_timeout_yields_outcome_unknown_receipt` | "UNKNOWN timeout path" |
| `test_observe_authorizes_under_gather_evidence_and_act` | frozen resolution: OBSERVE accepts GATHER_EVIDENCE or ACT |
| `test_request_and_receipt_round_trip_through_w1_json_store` | C9 "W1 round-trip" |
| `test_identical_receipt_reingestion_is_idempotent` | required outcome 9: idempotent re-ingestion (W4 dedup pattern) |
| `test_execution_contract_error_is_anchored_in_w1_validation_family` | C10 error anchoring |
| `test_w11_introduces_no_w12_w13_or_provider_integration_symbols` | C10 + exclusions (no W12/W13/integration symbols; source scan for provider/live-execution tokens) |
| `test_w11_references_frozen_authorities_without_redefining` | C10 (no duplicate W1/W4/W7/W8/W9 authorities — identity assertions) |

## 7. What this slice is NOT (Work Order exclusions honored)

No live execution, network I/O, subprocess spawning, or external side effect
inside `src/sos/`; no provider names/SDKs/transports/URLs/credentials in
`src/sos/`; no OpenMuse/Code-OSS integration (the seam stays as the
PREP-provider-cockpit design — a later slice); no W12 brownfield loops, no
W13 self-evolution; no new mission/value/context/evidence/assurance/
experiment/rollback/autonomy/error/persistence authority; no execution path
that bypasses W9/W7/W8 gates; no inferred evidence (receipts convert verbatim;
UNAVAILABLE may never render as success downstream — the UNAVAILABLE receipt's
evidence has `availability=SUCCESS` capture with an UNAVAILABLE **result**,
which W4 keeps distinct); no modification of frozen W1–W10 semantics.

## 8. Traceability

Work Order required outcomes 1–10 ↔ acceptance criteria C1–C10 map one-to-one
onto the module elements above and the tests in §6 (see the checkpoint file
`spec/development-state/W11-checkpoint.md` for the full criterion → test
table). Requirements: R6 (the substrate is the realization boundary both entry
paths converge on), R7 (exact graph id/revision pinning), R8 (bounded action
scope), R9 (receipt → W4 evidence with exact provenance), R13 (W7 PASS chain
re-verified before dispatch), R14 (governed rollback), R15 (W9 decision
reference required and resolved), R18 (provider port + capability matrix; no
provider semantics in core), R22 (W9 is the only authorization; providers
cannot self-authorize), R23 (explainability by evidence: receipts, typed side
effects, exact provenance, authorization echo), R24 (repo-governed
implementation: this design + tests are review artifacts). Architecture
sections: §4 (control plane), §8 (platform neutrality), §9 (safe evolution),
§10 (greenfield/brownfield symmetry), §12 (trust boundaries, no fifth
authority), §13 (invariants 4, 6, 8, 9, 10).

## 9. Stop-condition review

| Stop condition | Verdict |
| --- | --- |
| Provider-specific semantics in SOS core | No — core sees only the neutral port (id, capabilities, execute); the stub providers are test-local |
| An execution path could bypass W9/W7/W8 gates | No — requests are unconstructible without the W9 reference; submit resolves, state-checks, and chain-checks; no-run terminals are typed |
| A contract element would duplicate an existing authority | No — every authority symbol is referenced by identity (test-asserted); the only cross-module helper (`_build_evidence`) is reused, not reimplemented |
| Evidence would be inferred rather than observed | No — receipts convert verbatim; capture-state and observed-state stay distinct in W4 |
