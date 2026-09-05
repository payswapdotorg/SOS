# SOS Implementation Roadmap

**Status:** FROZEN — AUTHORITATIVE IMPLEMENTATION SEQUENCE v1.0
**Purpose:** Human-readable sequencing, progress and recovery authority for the SOS product program.

This roadmap adapts the implementation discipline proven in WorkflowOS while replacing WorkflowOS product semantics with SOS semantics. It is the sequencing authority; it never overrides the frozen SOS architecture, Work Orders, actual Git history, or required evidence.

## Zero-history rule

A fresh Architect or worker must be able to determine what to implement next from repository state alone:

`live main → this roadmap → development state → selected Work Order → dependency merge evidence → current implementation → exact verification/evidence → frontier`

Conversation history and agent memory are never hidden prerequisites.

## Program structure

```text
W0  Governance + constitution
 ↓
W1  Mission / value / context model
 ↓
W2  System-state + architecture graph
 ↓
W3  Existing-system recovery
 ↓
W4  Evidence + observability fabric
 ↓
W5  Causal knowledge + architecture memory
 ↓
W6  Candidate generation + bounded search
 ↓
W7  Assurance + impact analysis
 ↓
W8  Experimentation + promotion/rollback
 ↓
W9  Autonomy + ASK + authority controls
 ↓
W10 Personalization/contextual policies + platform adapters
 ↓
W11 Greenfield system realization
 ↓
W12 Brownfield optimization loop
 ↓
W13 SOS self-evolution / meta-adaptation
 ↓
W14 Integrated dogfood + adversarial verification
 ↓
W15 Final Architect gate
```

## Frozen task ledger

| Work Order | Task | Dependencies | Outcome |
|---|---|---|---|
| W0 | Governance foundation | none | repository authority, constitution, Work Order machinery, evidence conventions |
| W1 | Mission/value/context model | W0 | collaborative mission formalization, versioning, value model, context model |
| W2 | System State + architecture graph | W1 | typed/versioned system and architecture representation |
| W3 | Architecture recovery | W2 | brownfield ingestion/recovery with uncertainty |
| W4 | Evidence fabric | W2 | runtime/repo/environment evidence graph and telemetry adapters |
| W5 | Causal knowledge + memory | W4 | intervention hypotheses, causal evidence and architecture memory |
| W6 | Candidate/search engine | W3 + W5 | bounded subgraph mutation/search, Pareto candidate ranking |
| W7 | Assurance engine | W6 | static/tests/replay/simulation/impact/risk gates |
| W8 | Experiment/promotion plane | W7 | shadow/canary/controlled experiment/rollback lifecycle |
| W9 | Autonomy/ASK | W7 + W8 | calibrated decision policy and user authority controls |
| W10 | Contextual personalization + platform adapters | W2 + W9 | user/context-conditioned experience/execution policies across platforms |
| W11 | Greenfield realization | W1 + W2 + W9 | mission-only onboarding to initial realizable system |
| W12 | Brownfield optimization loop | W3 + W4 + W5 + W6 + W7 + W8 + W9 | production evolution from existing software |
| W13 | SOS self-evolution | W8 + W9 | SOS evolves its own implementation and adaptation mechanisms safely |
| W14 | Full dogfood/adversarial verification | W10–W13 | end-to-end evidence over representative systems and failure modes |
| W15 | Architect gate | W14 | final review, merge and canonical reconciliation |

## Work Order execution template

Every Work Order MUST define:

- mission/requirement traceability;
- exact scope and explicit exclusions;
- dependencies and proof of their authoritative merges;
- architecture authorities touched;
- permitted repository paths;
- forbidden authority surfaces;
- behavioral acceptance criteria;
- deterministic verification;
- real-system/evaluation or browser evidence where applicable;
- expected risk and rollback needs;
- required persisted evidence;
- completion and reconciliation criteria.

## Task-entry contract

For every task:

1. read the current live `main` SHA;
2. verify eligible dependencies from Git merge facts;
3. read the Work Order and governing architecture/requirements;
4. inspect current implementation;
5. write failing tests for new behavioral invariants where practical;
6. implement one bounded slice;
7. run exact-head verification;
8. persist evidence;
9. open/update the task PR;
10. stop at `WAITING_FOR_ARCHITECT` when review-ready.

## Review-ready lifecycle

```text
DISPATCH_AUTHORIZED
 → WORKER_ACTIVE
 → CHECKPOINTED
 → WAITING_FOR_ARCHITECT
 → CHANGES_REQUESTED → WORKER_ACTIVE → CHECKPOINTED → WAITING_FOR_ARCHITECT
 → APPROVED
 → MERGING
 → MERGED
 → RECONCILING
 → COMPLETE
```

## Frozen sequencing rule

No Work Order may be declared eligible because a branch exists, an agent says it is ready, or an unmerged sibling contains a dependency. Eligibility requires authoritative merged Git evidence for declared dependencies.

## Completion rule

A Work Order is complete only after its governing Architect gate passes, the actual Git merge exists, and canonical state records that merge and the resulting frontier.

## Final integrated gate

W14 MUST verify at minimum:

- mission formalization and revision;
- value-model constraints;
- context and personalization boundaries;
- system/architecture graph reconstruction;
- evidence truthfulness;
- causal hypothesis/evidence distinction;
- candidate subgraph replacement;
- multi-objective trade-offs;
- assurance and rollback;
- ASK/autonomy policy;
- platform adapters;
- greenfield and brownfield paths;
- SOS self-evolution with meta-adaptation boundary;
- full exact-revision traceability.
