# SOS Implementation Process

**Status:** FROZEN OPERATING PROCESS v1.0

This process is adapted from the repository-governance and resident-worker discipline used in `pectoraux/WorkflowOS`. It preserves the process mechanics while replacing all WorkflowOS-specific product semantics with SOS mission/system-state evolution semantics.

## 1. Authority hierarchy

When artifacts disagree, prefer:

1. actual Git history and live `main`;
2. canonical development-state artifacts;
3. frozen SOS architecture and architecture lock;
4. governing Work Order;
5. frozen implementation roadmap;
6. approved detailed design/implementation plan;
7. actual implementation, tests, CI and persisted evaluation evidence;
8. PR descriptions/comments and agent summaries only as navigation/evidence aids.

## 2. Fresh-agent bootstrap

Before changing code a fresh worker MUST:

1. read `AGENTS.md`;
2. read `ARCHITECT_START_HERE.md`;
3. read `spec/architecture.md`, `spec/architecture-lock.md`, `spec/requirements.md`;
4. read `spec/implementation-roadmap.md` and canonical development state;
5. inspect live `main` and open/merged PRs;
6. compute task eligibility from repository state;
7. verify every dependency by actual Git merge evidence;
8. read the selected Work Order and relevant contracts;
9. inspect the real implementation before trusting prior reports.

If authority is contradictory, stop and reconcile; do not guess.

## 3. One-slice rule

One bounded Work Order is implemented on one branch/PR. Unmerged sibling work is never a dependency. Integration work may combine slices only when the roadmap explicitly defines an integration gate.

## 4. Durable dispatch

Before implementation, the Architect/operator records on the task PR/issue or an adjacent durable artifact:

- repository identity;
- Work Order identity;
- exact base SHA;
- completed dependency merge identities;
- mission/requirement traceability;
- architecture authorities in scope;
- allowed implementation surface;
- forbidden authority surface;
- acceptance criteria;
- deterministic verification commands;
- real-system/evaluation requirements;
- rollback/risk requirements;
- one-PR requirement;
- explicit prohibitions on merge, self-approval, authority mutation and successor work.

The worker must re-verify these facts from repository/GitHub state before modifying code.

## 5. Implementation loop

For each Work Order:

```text
ELIGIBLE
  ↓
ARCHITECT DISPATCH
  ↓
WORKER ACTIVE
  ↓
READ AUTHORITY + CODE
  ↓
FAILING TEST (when behavior changes)
  ↓
RED → GREEN → REFACTOR
  ↓
DETERMINISTIC VERIFICATION
  ↓
REAL-SYSTEM / BROWSER / EVALUATION EVIDENCE
  ↓
SCOPE + AUTHORITY REVIEW
  ↓
DURABLE CHECKPOINT
  ↓
WAITING_FOR_ARCHITECT
```

Workers must use append-only history and preserve exact revisions. A checkpoint is not completion.

## 6. Architect review loop

For each PR:

1. verify actual base SHA against live `main` and Work Order;
2. verify exact submitted head SHA;
3. inspect actual diff, not PR prose;
4. map consequential concepts to their owning SOS authority;
5. detect duplicated semantic, evidence, execution, experiment or governance authorities;
6. check Mission/Value/Context/System-State traceability;
7. check unknown/failed/unavailable truthfulness;
8. check candidate-risk-assurance and rollback behavior;
9. check contextual personalization against global mission and hard constraints;
10. check exact-head tests and real-system/evaluation evidence;
11. approve or return stable findings tied to concrete evidence;
12. do not merge until the governing gate is satisfied;
13. merge only the reviewed head;
14. reconcile canonical state from actual Git evidence;
15. recompute the eligible frontier.

## 7. REQUEST_CHANGES protocol

Every correction packet MUST identify:

```yaml
work_item: W?
pr: <number>
head_sha: <exact reviewed head>
base_sha: <intended base>
iteration: <integer>
decision: REQUEST_CHANGES
findings:
  - id: SOS-W?-F01
    severity: HIGH
    path: <repository path>
    criterion: <acceptance criterion>
    required_change: <specific action>
```

Finding IDs persist until resolved. Corrections remain on the same PR.

## 8. Resident worker waiting

A review-ready worker enters `WAITING_FOR_ARCHITECT` rather than terminating its governed task. A session is disposable; the durable task identity is Work Order + branch + PR + exact base SHA + latest head SHA.

A replacement session resumes from repository/GitHub state and the same PR. It never creates a replacement PR merely because a session ended.

## 9. Watchdog states

Use:

- `ACTIVE_PROGRESS` — durable progress exists;
- `WAITING_FOR_ARCHITECT` — review-ready and no new finding;
- `WAITING_FOR_CAPACITY` — execution capacity is unavailable;
- `STALE_BASE` — the task base no longer satisfies its contract;
- `SUSPECTED_HANG` — no durable progress and activity cannot be confirmed;
- `ESCALATE` — authority, identity or repository state is contradictory.

Silence alone is not proof of hang. Automatic restarts are bounded; repeated identical failures escalate.

## 10. Evidence contract

Accepted task evidence records:

- Work Order identity;
- exact base SHA;
- exact head SHA;
- PR identity;
- verification commands/results;
- test and static-analysis results;
- real-system/browser/evaluation results where required;
- mission outcome or proxy outcome where applicable;
- known limitations and external blockers;
- risk and rollback state.

Never treat stale-head verification as evidence for a corrected head.

## 11. Completion boundary

A worker may declare `review-ready`, not complete.

A task is complete only when:

`Architect gate passed → actual Git merge exists → canonical state reconciled`

Reconciliation is bookkeeping and cannot approve or widen scope.

## 12. Change authority boundary

Ordinary implementation must stop and raise an Architecture Change Request when it would change a frozen invariant, mission authority, value-model semantics, system-state semantics, evidence semantics, assurance boundary, autonomy model, experiment semantics, or platform-neutral core semantics.

## 13. Self-evolution process

When implementing SOS itself as an evolutionary subject, the same process applies recursively. The subject may be SOS's own architecture, planner, evaluator, memory, adapters or implementation. The Constitution and assurance boundary remain outside autonomous mutation.

A self-evolution Work Order must explicitly identify the SOS subsystem being evolved, the mission-level outcome it serves, the meta-hypothesis, validation evidence, rollback mechanism and the proof that the change cannot disable the governance loop judging it.

## 14. Zero-history handoff invariant

At every task boundary, repository state must answer:

- what mission/product requirement is being advanced;
- what architecture governs;
- what Work Order is active;
- what dependencies are merged;
- what exact base/head are authoritative;
- what changed and why;
- what verification ran;
- what evidence remains uncertain;
- what the Architect decided;
- what can be implemented next.
