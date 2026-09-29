# W15 — Final Architect Gate (repository-level reconciliation and evidence gate)

**Status:** PREPARED — DISPATCH BLOCKED (W14 is not merged; W15 is the terminal wave of the frozen roadmap — there is no W16)
**Dependencies:** W14 authoritative merge (REQUIRED — none exists at preparation; W14 itself is blocked on W12/W13 merges). Transitively: the complete merged W0–W14 chain (W1 `091d4d10a38922fb2d9cadb103e7ba8caa7a1f20` … W11 `aae251813d31f5b85e005d4bff94462a84c440df`, plus the W12/W13/W14 merge SHAs as they become authoritative). The dispatching Architect MUST re-verify the W14 merge from actual Git history immediately before dispatch and record it in the dispatch envelope.
**Roadmap:** `spec/implementation-roadmap.md` — W15 (Architect gate — "final review, merge and canonical reconciliation")
**Primary requirements:** R9, R13, R14, R21, R22, R23, R24 (R1–R20 are verified transitively through the W14 integrated-gate evidence that W15 reconciles; R24 — repository-governed implementation recoverable by a fresh agent without conversation history — is the dominant requirement of this Work Order)
**Base for Worker branch:** live `main` AFTER the W14 merge (exact base SHA recorded at dispatch; re-read from live `main` at dispatch — the preparation-time live main `e3a97b895ca7f6cc7206a50bde45b2b55c554195` is NOT the dispatch base)

## Mission

Execute the final repository-level reconciliation and evidence gate for the
SOS-v1 program. W15 is a **verification/reconciliation Work Order, NOT a new
product subsystem**: it establishes a MACHINE-CHECKABLE checklist that
validates, at the final head, that the completed repository is internally
consistent, conforms to the frozen architecture, and is fully recoverable by
a fresh agent under the zero-history rule (roadmap: "a fresh Architect or
worker must be able to determine what to implement next from repository
state alone").

W15's gate semantics extend `docs/implementation/ARCHITECT-REVIEW-PROTOCOL.md`
(review sequence, hard stops), `docs/implementation/SOS-IMPLEMENTATION-PROCESS.md`
(§14 zero-history handoff invariant, §11 completion boundary), and
`docs/implementation/TL-FINAL-HANDOFF.md` (review discipline: "never use chat
history as state; never treat CI green as semantic approval"). The gate
mechanizes those rules; it never replaces the Architect's judgment —
reconciliation records facts and cannot approve work (architecture-lock
"Implementation governance").

The gate MUST verify:

- (a) the implementation conforms to the frozen architecture (the four
  authority classes, the per-wave module surface, no fifth authority, no
  unmapped subsystem);
- (b) the repository is recoverable by a fresh agent (zero-history rule);
- (c) every Work Order's completion lifecycle evidence exists (merge SHAs,
  checkpoints, verification evidence);
- (d) `implementation-state.json` reconciles with actual Git history;
- (e) rollback safety is demonstrable for every merged authority.

### Machine-checkable checklist coverage (binding)

The checklist MUST cover, with machine-checkable items (or explicitly
marked review-time items where offline repo state cannot decide them):
architecture; requirements; roadmap; implementation state; dependency
ancestry; tests; adversarial evidence; exact revisions; rollback safety;
documentation; final sign-off. The precise check definitions (G01–G12), the
script design, and the reconciliation rules are specified in
`docs/implementation/W15-FINAL-GATE-DESIGN.md` — that design is the
authoritative specification a future Worker implements mechanically.

### Final sign-off protocol (binding)

- **Who signs:** the governing Architect. If the operator delegates, the TL
  may sign under the recorded operator-delegation precedent (W10/W11
  gate self-approval, each recorded as evidence) — the delegation MUST be
  recorded in the sign-off record.
- **Required evidence packet:** (1) the final gate report
  `spec/development-state/W15-gate-report.json` with every check PASS at the
  exact final head; (2) exact-head `python -m pytest` and
  `python -m compileall -q src tests` outputs and counts; (3) the W14
  adversarial-evidence matrix (all sixteen case verdicts PASS); (4) the
  complete W1–W15 checkpoint chain (presence + currency per G08); (5) the
  per-wave rollback-safety declarations (G09); (6) the fresh-agent recovery
  walkthrough record — a reviewer who did not author the program artifacts
  performs the `ARCHITECT_START_HERE.md` bootstrap and states the frontier
  from repository state alone, recorded in the sign-off record; (7) the
  sign-off record itself, `spec/development-state/W15-final-sign-off.md`
  (Architect-authored at approval — outside the Worker's allowed surface),
  containing: signer identity and authority basis, exact final head SHA,
  references to items 1–6, the checklist verdict table, residual
  limitations, and date.
- **How the completed roadmap is recorded:** AFTER Architect approval and
  the W15 PR merge, a final reconciliation commit (Architect/TL authority,
  the same reconciliation discipline used after every prior merge) records
  program completion in canonical state WITHOUT touching any frozen
  document: `spec/development-state/implementation-state.json` → overall
  `status: "ROADMAP_COMPLETE"`, W15 task `status: "COMPLETE"` with its
  `mergedAs` merge SHA, `currentFrontier: []`, `currentTask: null`, plus a
  note recording the final gate; `spec/development-state/current-state.md`
  updated to the final projection (program complete, final head SHA,
  recovery path unchanged). The frozen roadmap, architecture, architecture
  lock, constitution, and requirements stay byte-identical v1.0 — completion
  is recorded in canonical state, never by rewriting frozen semantics.

## Required outcomes

1. **Gate script (scope specified here; implemented by the Worker):**
   `tools/final_gate_check.py` — offline, read-only (apart from writing its
   own report), deterministic, stdlib-only; implements checks G01–G12 per
   the design doc; exit code 0 iff every check passes; emits the JSON
   report `spec/development-state/W15-gate-report.json`.
2. **Git-vs-state reconciliation (G04/G05):** for every task W1–W14 with
   status COMPLETE: `mergedAs` resolves in the repository, is reachable
   from the final head, is unique across tasks, and the wave's
   checkpoint-recorded implementation head is an ancestor-or-equal of its
   merge (W0's `bootstrapCommit` is the recorded exception); and for every
   task, each declared dependency's merge is an ancestor of the task's
   merge (frozen sequencing rule, mechanically proven).
3. **Roadmap/requirements/architecture reconciliation (G01–G03):** the five
   frozen authority documents exist at their frozen v1.0 content (digests
   recorded in the gate baseline and Architect-verified at review);
   `src/sos/` contains exactly the per-wave module surface recorded in the
   gate baseline (no fifth authority, no unmapped module, none missing);
   every roadmap ledger row W0–W14 has a COMPLETE task with a merge; the
   implementation-state task set equals the roadmap task set; every
   requirement R1–R24 appears in at least one Work Order's primary
   requirements and in the W14 verification mapping.
4. **Tests green at the final head (G06):** `python -m pytest` exit 0 with
   the exact count recorded (count ≥ the W14 checkpoint count —
   extend-never-weaken); `python -m compileall -q src tests` exit 0.
5. **Adversarial-evidence verification (G07):** the W14 matrix exists,
   parses, contains all sixteen frozen case names, every verdict PASS, and
   its recorded `repoHead` is an ancestor of the final head.
6. **Checkpoint/exact-revision currency (G08):** `W?-checkpoint.md` exists
   for every wave W1–W15; each records exact base/head; each recorded head
   is reachable from the final head (or documented per
   ARCHITECT-REVIEW-PROTOCOL §2 as the PR head reference).
7. **Rollback safety (G09):** every wave's checkpoint carries its rollback
   declaration; no merged wave introduced deployment/migration/network
   state beyond its frozen surface (module-map + suite-green enforce).
8. **Documentation reconciliation (G10):** `current-state.md` matches live
   main (its recorded live-main SHA equals actual HEAD; its
   last-completed/frontier fields equal the canonical machine state); every
   wave W1–W15 has its Work Order file and design doc.
9. **Fresh-agent recoverability (G11):** the mechanical recovery chain is
   complete and contradiction-free (bootstrap artifacts exist; G01–G10
   pass); the human zero-history walkthrough is executed and recorded at
   review (see sign-off packet item 6).
10. **Sign-off packet and final reconciliation:** the Worker assembles the
    packet items it owns (1–5); the sign-off record and the
    ROADMAP_COMPLETE reconciliation are performed under Architect authority
    after merge, per the protocol above. The Worker NEVER writes
    `ROADMAP_COMPLETE`, never merges, and never modifies canonical state.

## Allowed implementation surface

Worker MUST limit implementation to these five files unless an
Architect-approved correction expands scope:

- `tools/final_gate_check.py` (new directory `tools/` is created by this
  Work Order; the script is a repository tool, not SOS product code — it
  must not be imported by `src/sos/` or add `sos` exports)
- `tests/test_w15_final_gate_check.py`
- `spec/development-state/W15-gate-report.json` (generated by the script at
  the exact head; committed as evidence)
- `spec/development-state/W15-checkpoint.md`
- `docs/implementation/W15-FINAL-GATE-DESIGN.md`

The Architect-side sign-off artifact
(`spec/development-state/W15-final-sign-off.md`) and the post-merge
canonical-state updates (`implementation-state.json` → ROADMAP_COMPLETE;
`current-state.md` final projection) are created under Architect authority
during approval/reconciliation — they are NOT part of the Worker's branch.

Do not modify frozen authority artifacts, roadmap semantics, Work Order
machinery, any `src/sos/` file, any existing test file, or any W1–W14
checkpoint/design/Work Order document.

## Explicit exclusions

W15 (this slice) MUST NOT:

- **invent any new architecture** — no new authority classes, no new
  subsystems, no new product semantics, no new ports, no changes to the
  frozen architecture/lock/constitution/requirements/roadmap; any
  architectural concern surfaced by the gate escalates as a finding or an
  Architecture Change Request under `spec/architecture-change-process.md`,
  never an in-PR semantic change;
- modify `src/sos/` or add `sos` exports (the gate script lives in
  `tools/`, outside the product);
- modify or re-run-to-green any W1–W14 test (extend-never-weaken; a red
  suite at the final head is a finding, not something the gate fixes);
- write `ROADMAP_COMPLETE`, merge its own PR, dispatch any successor
  (there is no W16), or modify canonical state;
- require network access, GitHub API calls, or credentials (open-PR state
  and PR-identity reconciliation are review-time Architect checks, not
  script checks; the script reads only the local repository);
- treat a passing script as approval (the gate is mechanical evidence; only
  the Architect's sign-off completes the roadmap — process §11);
- use conversation history as state (zero-history rule).

## Acceptance criteria

### C1 — Checklist completeness
All eleven mandated coverage areas (architecture; requirements; roadmap;
implementation state; dependency ancestry; tests; adversarial evidence;
exact revisions; rollback safety; documentation; final sign-off) are
covered by machine-checkable checks G01–G12, with any non-mechanical item
explicitly marked review-time and named in the sign-off protocol.

### C2 — Offline, read-only, deterministic gate
The script runs without network, mutates nothing except its own report
file, and produces identical results on identical repository state; Git
access is read-only plumbing (`rev-parse`, `cat-file -t`,
`merge-base --is-ancestor`, `log`).

### C3 — State↔Git reconciliation (both directions)
State→Git: every COMPLETE task's merge is a real, reachable, unique commit
with its checkpoint head ancestral to it. Git→State (coverage): every wave
has Work Order + checkpoint + design doc, and the current implementation
state records exactly the merged frontier.

### C4 — Dependency-ancestry proof
For every task, each declared dependency merge is an ancestor of the task
merge — the frozen sequencing rule is mechanically proven for the whole
program.

### C5 — Adversarial-evidence presence
The W14 matrix (sixteen frozen case names, all PASS, ancestral repo head)
is verified mechanically; its absence or any non-PASS verdict fails the
gate.

### C6 — Exact-revision currency
Every wave's checkpoint exists, cites exact base/head, and its recorded
heads are reachable from the final head; no stale-head completion claim
survives.

### C7 — Rollback safety demonstration
Every merged authority's rollback declaration is present and the
module-map check proves no wave left unrevertable state (no external
deployment/migration artifacts within the frozen surfaces).

### C8 — Documentation reconciliation
`current-state.md` matches live main and canonical machine state; the
bootstrap artifact chain (ARCHITECT_START_HERE, AGENTS, roadmap,
implementation-state, work orders, checkpoints) is complete and
contradiction-free.

### C9 — Fresh-agent recovery
The zero-history rule is verified both mechanically (recovery-chain checks)
and by the recorded human walkthrough at review.

### C10 — Bounded gate surface
No new architecture, no `src/sos/` changes, no frozen-document edits, no
test modifications; the diff touches only the five allowed Worker files;
the sign-off record and ROADMAP_COMPLETE reconciliation occur only under
Architect authority after merge.

## Required regression coverage

Tests MUST include, at minimum: a positive fixture reproducing a consistent
mini repository state (synthetic implementation-state, checkpoints, matrix,
docs in a temp directory) on which every check function returns PASS;
negative fixtures for each check (a dangling merge SHA, a COMPLETE task
without a merge, a dependency that is NOT an ancestor, a missing matrix
case, a non-PASS verdict, a stale/unreachable checkpoint head, a
current-state.md SHA mismatch, an extra `src/sos` module, a missing design
doc) on which exactly the targeted check FAILs; determinism of the report
(two runs over identical state produce identical JSON); read-only behavior
(the repository tree hash is unchanged by a check-only run); the
resolver-injection boundary (check logic is testable without invoking Git —
a fake in-memory revision resolver is injected, per the design doc).

## Deterministic verification

Worker MUST run and report exact-head results for:

```text
python -m pytest
python -m compileall -q src tests
python tools/final_gate_check.py --report spec/development-state/W15-gate-report.json
```

The gate script itself must exit 0 with every check PASS at the final head.
No network dependency may be required for any of the three commands.

## Evaluation / real-system evidence

W15's real-system evidence is the gate itself: the machine checks running
against the actual final repository head, plus the recorded fresh-agent
zero-history recovery walkthrough (sign-off packet item 6). No browser,
deployment, or external-system evidence applies to this Work Order.

## Risk / rollback

**Risk:** (1) false positive — a check passes although state is
inconsistent. Mitigations: every check has a negative fixture in
`tests/test_w15_final_gate_check.py`; the gate never approves (reconciliation
records facts; only Architect sign-off completes); review-time items are
explicitly marked rather than silently assumed mechanical. (2) stale
projections — canonical human-readable artifacts (e.g. `current-state.md`)
lag the final head; this is exactly what G10 detects, and the final
reconciliation commit closes it.

**Rollback:** ordinary Git revert of the merged W15 change (the script and
its tests are additive tooling; reverting removes the mechanical gate but
not any recorded evidence). The ROADMAP_COMPLETE reconciliation commit, if
later found wrong, is itself revertable canonical bookkeeping — it records
facts and confers no scope.

## Completion / reconciliation protocol

When implementation is complete, the Worker MUST:

1. run the full verification set at the exact head and checkpoint base/head
   SHAs, the three command results, and the gate-report reference in
   `spec/development-state/W15-checkpoint.md`;
2. assemble the Worker-owned sign-off packet items (gate report, exact-head
   verification outputs, W14 matrix reference, checkpoint chain reference);
3. remain at `WAITING_FOR_ARCHITECT`;
4. stop without merging, without writing `ROADMAP_COMPLETE`, without
   dispatching any successor (there is no W16), and without modifying
   canonical state;
5. await Architect review and sign-off. Corrections stay on the same PR.

W15 completion requires the Architect sign-off, the actual Git merge of the
W15 PR, and the final reconciliation commit recording `ROADMAP_COMPLETE`,
the W15 merge, and the closed frontier. After that reconciliation the
SOS-v1 frozen roadmap is complete; any further work requires a new governed
program under the Constitution — none is authorized by this Work Order.
