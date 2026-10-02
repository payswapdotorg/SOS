# SOS Public Deployment — Worker Dispatch Model

**Status:** ACTIVE — dispatch authority artifact (Public Deployment Overlay)
**Contract:** `spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md` (per-item work orders §D)
**Model:** the operator directive §16 three-worker model, run under the house
discipline proven in W1–W15 (`docs/implementation/TL-3-WORKER-COORDINATION.md`,
`spec/development-state/WORKER-DISPATCH.md`).

## Worker lanes

- **Worker A — control plane + infrastructure:** PUB-01 (FastAPI adapter +
  G09 reconciliation + LOCAL adapters + schemas), PUB-05 (Neon persistence),
  PUB-06 (Upstash jobs/coordination). Never executes arbitrary user repository
  code (directive §16-A).
- **Worker B — web product:** PUB-02 (Next.js cockpit, fixture-first),
  PUB-04 (GitHub auth + tenancy). Never implements SOS decision rules in the
  client (directive §16-B).
- **Worker C — providers + deployment:** PUB-03 (free-tier infra + CI + runbooks),
  PUB-07 (R2 evidence/artifact layer), PUB-08 (Apify bounded execution provider
  + adversarial provider-isolation tests, directive §16-C).
- **TL/Architect:** PUB-00 (done), PUB-09 coordination (journey integration),
  PUB-10 oversight, PUB-11/12 deployment execution (operator credentials),
  PUB-13 final gate. The TL never writes application code; it authors contracts,
  dispatches, verifies, merges, reconciles.

## Wave plan

```text
Wave 1 (parallel, after PUB-00 merges):  PUB-01 (A)  |  PUB-02 (B)  |  PUB-03 (C)
Wave 2:                                  PUB-04 (B)  |  PUB-05 (A)  |  PUB-07 (C)
Wave 3:                                  PUB-06 (A)  |  PUB-08 (C, needs 06+07)
Wave 4:                                  PUB-09 (A+B+C contributions, TL-coordinated)
Wave 5:                                  PUB-10 (C + independent adversarial review)
Wave 6:                                  PUB-11 → PUB-12 (deployment stages)
Wave 7:                                  PUB-13 (final Architect gate)
```

No worker treats an unmerged sibling branch as a dependency (house rule). PUB-02
builds against the CONTRACT schemas + fixtures, NOT against PUB-01's branch.

## Dispatch protocol (per item)

1. TL records the dispatch packet in the session registry: repository identity,
   work item identity (PUB-XX), exact base SHA (live merged main), dependency
   merge evidence, the contract §D item as the work order, verification commands
   (§G matrix), one-PR rule, prohibitions (no merge, no self-approval, no
   successor work, no frozen-surface edits), anti-fabrication rules (§F).
2. Worker session created (agents tab discipline; model/skill per platform
   directive). The packet embeds the full binding contract text so the worker
   has zero conversation-history dependencies (zero-history rule).
3. Worker: bootstrap per `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` §2
   (read AGENTS.md → ARCHITECT_START_HERE.md → frozen architecture/lock →
   contract §A/§D item → live main → dependency evidence), then implement on
   branch `work/pub-XX-<slug>` from the recorded base.
4. Worker runs the §G matrix at its exact head, writes the checkpoint
   (`spec/development-state/PUB-XX-checkpoint.md`), pushes the branch, enters
   `WAITING_FOR_ARCHITECT`, and reports with the exact head SHA.
5. TL: remote-ref truth gate (fetch the exact ref — a completion claim without
   a fetchable remote ref at that SHA is void), fresh re-run of the §G matrix
   at the exact head, diff review against the contract §D surface.
6. Review verdict: APPROVE (merge the reviewed head only, COMMENT-form review
   record on the PR per the W12+ self-approval-protection precedent, then
   reconcile `public-deployment-state.json` with the merge SHA and recompute
   the frontier) or REQUEST_CHANGES (stable findings, IDs `PUB-XX-F##`,
   severity, path, criterion, required change; corrections stay on the same PR).

## Worker reporting (checkpoint format — every item)

- Work item identifier + branch + PR;
- exact base SHA and exact head SHA;
- files/artifacts changed (must equal the contract §D allowed surface);
- requirement/directive traceability;
- verification commands + results (§G matrix, run at the exact head);
- unresolved findings, known limitations, external blockers (credentials,
  capacity) — truthful `WAITING_FOR_CAPACITY` / blocked states are legitimate;
- explicit statement: no unmerged sibling is a dependency; no frozen surface
  touched; no merge performed.

## Watchdog states

`ACTIVE_PROGRESS`, `WAITING_FOR_ARCHITECT`, `WAITING_FOR_CAPACITY`,
`STALE_BASE`, `SUSPECTED_HANG`, `ESCALATE` (house process §9). Silence alone is
not proof of hang; bounded restarts; repeated identical failures escalate to
the TL → operator.

## TL responsibilities

1. Keep every worker on its contracted lane; prevent scope creep into frozen
   surfaces or siblings' lanes.
2. Independently verify every review-ready head (never trust reported numbers).
3. Merge only after the review gate passes; merge only the reviewed head.
4. Reconcile canonical state from actual Git facts after every merge; record
   merge SHAs in `public-deployment-state.json`.
5. Keep the frozen W0–W15 gate green at every merge (overlay-scoped G09).
6. Report progress to the operator through the standing resident-watch loop
   (monitor → harvest → review → approve/require-changes → dispatch next).
