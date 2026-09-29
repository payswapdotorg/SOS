# W13 Implementation Checkpoint — PREPARATION TEMPLATE ONLY

> **THIS FILE IS A PREPARATION TEMPLATE — NOT A CHECKPOINT.**
> It was created by the W13 spec-preparation pass (task 3-a) so the future
> W13 Worker has the required checkpoint shape in place. **Nothing in this
> file is evidence of any W13 work.** Every `«…»` placeholder below is to be
> filled by the W13 Worker at checkpoint time, replacing the placeholder text
> with the actual value. Until then this file records preparation state only.
>
> Preparation provenance: template authored at live `main`
> `e3a97b895ca6f6cc7206a50bde45b2b55c554195` (the W12 dispatch point); W13
> is NOT dispatched (Work Order status `PREPARED — DISPATCH BLOCKED`; W12 is
> PR #19, open, unmerged). No W13 implementation exists at preparation time.

**Work Order:** `spec/work-orders/W13-self-evolution.md` (authoritative once
dispatched; dispatch requires the W12 merge and canonical reconciliation
first)
**State:** «to be filled by the W13 Worker — expected `WAITING_FOR_ARCHITECT`
(review iteration 1)»
**Branch:** «to be filled — expected `work/w13-self-evolution` (from live
`main` AFTER the W12 merge)»
**Base SHA (dispatch commit, live `main` AFTER the W12 merge):**
«to be filled — the exact post-W12-merge `main` SHA recorded at dispatch; NOT
`e3a97b895ca6f6cc7206a50bde45b2b55c554195`, which is the W12 dispatch point»
**Exact implementation head (contract code, exports, tests):**
«to be filled»
**Exact branch tip:** «to be filled — the commit carrying this checkpoint
plus `docs/implementation/W13-SELF-EVOLUTION-DESIGN.md` reconciled to the
implementation (a commit cannot embed its own SHA; record the head in the
worker report)»

## Dependency proof (to be verified by the Worker from live state at dispatch)

Frozen-ledger declared dependencies (already authoritative at preparation
time; re-verify from `spec/development-state/implementation-state.json` and
Git at dispatch):

- W8 merged `65b84058aa204b3749e45b7e21ae433a4b138d83`
- W9 merged `203cfb7590bd25244cabf3cc7299dd192b00948d`

Reused frozen authorities (merged at preparation time; re-verify):

- W1 `091d4d10a38922fb2d9cadb103e7ba8caa7a1f20`
- W4 `26060db57c24ba8b36315c1005466046810c5163`
- W5 `2bfd0f89da129c6b3347d88b0d8da1b79dd04127`
- W6 `b5171f70ca5ce85ca0be07cfdb3abf034c03c32f`
- W7 `25f663cf444f92b3190074a9119619cbc53e9ece`

Roadmap sequencing gate (NOT an implementation dependency; must be satisfied
before dispatch):

- W12 merged as «to be filled — the W12 merge SHA from the actual Git merge
of PR #19 and the canonical reconciliation recording it»; the Worker's base
is the post-W12-merge live `main`. No unmerged branch content may be used as
a dependency, and W12 implementation internals must not be depended upon.

## Scope implemented (exactly the five allowed files — to be filled)

- `src/sos/selfevolution.py`: «to be filled — NEW; record model, frozen
vocabulary, lifecycle state machine, governed evaluation surface, W4
binding, W1 persistence; no network/subprocess/file-mutation/git»
- `src/sos/__init__.py`: «to be filled — W13 exports only (+N lines)»
- `tests/test_w13_selfevolution.py`: «to be filled — contract suite summary
(happy path, gate mechanics, intake policy, prohibition proofs, composition
identity, persistence/determinism)»
- `docs/implementation/W13-SELF-EVOLUTION-DESIGN.md`: «to be filled —
reconciled to the implemented contract (extend, never weaken; record honest
deviations from the PREPARED design §12 recommended defaults)»
- `spec/development-state/W13-checkpoint.md`: this file, filled.

Zero modifications to W1–W12 sources, frozen specs, roadmap, or Work Order
machinery (verify: `git diff --name-only <base>..HEAD` lists exactly the
four non-checkpoint files above; the fifth is this file).

## Acceptance criteria → implementation → test mapping (to be filled)

| Criterion | Implementation | Tests |
|---|---|---|
| C1 composed-authority integrity | «to be filled» | «to be filled» |
| C2 proposal-as-data integrity | «to be filled» | «to be filled» |
| C3 W7→W8→W9 ordering invariant | «to be filled» | «to be filled» |
| C4 no self-authorization | «to be filled» | «to be filled» |
| C5 ASK pause mechanics | «to be filled» | «to be filled» |
| C6 Constitution/authority protection | «to be filled» | «to be filled» |
| C7 governed promotion/rollback | «to be filled» | «to be filled» |
| C8 truth preservation | «to be filled» | «to be filled» |
| C9 origin never authorizes | «to be filled» | «to be filled» |
| C10 bounded recursion | «to be filled» | «to be filled» |
| C11 determinism and bounds | «to be filled» | «to be filled» |
| C12 persistence and bounded surface | «to be filled» | «to be filled» |

## Verification (to be filled by the Worker at checkpoint time)

```text
python -m pytest
python -m compileall -q src tests
```

Exact-head results:

```text
$ python -m pytest
«to be filled — exact pass count»
$ python -m compileall -q src tests
«to be filled — expected exit code 0; no output»
```

Exact pass count: «to be filled» = «baseline at the recorded dispatch base»
(verified by the Worker before any work) + «N new W13 tests». Preparation
reference only (NOT the Worker's baseline): live `main`
`e3a97b895ca6f6cc7206a50bde45b2b55c554195` (W12 dispatch point) = 327
passed, compileall clean. Duration is environment-dependent; counts are
exact. Fully offline: no network, no provider, no wall clock.

## Honest deviations (to be filled)

«To be filled — every deviation from the Work Order envelope or the
PREPARED design's recommended defaults, with the governing reason; "none" is
a valid entry»

## Known limitations (to be filled)

«To be filled — expected shape: contract/proposal evidence only (fixture
chains, no live adoption); registries caller-supplied and in-memory;
adoption of a PROMOTED proposal stays with ordinary repository governance;
any others»

## Risk / rollback (to be filled)

«Expected shape: risk = boundary leakage (self-authorization, gate bypass,
rollback weakening, or source mutation); the C1–C12 mechanical invariants
are the guard and the promoted tests are the executable proof. Rollback =
ordinary Git revert of the merged W13 change; no deployment, network side
effect, or data migration in this slice.»

## Completion state (to be filled)

«Expected: `WAITING_FOR_ARCHITECT`. No merge, no push, no successor Work
Order, no W14 dispatch, no canonical-state modification. W13 completion
requires the Architect gate, actual Git merge, and canonical reconciliation
recording the W13 merge and the next frontier. Corrections stay on the same
PR.»
