# W9 — Autonomy + ASK + Human Authority

**Status:** DISPATCHED — WORKER AUTHORIZED
**Dependencies:** W7 authoritative merge `25f663cf444f92b3190074a9119619cbc53e9ece`; W8 authoritative merge `65b84058aa204b3749e45b7e21ae433a4b138d83`
**Roadmap:** `spec/implementation-roadmap.md` — W9
**Primary requirements:** R13, R14, R16, R17, R18, R19, R21, R24

## Mission

Implement the autonomy/ASK decision boundary above the W7 assurance and W8 experiment/promotion lifecycle. W9 must make autonomy explicit, policy-governed, reversible, explainable, and subordinate to human authority. It MUST NOT invent evidence, bypass W7/W8 gates, execute platform actions, or redefine the frozen constitution.

## Governing authorities

The implementation MUST obey, without redefining them:

- `spec/architecture-lock.md` (frozen v1.0), especially autonomy, authorization, assurance, uncertainty, rollback, and governance invariants;
- `spec/requirements.md` R13/R14/R16/R17/R18/R19/R21/R24;
- `spec/implementation-roadmap.md` W9;
- `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` and `AGENTS.md`;
- W1 truth/traceability and mission/value/context authorities;
- W2 System State / Architecture Graph authority;
- W4 evidence authority;
- W5 causal knowledge authority;
- W6 candidate/objective authority;
- W7 non-authorizing AssuranceResult authority;
- W8 experimentation/promotion/rollback lifecycle authority.

Candidate/model reasoning remains untrusted. W9 MUST NOT turn model output, confidence, or narrative into truth, authorization, safety, completion, or causal proof.

## Required outcome

Create a deterministic W9 boundary that can represent and evaluate at minimum:

1. **Autonomy policy:** explicit bounded policy describing what actions may be considered, under what conditions, with scope, ceilings, uncertainty limits, reversibility requirements, and human-authority constraints.
2. **Decision boundary:** explicit states for `GATHER_EVIDENCE`, `EXPERIMENT`, `ACT`, `ASK`, `REJECT`, and `ROLLBACK`; no implicit action from candidate generation, assurance, or experiment completion.
3. **Human authority / ASK:** unresolved authority, value ambiguity, unsafe scope, or policy boundary MUST route to an explicit ASK request rather than inference or silent continuation.
4. **Pre-action gates:** ACT requires all required upstream evidence/assurance/promotion gates plus W9 policy authorization. W9 must never convert W7 PASS into generic authorization and must respect W8 promotion/rollback gates where applicable.
5. **Uncertainty handling:** UNKNOWN/FAILED/UNAVAILABLE/UNSUPPORTED truth states remain distinct and can force evidence gathering, ASK, experiment, rejection, or rollback according to policy; confidence alone cannot authorize action.
6. **Bounded actions:** action proposals are limited by explicit scope, resource/risk ceilings, blast-radius constraints, and reversibility/rollback conditions; no unbounded loops or hidden traversal.
7. **Explainability:** every decision/request records rationale, traceability, governing policy references, upstream assurance/experiment references, relevant evidence ids, and uncertainty/constraint outcomes without fabricating proof.
8. **Rollback and containment:** rollback remains an explicit governed action/state, preserving W8 recovery evidence and preventing silent downgrade of recovery guarantees.
9. **Determinism:** identical authoritative inputs produce identical decision/request states without network or provider dependency.
10. **Non-authority boundary:** no W10 personalization/platform adapters, W11/W12 realization, W13 self-evolution, or replacement of W7/W8 authority.

## Required decision semantics

W9 MUST distinguish:

- `ASK` from `ACT` — ASK means human authority or unresolved boundary is required and MUST NOT be silently inferred;
- `REJECT` from `UNKNOWN` — rejection is an explicit policy outcome, not a truth-state rewrite;
- `EXPERIMENT` from `ACT` — experiments remain bounded lifecycle operations governed by W8;
- `ROLLBACK` from failure narration — rollback eligibility/recovery must remain evidence/policy-backed;
- policy authorization from assurance — W7 assurance is non-authorizing and cannot be treated as an authorization token.

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an Architect-approved correction expands scope:

- `src/sos/autonomy.py`
- `src/sos/__init__.py` (W9 exports only)
- `tests/test_w9_autonomy.py`
- `docs/implementation/W9-AUTONOMY-ASK-DESIGN.md`
- `spec/development-state/W9-checkpoint.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order machinery, or W1–W8 source files.

## Explicit exclusions

W9 MUST NOT implement:

- provider-specific execution or platform adapters (W10);
- personalization/context adapters (W10);
- greenfield or brownfield realization loops (W11/W12);
- self-evolution/meta-adaptation (W13);
- a second evidence/cause/architecture authority;
- scalarized architecture quality as sole authority;
- LLM-derived proof or confidence-only authorization;
- mission/value/constitution revision authority;
- autonomous bypass of human authority or ASK;
- production deployment integrations.

## Acceptance criteria

### C1 — Explicit autonomy policy
Policy is structured, bounded, traceable, and cannot authorize beyond its declared scope/ceilings.

### C2 — Explicit action/request state machine
Valid transitions among GATHER_EVIDENCE, EXPERIMENT, ACT, ASK, REJECT, ROLLBACK are deterministic and invalid transitions are rejected.

### C3 — Human authority / ASK gate
Authority ambiguity, unsafe scope, or unresolved policy constraints route to ASK; no silent inference of user authorization.

### C4 — Assurance/promotion boundary
ACT and other executable outcomes require the appropriate upstream W7/W8 gates. W7 PASS remains non-authorizing; W8 promotion remains explicit.

### C5 — Truthful uncertainty gate
UNKNOWN/FAILED/UNAVAILABLE/UNSUPPORTED remain distinct; confidence does not substitute for evidence or authorization.

### C6 — Bounded action scope
Action candidates carry explicit scope, resource/risk ceilings, blast-radius bounds, and reversibility requirements; no hidden unbounded execution.

### C7 — Evidence and traceability chain
Decisions/ASK requests preserve exact evidence ids, revisions/provenance, policy refs, candidate/assurance/experiment refs, and W1 traceability.

### C8 — Rollback/containment integrity
Rollback decisions consume W8 governed recovery semantics and cannot claim successful recovery without required evidence/reference.

### C9 — Explainable decision record
Each decision has a deterministic rationale and explicit reasons for action, ASK, rejection, experiment, evidence gathering, or rollback.

### C10 — Deterministic bounded evaluation
Same authoritative inputs produce same outputs; no network/provider dependency required for deterministic tests.

### C11 — Persistence + traceability
W9 records round-trip through the existing W1 persistence mechanism without introducing another authority.

### C12 — Bounded authority surface
W9 owns autonomy/ASK decision semantics only and introduces no W10+ symbols or duplicate W7/W8 authority.

## Required regression coverage

Tests MUST include, at minimum: policy scope/ceiling enforcement; invalid transition rejection; explicit ASK for unresolved human authority; rejection of confidence-only authorization; non-PASS assurance cannot ACT; W8 promotion requirement where an experiment is involved; unknown/failed/unavailable/unsupported truth states cannot silently become authorization; bounded blast radius; evidence/provenance traceability; rollback/recovery integrity; deterministic decisions; JSON round-trip; and absence of W10+ authority/platform symbols.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

## Risk / rollback

Risk is semantic and high because W9 introduces the autonomy boundary before platform realization. The implementation must remain explicit, bounded, reversible, human-authority preserving, deterministic, and provider-neutral. Git revert of the merged W9 change is the repository rollback mechanism.

## Completion protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and verification evidence;
2. run the deterministic verification commands;
3. leave Worker state at `WAITING_FOR_ARCHITECT`;
4. stop without merging and without creating W10;
5. await Architect review. Corrections stay on the same PR.
