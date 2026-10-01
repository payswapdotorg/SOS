# W15 Final Gate Design (repository-level reconciliation and evidence gate)

**Status:** IMPLEMENTED — reconciled to the implemented contract by the W15
Worker (work branch `work/w15-final-gate`); §§1–7 (the prepared design)
are preserved verbatim below — extend, never weaken — and §§8–14 record the
implemented contract, its reconciliations to the repository's actually
recorded conventions, the baseline as shipped, and the test coverage map.
The Work Order `spec/work-orders/W15-final-architect-gate.md` remains the
normative authority.
**Work Order:** `spec/work-orders/W15-final-architect-gate.md` (prepared;
frozen once dispatched)
**Dependencies at preparation:** W14 NOT merged (itself blocked on
W12/W13). Preparation-time repo facts (verified by read): live `main`
`e3a97b895ca7f6cc7206a50bde45b2b55c554195` (NOT the dispatch base);
implementation-state records W0–W11 COMPLETE (W0 bootstrap
`8158bc441025e6e815999deb965dd4b7adf989ac`; W1 `091d4d10…`;
W2 `587201d3…`; W3 `6541441b…`; W4 `26060db5…`; W5 `2bfd0f89…`;
W6 `b5171f70…`; W7 `25f663cf…`; W8 `65b84058…`; W9 `203cfb75…`;
W10 `a1778653…`; W11 `aae25181…`), W12 DISPATCHED (PR #19 open), W13/W14/W15
BLOCKED. `current-state.md` on main still projects the W10-era state (live
main `d2b813eb…`) — i.e., it lags the actual head by several merges. That
lag is precisely the class of defect G10 exists to catch at the final head
(motivating observation, not a defect to fix in this preparation).
**Gate semantics extend:** `docs/implementation/ARCHITECT-REVIEW-PROTOCOL.md`,
`docs/implementation/SOS-IMPLEMENTATION-PROCESS.md` (§2, §11, §14),
`docs/implementation/TL-FINAL-HANDOFF.md` (§7 review discipline)
**Planned artifacts:** `tools/final_gate_check.py`,
`tests/test_w15_final_gate_check.py`,
`spec/development-state/W15-gate-report.json`,
`spec/development-state/W15-checkpoint.md`; Architect-side
`spec/development-state/W15-final-sign-off.md` (at sign-off, not Worker
surface)

## 1. Overview

W15 is the terminal gate of the SOS-v1 frozen roadmap: a repository-level
reconciliation and evidence gate. It is NOT a product subsystem — it adds
no architecture and no `src/sos/` code. Its product is certainty, stated
mechanically, that at the final head:

- the implementation conforms to the frozen architecture;
- canonical machine state reconciles with actual Git history in both
  directions;
- every Work Order's completion lifecycle evidence exists and is current;
- the adversarial evidence from W14 is present and complete;
- rollback safety is demonstrable for every merged authority;
- a fresh agent can recover the whole operating state from the repository
  alone (zero-history rule);
- and the Architect can sign off the completed roadmap from an evidence
  packet, not from memory.

The gate is implemented as one offline, read-only, deterministic script
whose every check is a pure function over repository state plus an injected
revision resolver, so the whole gate is unit-testable without Git and
negative-testable per check.

## 2. The gate checklist (machine-checkable items G01–G12)

Each check returns `{id, title, area, status: PASS|FAIL, details}`. Areas
map to the eleven mandated coverage areas. "Gate baseline" is a
module-level constant table in the script (filled at W15 dispatch from the
then-verified repository facts, Architect-verified at review — the baseline
records data, it does not authorize anything).

| ID | Check (precise semantics) | Area |
| --- | --- | --- |
| G01 | **FROZEN_AUTHORITY_INTEGRITY.** The five frozen authority documents (`spec/architecture.md`, `spec/architecture-lock.md`, `spec/constitution.md`, `spec/requirements.md`, `spec/implementation-roadmap.md`) exist and their sha256 digests equal the gate-baseline digests recorded at dispatch. FAIL means a frozen semantic drifted during W15 — hard stop, requires a governed Architecture Change Request. | architecture |
| G02 | **MODULE_SURFACE_CONFORMANCE.** The set of `src/sos/*.py` (excluding `__init__.py`) equals the gate-baseline wave→module map exactly (W1 `model.py`; W2 `graph.py`; W3 `recovery.py`; W4 `evidence.py`; W5 `causal.py`; W6 `candidates.py`; W7 `assurance.py`; W8 `experimentation.py`; W9 `autonomy.py`; W10 `personalization.py`+`platform.py`; W11 `execution.py`; W12 and W13 modules per their merged Work Orders; W14/W15 add no modules). FAIL on any extra module (possible fifth authority/unmapped subsystem) or any missing module. Proves architecture conformance (a) mechanically: the frozen four authority classes are realized by exactly the mapped per-wave surfaces. | architecture |
| G03 | **REQUIREMENTS_COVERED.** For every R1–R24: the token `R<n>` appears in the "Primary requirements" line of at least one `spec/work-orders/W*.md` AND in the W14 verification mapping (scanned from `spec/development-state/W14-checkpoint.md` mapping table and/or the W14 design doc §1 mapping). FAIL names the uncovered requirement. | requirements |
| G04 | **STATE_VS_GIT.** Parse `spec/development-state/implementation-state.json`. For every task T in W1..W14 with `status == "COMPLETE"`: (i) `mergedAs` is a 40-hex SHA; (ii) `resolver.exists(mergedAs)`; (iii) `resolver.is_ancestor(mergedAs, HEAD)`; (iv) `mergedAs` values are pairwise unique; (v) if the wave's checkpoint records an implementation/review head H, then `resolver.is_ancestor_or_equal(H, mergedAs(T))`. W0 exception: `bootstrapCommit` must exist and be ancestral to HEAD; `mergedAs: null` is lawful for W0 only. FAIL on any violation. Conversely (coverage direction): every wave W1..W15 has a Work Order file and a checkpoint file (see G08/G10), and the implementation-state task-key set equals the frozen roadmap task set {W0..W15}. | implementation state |
| G05 | **DEPENDENCY_ANCESTRY.** For every task T with non-empty `dependencies`: for every dependency D, the authoritative merge of D (`mergedAs`, or `bootstrapCommit` for W0) satisfies `resolver.is_ancestor(merge(D), merge(T))` (W15 itself: every W0–W14 merge is ancestral to the W15 reviewed head). This mechanically proves the frozen sequencing rule for the entire program. | dependency ancestry |
| G06 | **SUITE_GREEN.** Run `python -m pytest` and `python -m compileall -q src tests` in the repository root (offline subprocesses); record exit codes and the pytest summary count N. PASS iff both exit 0 and N ≥ the W14 checkpoint's recorded count (extend-never-weaken). The exact counts go into the report. | tests |
| G07 | **ADVERSARIAL_EVIDENCE.** `spec/development-state/W14-adversarial-evidence-matrix.json` exists, parses, `schema == "sos-w14-adversarial-evidence-matrix/1.0"`, its row set contains each of the sixteen frozen case names at least once, every `verdict == "PASS"`, and `resolver.is_ancestor(rows' repoHead, HEAD)`. FAIL names the missing/failing case. | adversarial evidence |
| G08 | **CHECKPOINTS_CURRENT.** For every wave W in W1..W15: `spec/development-state/W{W}-checkpoint.md` exists, contains a base SHA and a head (or the documented PR-head reference per ARCHITECT-REVIEW-PROTOCOL §2), and every 40-hex SHA it records as an implementation/review head is `resolver.is_ancestor_or_equal(sha, HEAD)`. FAIL on a missing checkpoint or an unreachable (stale-head) claim. | exact revisions |
| G09 | **ROLLBACK_SAFETY.** For every wave W1..W15: the checkpoint (or the wave's design doc, recorded in the gate baseline which file carries it) contains a rollback declaration (section/heading match, e.g. "Rollback:" with a mechanism statement). Combined with G02 (module surface) and G06 (suite green, which includes every wave's rollback-invariant tests — DEPLOY-requires-rollback, bounded paths, revert-only mechanisms), this demonstrates rollback safety for every merged authority: each wave is revertable by ordinary Git and none introduced unrevertable external state. | rollback safety |
| G10 | **DOCS_RECONCILED.** `spec/development-state/current-state.md`: (i) its recorded "Live `main` SHA:" value equals actual HEAD; (ii) its "Last Completed Work Order" equals the highest-COMPLETE task in implementation-state; (iii) its "Current frontier" equals implementation-state `currentFrontier`. Additionally every wave W1..W15 has a design doc under `docs/implementation/W{W}-*-DESIGN.md` and a Work Order under `spec/work-orders/W{W}-*.md` (filenames from the gate baseline). FAIL names the stale field/file. (Preparation-time motivation: current-state.md currently lags live main — the exact defect class this check exists to catch.) | documentation |
| G11 | **FRESH_AGENT_RECOVERABLE (mechanical proxy).** The zero-history bootstrap chain exists and is mutually consistent: `ARCHITECT_START_HERE.md`, `AGENTS.md`, frozen specs (G01), roadmap (G01), `implementation-state.json` (G04), `current-state.md` (G10), Work Orders (G10), checkpoints (G08), and G01–G10 all PASS. The check asserts the chain answers, from repository state alone, every question of SOS-IMPLEMENTATION-PROCESS §14 (what is active, what is merged, what are the exact heads, what verification ran, what is next). The **human** half — a fresh reviewer actually bootstrapping and stating the frontier — is a review-time protocol step recorded in the sign-off record (script cannot verify comprehension; it verifies recoverability). | fresh-agent recovery |
| G12 | **SIGNOFF_PACKET_READY.** The Worker-owned packet components exist at the final head: the gate report file, the W14 matrix (G07), the W15 checkpoint citing the three verification commands' results, and the checkpoint chain (G08). The sign-off record itself is Architect-authored at approval — deliberately NOT a script check (the gate never approves; process §11). | final sign-off |

Report schema (`spec/development-state/W15-gate-report.json`):

```json
{
  "schema": "sos-w15-gate-report/1.0",
  "repoHead": "<exact 40-hex SHA>",
  "commands": {"pytest": {"exitCode": 0, "passed": 1234}, "compileall": {"exitCode": 0}},
  "checks": [{"id": "G01", "title": "…", "area": "architecture", "status": "PASS", "details": "…"}],
  "overall": "PASS"
}
```

## 3. Script design (`tools/final_gate_check.py`)

- **Purity boundary:** every check is a function
  `check(state: GateState, resolver: RevisionResolver) -> CheckResult`,
  where `GateState` is the parsed repository content (implementation-state
  JSON, checkpoints, matrix, current-state, module listing, baseline) and
  `RevisionResolver` is an injected protocol:
  `head() -> str`, `exists(sha) -> bool`,
  `is_ancestor(ancestor, descendant) -> bool`. The CLI wires a
  Git-backed resolver (read-only plumbing: `git rev-parse HEAD`,
  `git cat-file -t <sha>`, `git merge-base --is-ancestor <a> <b>`,
  `git log`); the tests wire an in-memory DAG resolver — so all check logic
  is testable with zero subprocesses, and the only Git-touching code is the
  thin resolver adapter (also unit-tested against a temp git repository).
- **Determinism:** no clocks, no randomness, no network; the report embeds
  only repo-derived facts; two runs over identical state produce
  byte-identical reports (asserted in tests). A check-only mode
  (`--check-only`) writes nothing; report mode writes exactly one file (the
  report path argument).
- **Read-only discipline:** apart from its own report file the script
  mutates nothing; tests assert the repository tree hash is unchanged by a
  check-only run.
- **G06 subprocess boundary:** pytest/compileall are launched as offline
  subprocesses from the repository root only in report mode; their exit
  codes and the parsed pytest count are recorded. The Worker ALSO runs both
  commands manually for the checkpoint (exact-head discipline); the script
  never edits anything to make them pass.
- **Baseline table (module-level constant):** frozen-doc digests (recorded
  at dispatch, Architect-verified at review), wave→module map, wave→
  work-order/design/checkpoint filenames, the sixteen W14 case names, W0
  bootstrap exception, per-wave rollback-declaration carrier. Changing the
  baseline is a review-visible diff, never a silent reroute.

## 4. Reconciliation rules (Git vs implementation-state vs docs)

Authority order is fixed by SOS-IMPLEMENTATION-PROCESS §1: actual Git
history and live `main` outrank canonical development-state artifacts,
which outrank human-readable projections. The gate enforces:

1. **Git is completion authority:** a task is COMPLETE only with a real,
   reachable merge (G04 i–iii). Machine state may never assert completion
   Git cannot confirm (development-state README invariant 2).
2. **State is the ledger:** every wave merge must be recorded in
   `implementation-state.json` with its exact `mergedAs` (G03/G04 coverage
   direction); the ledger's task set equals the frozen roadmap's (G03).
3. **Sequencing is ancestry:** dependency edges must be real ancestor
   relations in Git (G05) — the frozen sequencing rule as a graph property.
4. **Checkpoints are the lifecycle evidence:** each wave's checkpoint head
   must be ancestral to its merge and reachable from the final head (G08) —
   stale-head completion claims fail (review-protocol hard stop
   "tests/evidence are stale-head").
5. **Docs are projections, checked against their sources:** `current-state.md`
   must match HEAD and the machine state field-by-field (G10). Projections
   never authorize (development-state README); the gate checks them anyway,
   because a stale projection breaks the zero-history rule.
6. **Frozen semantics are immutable:** the five frozen documents must be
   byte-identical to the dispatch-time baseline (G01); recording roadmap
   completion happens in canonical state and docs, never by editing frozen
   semantics (Work Order sign-off protocol).
7. **The gate never approves:** PASS is evidence for the Architect's
   sign-off, not a substitute (process §11: "Reconciliation is bookkeeping
   and cannot approve or widen scope").

## 5. Fresh-agent recovery test design (zero-history rule)

Mechanical half (G11): the script proves the recovery chain
`live main → roadmap → implementation-state → Work Order → dependency
merge evidence → current implementation → exact verification/evidence →
frontier` is complete and contradiction-free at the final head — every link
exists (G01, G04, G08, G10) and no two links disagree (G04, G05, G10
cross-checks).

Human half (review-time, recorded): a reviewer who did not author the
program artifacts performs the ARCHITECT_START_HERE.md bootstrap sequence
(§"Bootstrap sequence" steps 1–8) using ONLY repository state, then states:
current frontier, active/merged Work Orders with SHAs, the verification
evidence trail, and what could be implemented next. The walkthrough record
(this statement, the reviewer identity, the head SHA, and date) is packet
item 6 in the sign-off protocol. The roadmap's rule "conversation history
and agent memory are never hidden prerequisites" is thereby tested, not
assumed — the reviewer's lack of history is the test condition.

## 6. Sign-off protocol

1. **Precondition:** W15 Worker at `WAITING_FOR_ARCHITECT` with the packet
   assembled (gate report all-PASS at the exact head; the three command
   results; W14 matrix reference; checkpoint chain reference) — Work Order
   "Required outcomes" item 10.
2. **Review:** the Architect (or operator-delegated TL, delegation recorded
   — the W10/W11 precedent) verifies the gate baseline digests against the
   frozen v1.0 documents, inspects the diff (only the five allowed files),
   performs/records the fresh-agent walkthrough, and executes the
   ARCHITECT-REVIEW-PROTOCOL hard-stop list against the final state.
3. **Sign-off record:** `spec/development-state/W15-final-sign-off.md`
   (Architect-authored): signer identity + authority basis (or recorded
   delegation), exact final head SHA, references to the six packet items,
   the G01–G12 verdict table, residual limitations, date.
4. **Merge:** the W15 PR merges (the reviewed head only).
5. **Final reconciliation commit** (Architect/TL authority): canonical
   state records completion — `implementation-state.json`:
   `status: "ROADMAP_COMPLETE"`, W15 `status: "COMPLETE"` +
   `mergedAs: <W15 merge SHA>`, `currentFrontier: []`, `currentTask: null`,
   note recording the final gate and sign-off;
   `current-state.md`: final projection (program complete; final head;
   recovery path unchanged). Frozen documents remain byte-identical v1.0.
6. **Terminal state:** the SOS-v1 frozen roadmap is complete. No W16
   exists; successor programs require a new governed roadmap under the
   Constitution and are out of scope for this Work Order.

## 7. Non-goals

- **No new architecture** — no new authority classes, subsystems, product
  semantics, or ports; no edits to frozen architecture/lock/constitution/
  requirements/roadmap; architectural concerns surface as findings or
  Architecture Change Requests (`spec/architecture-change-process.md`),
  never as in-PR semantic changes.
- No `src/sos/` changes, no `sos` exports, no product code; the gate script
  is tooling under `tools/` and is never imported by the product.
- No test modifications or re-runs-to-green; a red suite is a finding.
- No network, GitHub API, or credential dependence; PR-state and
  open-sibling reconciliation are review-time Architect checks, explicitly
  not script checks.
- No self-approval by the gate: PASS evidence ≠ Architect sign-off; the
  Worker never merges, never writes `ROADMAP_COMPLETE`, never reconciles
  canonical state.
- No dependence on unmerged work: the design binds W12/W13/W14 only through
  their merged Work Orders and actual merges (gate baseline filled at
  dispatch from verified repo facts).

## 8. The implemented check semantics (reconciled to the repository's recorded conventions)

The prepared design §2 is the specification; this section records the
implemented contract. Every reconciliation below EXTENDS the prepared
semantics or keys it to a convention the repository actually records — none
weakens a prepared guarantee; each is covered by negative fixtures in
`tests/test_w15_final_gate_check.py` and disclosed in the W15 checkpoint's
honest-deviations section.

**G01 FROZEN_AUTHORITY_INTEGRITY** — implemented exactly as prepared: the
five frozen documents must be byte-identical (sha256) to the dispatch-time
gate baseline (§10). The baseline records data; the Architect verifies the
digests against frozen v1.0 at review (review-time, named in the protocol).

**G02 MODULE_SURFACE_CONFORMANCE** — implemented exactly as prepared
(§10's wave→module map; W12 `optimization.py` and W13 `selfevolution.py`
taken from their merged Work Orders).

**G03 REQUIREMENTS_COVERED** — the prepared semantics, with the repository's
actual requirement-line syntaxes handled faithfully: the Work-Order scan
parses each Work Order's "Requirements:"/"Primary requirements:" line and
expands `Rn–Rm` ranges and `Rn/Rm` slash pairs (the W1–W6 and W7+ line
formats respectively); the W14 verification mapping is scanned (with the
same expansion) from the W14 design doc and the W14 checkpoint; the roadmap
ledger table ("## Frozen task ledger") is parsed for the task set; every
row W0–W14 must have a COMPLETE task with a merge (W0 via the recorded
`bootstrapCommit` exception). Task-set equality between the roadmap ledger
and `implementation-state.json` is enforced here (G04's coverage direction
cites it).

**G04 STATE_VS_GIT** — implemented as prepared, plus a checkpoint
merge-label cross-check (a "**Merge SHA:**" claim must equal the ledger
`mergedAs`; W1 carries one, and it reconciles), plus the squash-era
PR-head exemption below. Coverage direction (Work Order + checkpoint +
design-doc existence) is enforced by G08/G10 and cited in G04's details,
per the prepared design's own "(see G08/G10)".

**The §2 squash-era PR-head exemption (G04(v)/G08 reconciliation).** A
checkpoint head claim that is NOT ancestral to its wave's merge (G04(v)) or
to HEAD (G08) is lawful ONLY when (a) the claim line's own label matches
the review/PR-head reference convention (ARCHITECT-REVIEW-PROTOCOL §2:
"Review head" / "Reviewed head" / "PR `head.sha`" / an explicit §2
citation), (b) the claimed SHA resolves, and (c) the wave's merge is a
single-parent commit (squash-era topology — the branch content was replayed
onto the base, so the PR head is genuinely not an ancestor of `main`; the
W1 merge `091d4d10` is exactly this form). A non-ancestral
"implementation head" claim FAILs; the same review-head claim under a TRUE
(two-parent) merge FAILs; a dangling review-head reference FAILs. The
convention is recognized ONLY within the claim line itself (label + the
claim line + its immediate continuation), never anywhere in the file, so a
stale head cannot hide behind an unrelated §2 mention. Every exemption is
recorded in the report details.

**G05 DEPENDENCY_ANCESTRY** — implemented exactly as prepared: all 30
declared edges (W0 via its `bootstrapCommit`) must be real ancestry
relations; for the active/unmerged task (W15 at the reviewed head) every
dependency merge must be ancestral to the reviewed head; and every W0–W14
merge must be ancestral to the W15 reviewed head.

**G06 SUITE_GREEN** — implemented as prepared: report mode launches
`python -m pytest` and `python -m compileall -q src tests` as local
subprocesses from the repository root (never edit-to-green); check-only
mode launches no subprocess and records G06 as DEFERRED (tolerated by the
exit contract: report mode exits 0 iff every check passes; check-only
exits 0 iff no check FAILs). The extend-never-weaken threshold is
RE-PARSED from the W14 checkpoint's recorded "Exact pass count: **478**"
at run time (dispatch-baseline 478 as the verified fallback — a regression
guard also asserted by the test suite). The exact counts go into the
report's `commands` object.

**G07 ADVERSARIAL_EVIDENCE** — implemented exactly as prepared (schema,
the sixteen frozen case ids each present at least once, every verdict
PASS, `repoHead` ancestral of HEAD). The baseline records the sixteen ids
in their persisted matrix realization (`ADV-01-missing-evidence` …
`ADV-16-partial-failure-recovery`), which is the operator-mandated
verbatim catalog in catalog order.

**G08 CHECKPOINTS_CURRENT** — the prepared head-claim semantics, keyed to
the repository's recorded checkpoint conventions: a claim line is a bold
label naming a base / head / tip / merge / implementation-SHA claim (the
W1–W15 forms, including "Latest implementation SHA" and the W11+ multi-line
label form whose SHA sits on the following line); base claims must resolve
and be reachable from HEAD; head claims must resolve and be
ancestor-or-equal of HEAD, or be lawful under the §2 squash-era exemption
above. Dangling NON-claim narrative citations (outside any claim label)
are recorded as observations in the details — the prepared check never
covered prose citations, and recording extends the report's evidence
without changing pass/fail semantics (the W13 checkpoint's one-character
typo of the W12 dispatch point is recorded this way and escalated in the
W15 checkpoint).

**G09 ROLLBACK_SAFETY** — the prepared carrier semantics with the baseline
recording, per wave, WHICH file carries the declaration and in WHICH form:
W3–W15 carry a rollback section (heading/label match + a mechanism
statement, e.g. "ordinary Git revert …"); W1/W2 predate that convention
(their checkpoints date to the program's first waves) and carry the
early-wave scope-exclusion form ("W1 intentionally contains no runtime
observation … / No runtime architecture recovery … changes"), which states
the same fact G09 exists to demonstrate — the wave introduced nothing
beyond its additive surface, so ordinary Git revert is complete recovery.
G02 (exactly the frozen module surface) and G06 (the suite green,
including every wave's rollback-invariant tests) co-enforce, per the
prepared design. Additionally the implemented check scans the whole
repository tree for deployment/migration/network artifacts
(Dockerfile/compose/terraform/helm/k8s/migrations/alembic/SQL patterns;
`.git`/`.github`/caches excluded) — a mechanical extension proving no
merged wave left unrevertable external state.

**G10 DOCS_RECONCILED (the one substantive reconciliation).** The prepared
design required field-by-field equality of `current-state.md` with HEAD
and the machine state. Two recorded repository facts make literal equality
impossible at any commit that contains the projection: (a) the live-main
SHA line cannot embed the SHA of the commit that carries it — the
repository's own recorded convention (since the W12-era reconciliations)
is the "recompute from live Git" instruction with milestone SHAs; (b) the
projection header is rewritten by merge-reconciliation commits under
Architect/TL authority AFTER each merge, and the Work Order's own sign-off
protocol assigns the FINAL projection update to the post-merge final
reconciliation commit — the Worker may never touch it. At the W15 dispatch
base the projection lags the ledger by exactly one wave (the W14
reconciliation `c04ddf1` updated the ledger but only appended the W14 gate
record to `current-state.md`). The implemented semantics preserve every
guarantee the prepared check existed for (a stale projection breaking the
zero-history rule) while keying to the recorded lifecycle:

- every wave W1–W15 has its Work Order and design doc (baseline
  filenames) — as prepared;
- the four projection fields must be present — as prepared;
- the live-main line: EITHER a literal 40-hex SHA equal to actual HEAD
  (the strict prepared form), OR the recorded recompute convention, in
  which every cited milestone SHA must resolve and be ancestral of HEAD;
  a plain literal SHA that is not HEAD FAILs (the W10-era stale-recording
  defect class the prepared design wanted caught);
- the last-completed wave's cited merge must be EXACTLY the ledger's
  `mergedAs` for that wave (a wrong or dangling SHA FAILs), and the wave
  must never be AHEAD of the ledger (a false completion claim FAILs);
- the frontier must be a real ledger task, never ahead of the ledger
  frontier;
- while the program is OPEN (ledger status ≠ ROADMAP_COMPLETE): the
  last-completed/frontier/machine-state-snapshot fields may lag the ledger
  by AT MOST the single merge-reconciliation boundary (one wave); any lag
  is RECORDED in the report details and flagged REVIEW-TIME for the
  Architect ("the final reconciliation commit closes it" — the Work
  Order's own risk section); a lag of two or more waves FAILs (a genuinely
  broken recovery chain);
- in the TERMINAL state (ROADMAP_COMPLETE): strict field equality — the
  last-completed must be the highest COMPLETE wave (W15) with its exact
  merge, the frontier must be the none-form or exactly the (empty) ledger
  frontier, and the machine-state snapshot must be empty — enforced
  exactly as the prepared design specified, at the one state where it is
  enforceable.

At the W15 reviewed head the committed report's G10 details record the
observed one-wave lag verbatim and the Architect flag; the W15 checkpoint
escalates it (deviation 1).

**G11 FRESH_AGENT_RECOVERABLE** — implemented as prepared (mechanical
proxy: bootstrap artifacts + G01–G10). G06's check-only DEFERRED is
tolerated (it is not a broken link; the subprocess evidence is collected
in report mode). The human half is REVIEW-TIME and named in the details
and the sign-off protocol.

**G12 SIGNOFF_PACKET_READY** — implemented as prepared: the Worker-owned
packet components (the W14 matrix, the W15 checkpoint citing the three
verification commands' results, the complete W1–W15 checkpoint chain, and
the gate report — present at the report path, or produced by the current
report-mode run). The sign-off record itself and open-PR/PR-identity
reconciliation are REVIEW-TIME (deliberately not script checks; the gate
never approves).

## 9. The report and its determinism (as implemented)

Report schema — exactly the prepared §2 schema:
`{"schema": "sos-w15-gate-report/1.0", "repoHead", "commands": {"pytest":
{"exitCode", "passed"}, "compileall": {"exitCode"}}, "checks": [{id,
title, area, status, details}], "overall"}` — written in report mode only,
to exactly one file (the report path argument; default
`spec/development-state/W15-gate-report.json`), UTF-8 JSON with a sorted
deterministic layout. No clocks, no randomness, no network: two runs over
identical repository state produce byte-identical JSON (the report-path
presence of the report file itself is part of the state — the first write
initializes it, and the stabilized state is what the determinism contract
covers; the test suite asserts exactly this).

The committed report cites `repoHead` = the implementation head
`6c7d78482c41e01403ddd75398496fcefe0b6262` and was generated with the full
branch content in place (the two-commit convention, W10–W14 precedent and
the W14 matrix `repoHead` reconciliation in particular): the branch tip
carries the report, the checkpoint, and this reconciliation as a
documentation-only delta; a tip re-run reproduces identical verdicts and
differs only in the regenerated `repoHead` (the tip SHA).

## 10. The gate baseline as shipped

Frozen-doc sha256 digests (recorded at dispatch from the verified base
`c04ddf1314ebda2c23467367099bfbe7b32972b5`; the test suite re-verifies them
against the actual files at every run):
`spec/architecture.md`
`c711b626d430f58046ae5532bd0c4bc30782a2d82248f84689e4f9a37cf7218d`;
`spec/architecture-lock.md`
`83f88bd6de7e2a770911d77dc619fec7613593f87df76bfb154dd2269e219382`;
`spec/constitution.md`
`3c1067f59fbdb8f818032a1a7c33a4ae127887aa0c25bbe740f382e52be4d63d`;
`spec/requirements.md`
`21af44a902561788e09e36a9d9caab892647c3ab21565b12d1a022667427fd30`;
`spec/implementation-roadmap.md`
`22d8d90afcfcd19828ac5104d324bc835c89c5abe181bb64ca33ef37e1cb0cff`.
Wave→module map: W1 `model.py`; W2 `graph.py`; W3 `recovery.py`; W4
`evidence.py`; W5 `causal.py`; W6 `candidates.py`; W7 `assurance.py`; W8
`experimentation.py`; W9 `autonomy.py`; W10 `personalization.py` +
`platform.py`; W11 `execution.py`; W12 `optimization.py`; W13
`selfevolution.py`; W14/W15 none. The sixteen W14 case ids and the W14
count floor (478, re-parsed at run time) as in §8. Per-wave Work
Order/design-doc filenames, per-wave rollback carriers (W1/W2
scope-exclusion; W3–W15 section+mechanism), the W0 bootstrap exception,
and the deployment-artifact scan patterns complete the table. Changing the
baseline is a review-visible diff; it authorizes nothing.

## 11. The script architecture as implemented

One stdlib-only file, `tools/final_gate_check.py`: a module-level baseline
table (§10); `GateState` (the parsed repository content + injected command
results); the `RevisionResolver` protocol (`head`, `exists`,
`is_ancestor` with Git ancestor-or-equal semantics, `parents` via
`git log -n1 --format=%P` — read-only plumbing only) with `GitResolver`
as the thin Git-backed adapter and the tests' in-memory DAG resolver;
`CommandResults` for the injected G06 evidence; the ten primary checks as
pure `(GateState, RevisionResolver) -> CheckResult` functions; the G11
composite (explicit prior results input) and G12 (packet facts) closers;
`run_gate`, `build_report`, the CLI (`--report [PATH]` / `--check-only` /
`--root`, defaulting to the root containing `tools/`). Exit codes: 0 iff
every check passes (report mode) / no check FAILs (check-only); 1 on any
FAIL; 2 on tool misuse (unreadable root / no Git HEAD). The tool is
importable for the tests (the tests insert `tools/` on `sys.path`) but is
never imported by `src/sos/` and adds no `sos` exports.

## 12. Review-time items (explicit, per acceptance criterion C1)

The fresh-agent human walkthrough (packet item 6); the Architect-authored
sign-off record `spec/development-state/W15-final-sign-off.md`;
open-PR/PR-identity reconciliation; the verification of the gate baseline
digests against the frozen v1.0 documents; and the final reconciliation
commit that closes the recorded open-program projection lag. These are
named in the check details, the stdout summary, the report, and the W15
checkpoint — never silently assumed mechanical.

## 13. The test coverage map (as implemented)

`tests/test_w15_final_gate_check.py` (73 items: 70 functions, one of them
parametrized over the G06 command-failure modes): the positive
mini-repository fixture (every check PASS, the §2 exemption recorded, the
report shape exactly per schema); per-check negative fixtures for every
machine-checkable item — including every negative named by the Work
Order's "Required regression coverage" (dangling merge SHA; COMPLETE task
without a merge; dependency NOT an ancestor; missing matrix case; non-PASS
verdict; stale/unreachable checkpoint head; current-state.md SHA mismatch;
extra `src/sos` module; missing design doc) — each engineered so exactly
the targeted check FAILs, with the G11 composite (which by design requires
G01–G10) and a small set of honestly-documented cascades (G12's packet
components; G05's dependency edges) as the only additional failures, each
asserted explicitly; the §2 exemption matrix (topology guard,
resolvability guard, non-review-label guard); G06's threshold parse and
fallback; determinism (byte-identical stabilized runs); read-only behavior
(tree hash + file set unchanged by a check-only CLI run); the
resolver-injection boundary (subprocess poisoned — zero subprocess usage
in check logic); the GitResolver adapter against a temp git repository;
CLI end-to-end (check-only exit 0; report mode with a real passing
micro-suite, byte-identical second run; exit 1 on a failing gate; exit 2
on a non-repository root); the shipped baseline self-verification against
the actual repository; and the real-repository integration test through
the real Git plumbing (skipped at the implementation head — its subject
artifacts are the tip's documentation-only delta — and re-proving the
committed report's verdicts at the tip and after merge).

## 14. Non-goals honored

No new architecture, authority class, subsystem, product semantics or
ports; no `src/sos/` change and no `sos` exports; no frozen-document,
roadmap-semantic, Work-Order-machinery, W1–W14-artifact, `.github/**` or
`pyproject.toml` change; no test modifications or re-runs-to-green; no
`ROADMAP_COMPLETE`, no merge, no PR creation, no successor dispatch; no
network/GitHub-API/credential dependence; no self-approval — PASS is
mechanical evidence for the Architect's sign-off, never a substitute
(process §11). The diff touches exactly the five Work-Order-allowed files
(`git diff --name-only c04ddf1314ebda2c23467367099bfbe7b32972b5..HEAD`).
