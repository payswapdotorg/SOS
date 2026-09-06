# W10 — Contextual Personalization + Platform Adapters

**Status:** DISPATCHED — WORKER AUTHORIZED
**Dependencies:** W2 authoritative merge `587201d3e12a10ba9fac6da751d663a40c33dfb9`; W9 authoritative merge `203cfb7590bd25244cabf3cc7299dd192b00948d`
**Roadmap:** `spec/implementation-roadmap.md` — W10
**Primary requirements:** R5, R15, R16, R17, R18, R22, R23, R24
**Base for Worker branch:** live `main` after W9 merge

## Mission

Implement the W10 boundary for contextual personalization and platform-neutral adapter contracts. W10 MUST use authoritative W1 context/mission/value material, W2 System State/architecture representations, W9 autonomy/ASK policy, and W4 evidence where referenced. It MUST preserve global mission, safety, legal/fairness/business constraints and human authority while allowing context-conditioned policy selection across supported platforms.

W10 is a policy/adaptation boundary, not a deployment or realization engine. It MUST NOT execute external platform actions, invent user authority, bypass W9 ASK/ACT gates, create a second evidence authority, or make platform-specific implementation details into semantic authorities.

## Governing authorities

The implementation MUST obey, without redefining them:

- `spec/architecture-lock.md` frozen architecture and authority rules;
- `spec/requirements.md` R5/R15/R16/R17/R18/R22/R23/R24;
- `spec/implementation-roadmap.md` W10;
- `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` and `AGENTS.md`;
- W1 mission/value/context authorities;
- W2 System State / Architecture Graph authority;
- W4 evidence authority;
- W7 non-authorizing assurance authority;
- W8 experimentation/promotion/rollback authority;
- W9 autonomy/ASK/human-authority boundary.

Model-generated personalization recommendations remain proposals. They MUST NOT become truth, authority, safety, legal compliance, fairness compliance, or promotion evidence merely because a model produced them.

## Required outcomes

1. **Context-conditioned policy:** represent explicit context dimensions relevant to policy selection, including user/cohort, device/platform, environment, time/workload and other context already authorized by W1. Context MUST be traceable and versionable and MUST NOT rewrite mission/value authorities.
2. **Personalization policy selection:** select or evaluate bounded policies/candidates against context while preserving global constraints. The mechanism MUST support context-conditioned preferences without requiring a single global scalar architecture score.
3. **Human authority preservation:** W10 MUST consume W9 authority outcomes. Context may narrow or choose among already-authorized options, but MUST NOT expand `allowed_actions`, risk ceilings, blast-radius ceilings, reversibility requirements, ASK rules, or human-approval requirements.
4. **Platform-neutral adapter contract:** define a common adapter boundary for web, mobile, desktop, TV, cross-platform and future supported surfaces. Adapter metadata MAY describe capabilities and constraints, but platform-specific metadata MUST NOT become semantic authority.
5. **No live execution:** adapters in W10 are contract/policy interfaces only. They may validate capability/compatibility and produce bounded action plans/requests, but MUST NOT deploy, mutate production systems, click user interfaces, or invoke external side effects.
6. **Explainability:** consequential personalization/adapter decisions MUST preserve context references, policy references, W9 decision/authority references, relevant evidence identifiers, constraints, alternatives and uncertainty.
7. **Uncertainty and missing context:** unknown/unavailable/unsupported context MUST remain distinct and MUST NOT silently collapse to a favorable value. Ambiguous or authority-relevant context MUST route to ASK or another explicit non-authorization outcome according to W9 policy.
8. **Determinism:** identical authoritative inputs produce identical policy-selection and adapter-validation results without network/provider dependence.
9. **Bounded extensibility:** new platform adapters can be added without modifying frozen mission/value/autonomy authorities. No W11/W12/W13 implementation belongs in this Work Order.

## Required semantic distinctions

W10 MUST distinguish:

- personalization preference from mission authority;
- context evidence from inferred identity/authorization;
- adapter capability from semantic correctness;
- policy selection from action authorization;
- ASK/REJECT from defaulting on missing context;
- platform-specific constraints from global safety/legal/fairness/business constraints;
- compatibility validation from actual execution.

## Allowed implementation surface

Worker MUST limit implementation to these six files unless an Architect-approved correction expands scope:

- `src/sos/personalization.py`
- `src/sos/platform.py`
- `src/sos/__init__.py` (W10 exports only)
- `tests/test_w10_personalization_platform.py`
- `docs/implementation/W10-PERSONALIZATION-PLATFORM-DESIGN.md`
- `spec/development-state/W10-checkpoint.md`

Do not modify frozen authority artifacts, roadmap semantics, Work Order machinery, or W1–W9 source files.

## Explicit exclusions

W10 MUST NOT implement:

- production deployment or external side effects;
- greenfield realization loops (W11);
- brownfield optimization loops (W12);
- SOS self-evolution/meta-adaptation (W13);
- browser/UI automation;
- a second mission, value, context, evidence, assurance, experiment, rollback, or autonomy authority;
- context-based privilege escalation or silent human-approval inference;
- platform-specific implementation as semantic authority;
- LLM/model output as authorization, safety, truth, or evidence;
- mutable global personalization state that bypasses W1/W9 governance.

## Acceptance criteria

### C1 — Explicit contextual model
Context dimensions and values are typed/structured, versioned, traceable, and distinguish known/unknown/unavailable/unsupported values.

### C2 — Bounded personalization
Personalization can select among declared policy/candidate alternatives using context while preserving global mission/value/safety/business constraints and without creating a scalar sole authority.

### C3 — W9 authority inheritance
A contextual policy MUST NOT exceed its source W9 `AutonomyRequest` or decision boundary. It cannot add allowed actions, relax ceilings, waive human approval, or turn ASK/REJECT into ACT.

### C4 — Human authority / ASK
Authority-relevant context ambiguity, missing authorization, or unresolved policy boundaries remain explicit and lead to ASK/non-authorization outcomes rather than silent defaults.

### C5 — Platform-neutral adapter interface
Adapters expose stable capability/compatibility contracts, platform identity metadata, bounded action descriptions and traceability without embedding semantic authority in any platform implementation.

### C6 — No execution
Adapter validation/building is side-effect free and deterministic. There is no deployment, network call, browser automation, or external platform mutation.

### C7 — Constraint preservation
Global mission/value/safety/legal/fairness/business constraints are preserved across personalization and platform adaptation; platform constraints may further narrow options but not weaken global constraints.

### C8 — Explainability and evidence
Consequential decisions preserve context refs, source policy/W9 refs, alternatives, constraints, uncertainty and relevant evidence/provenance identifiers.

### C9 — Deterministic evaluation
Same authoritative inputs yield same outputs; unknown/missing context does not produce optimistic authorization.

### C10 — Persistence / traceability
W10 records round-trip through the existing W1 JSON persistence mechanism or another explicitly existing repository authority; no new persistence authority.

### C11 — Bounded authority surface
No W11/W12/W13 symbols, no execution/deployment authority, and no duplicate W1/W4/W7/W8/W9 semantic authorities.

### C12 — Extension contract
A new adapter can implement the common contract without changing global semantic authorities. Invalid/incompatible adapter capability data is rejected deterministically.

## Required regression coverage

Tests MUST include, at minimum: structured context and truth-state distinctions; context-conditioned policy selection; preservation of global constraints; W9 authority ceiling inheritance; refusal to expand allowed actions; ASK on unresolved authority/missing context; platform adapter capability validation; platform neutrality; side-effect-free adapter planning/validation; deterministic results; JSON round-trip; explainability/evidence traceability; invalid adapter data rejection; and absence of W11/W12/W13/execution symbols.

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
```

No network/provider dependency may be required for the deterministic acceptance suite.

## Evaluation / real-system evidence

Because W10 explicitly excludes live execution, the required evidence is contract/evaluation evidence rather than deployment evidence. Tests MUST demonstrate that platform adapters are pure validation/planning boundaries and that W9 authorization is preserved. Any real platform metadata used in tests MUST be fixture data with explicit provenance, not asserted as live truth.

## Risk / rollback

**Risk:** high semantic risk because contextualization can accidentally weaken global policy or human authority. The design must be monotonic with respect to global constraints: personalization and platform constraints may narrow an already-authorized option set, never widen it.

**Rollback:** ordinary Git revert of the merged W10 change. No deployment, network side effect, or data migration is permitted in W10.

## Completion / reconciliation protocol

When implementation is complete, the Worker MUST:

1. checkpoint exact base/head SHAs and verification evidence;
2. report the exact pytest and compileall results;
3. remain at `WAITING_FOR_ARCHITECT`;
4. stop without merging, without dispatching W11, and without modifying canonical state;
5. await Architect review. Corrections stay on the same PR.

W10 completion requires the Architect gate, actual Git merge, and canonical reconciliation recording the W10 merge and next frontier.