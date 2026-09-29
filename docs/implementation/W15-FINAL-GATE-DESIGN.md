# W15 Final Gate Design (repository-level reconciliation and evidence gate)

**Status:** PLANNED — Work Order PREPARED, DISPATCH BLOCKED (W14 unmerged at
preparation; this design is the authoritative specification of the gate a
future Worker implements mechanically once W15 is dispatched)
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
