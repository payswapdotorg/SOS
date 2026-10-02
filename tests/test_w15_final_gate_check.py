"""W15 — deterministic test coverage for the final-gate machinery.

Work Order: ``spec/work-orders/W15-final-architect-gate.md`` (the normative
Work Order: acceptance criteria C1–C10; "Required regression coverage").
Design: ``docs/implementation/W15-FINAL-GATE-DESIGN.md`` §2–§3 and the
implemented-contract sections §8+ reconciled by this Worker.

Coverage (the Work Order's MUST list, plus the failure-detection path for
every machine-checkable check G01–G12):

- a positive fixture reproducing a consistent mini repository state
  (synthetic frozen docs, roadmap ledger, implementation-state, checkpoints,
  the W14 matrix, current-state.md, work orders, designs, module surface) on
  which every check returns PASS;
- negative fixtures on which exactly the targeted check FAILs (the composite
  G11 — which by design requires G01–G10 to pass — is the only documented
  cascade): a dangling merge SHA, a COMPLETE task without a merge, a
  dependency that is NOT an ancestor, a missing matrix case, a non-PASS
  verdict, a stale/unreachable checkpoint head, a current-state.md SHA
  mismatch, an extra ``src/sos`` module, a missing design doc, frozen-doc
  drift, uncovered requirements, task-set mismatch, duplicate merges, a
  non-COMPLETE task with a merge, a stale checkpoint-head-vs-merge claim, a
  failing/short pytest run, a failing compileall, a missing checkpoint, a
  missing rollback declaration, a deployment artifact, a stale literal
  live-main SHA, a two-wave projection lag, an ahead-of-ledger projection
  claim, terminal-state staleness, a missing bootstrap artifact, missing
  W15-checkpoint command citations, a missing report in check-only mode;
- the ARCHITECT-REVIEW-PROTOCOL §2 squash-era PR-head exemption: lawful
  (single-parent topology + review-head label) and rejected (true-merge
  topology / non-review label / dangling);
- determinism of the report (two runs over identical state produce
  byte-identical JSON);
- read-only behavior (a check-only CLI run leaves the repository tree hash
  and file set unchanged);
- the resolver-injection boundary: every check runs green with an in-memory
  DAG resolver and canned command results while ``subprocess`` is poisoned —
  zero subprocess usage in check logic; the thin GitResolver adapter is
  separately unit-tested against a temp git repository;
- the shipped gate baseline is verified against the actual repository
  (frozen-doc digests, module surface, W14 case ids, recorded count);
- the real repository passes G01–G05 and G07–G12 through the real Git-backed
  resolver once the W15 artifacts are committed (skipped at the
  implementation head, where they do not exist yet).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import final_gate_check as fgc  # noqa: E402


# ---------------------------------------------------------------------------
# The in-memory revision resolver (the resolver-injection boundary)
# ---------------------------------------------------------------------------


class FakeResolver(fgc.RevisionResolver):
    """A pure in-memory DAG: no Git, no subprocess, fully deterministic."""

    def __init__(self, dag: dict[str, tuple[str, ...]], head: str) -> None:
        self._dag = dict(dag)
        self._head = head

    def head(self) -> str:
        return self._head

    def exists(self, sha: str) -> bool:
        return sha in self._dag

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        if ancestor not in self._dag or descendant not in self._dag:
            return False
        stack = [descendant]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == ancestor:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self._dag.get(current, ()))
        return False

    def parents(self, sha: str) -> tuple[str, ...]:
        return self._dag.get(sha, ())


def sha(n: int) -> str:
    """Deterministic distinct 40-hex fixture SHAs."""
    return f"{n:040x}"


# The fixture DAG: a linear main line M0..M14 (one merge per wave W1–W14,
# each the single child of its predecessor — ancestry satisfies every real
# dependency edge), then the W15 implementation head H15 and the branch tip
# TIP beyond it; plus R1F/R2F (squash-era PR-head siblings, resolvable but
# not ancestral to their wave's merge) and SIDE (a side branch merged late,
# for the non-ancestor dependency negative).
M = {n: sha(100 + n) for n in range(15)}  # M[0]..M[14]
H15 = sha(115)
TIP = sha(116)
R1F = sha(500)
R2F = sha(501)
SIDE = sha(600)
XNODE = sha(700)
DANGLING = sha(999)

DAG: dict[str, tuple[str, ...]] = {M[0]: ()}
for n in range(1, 15):
    DAG[M[n]] = (M[n - 1],)
DAG[H15] = (M[14],)
DAG[TIP] = (H15,)
DAG[R1F] = (M[0],)      # sibling of M1: resolvable, NOT <= M1, NOT <= TIP
DAG[R2F] = (M[1],)      # sibling of M2: resolvable, NOT <= M2, NOT <= TIP
DAG[SIDE] = (M[4],)     # side branch merged at M12 (non-ancestor of M6)
DAG[M[12]] = (M[11], SIDE)
DAG[XNODE] = ()         # second parent for the true-merge topology variant

REAL_DEPS: dict[str, list[str]] = {
    "W0": [],
    "W1": ["W0"],
    "W2": ["W1"],
    "W3": ["W2"],
    "W4": ["W2"],
    "W5": ["W4"],
    "W6": ["W3", "W5"],
    "W7": ["W6"],
    "W8": ["W7"],
    "W9": ["W7", "W8"],
    "W10": ["W2", "W9"],
    "W11": ["W1", "W2", "W9"],
    "W12": ["W3", "W4", "W5", "W6", "W7", "W8", "W9"],
    "W13": ["W8", "W9"],
    "W14": ["W10", "W11", "W12", "W13"],
    "W15": ["W14"],
}

# Work-Order primary-requirements distribution: the union covers R1–R24 with
# R7 owned by exactly one Work Order (for the uncovered-requirement negative).
WO_REQUIREMENTS: dict[str, str] = {
    "W1": "R1–R5, R15–R18, R22–R23",
    "W2": "R7–R8, R23–R24",
    "W3": "R6–R8, R21, R23–R24",
    "W4": "R7, R9, R21, R23–R24",
    "W5": "R9, R20/R21, R23, R24",
    "W6": "R11/R12, R15, R21, R23, R24",
    "W7": "R12, R13, R15, R21, R23, R24",
    "W8": "R12, R14, R15, R21, R23, R24",
    "W9": "R13, R14, R16–R19, R21, R24",
    "W10": "R5, R15–R18, R22, R23, R24",
    "W11": "R6–R9, R13–R15, R18, R22–R24",
    "W12": "R1, R6–R15, R18, R22–R24",
    "W13": "R7, R9, R13–R16, R19, R20, R21–R24",
    "W14": "R1–R6, R8–R9, R11–R14, R19–R24 (integrated verification)",
    "W15": "R9, R13, R14, R21–R24",
}

W14_MAPPING_TEXT = (
    "Requirement traceability: R1–R5 by the scenario W1 stage; R6/R7/R8 "
    "by the two entry paths; R9/R21 by the evidence cycle; R10 by the "
    "causal stage; R11/R12 by the candidate stage; R13/R14 by assurance "
    "and rollback; R15/R16/R22 by the gate and ASK-bypass cases; R17/R18 "
    "by the narrowing stage; R19 by the learning record; R20 by the "
    "self-evolution boundary; R23 by the traceability assertions; R24 by "
    "the repository-resident program."
)


def _frozen_doc_content(name: str) -> str:
    return f"SOS frozen authority document (fixture): {name} v1.0\n"


def _roadmap_text() -> str:
    rows = ["| Work Order | Task | Dependencies | Outcome |", "|---|---|---|---|"]
    for w in (f"W{i}" for i in range(16)):
        deps = REAL_DEPS[w]
        dep_text = " + ".join(deps) if deps else "none"
        rows.append(f"| {w} | fixture task {w} | {dep_text} | fixture outcome |")
    return (
        "# SOS Implementation Roadmap (fixture)\n\n"
        "## Frozen task ledger\n\n" + "\n".join(rows) + "\n\n"
        "## Work Order execution template\n\nEvery Work Order MUST define "
        "scope.\n"
    )


def _impl_state_json() -> dict:
    tasks: dict[str, dict] = {
        "W0": {
            "status": "BOOTSTRAP_COMPLETE",
            "dependencies": [],
            "mergedAs": None,
            "bootstrapCommit": M[0],
        }
    }
    for n in range(1, 15):
        tasks[f"W{n}"] = {
            "status": "COMPLETE",
            "dependencies": REAL_DEPS[f"W{n}"],
            "mergedAs": M[n],
        }
    tasks["W15"] = {
        "status": "READY",
        "dependencies": REAL_DEPS["W15"],
        "mergedAs": None,
    }
    return {
        "schemaVersion": "1.0",
        "program": "SOS-v1",
        "roadmap": "spec/implementation-roadmap.md",
        "status": "W15_READY_TO_DISPATCH",
        "tasks": tasks,
        "currentFrontier": ["W15"],
        "currentTask": "W15",
        "notes": [],
    }


def _checkpoint_text(wave: str) -> str:
    n = fgc.wave_num(wave)
    parts = [
        f"# W{n} Implementation Checkpoint (fixture)",
        "",
        f"**Work Order:** fixture WO for {wave}",
        "**State:** `WAITING_FOR_ARCHITECT`",
        f"**Base SHA:** `{M[n - 1]}`",
    ]
    if wave == "W1":
        # The squash-era form (mirrors the real W1 checkpoint): a PR-head
        # reference under ARCHITECT-REVIEW-PROTOCOL §2.
        parts.append(f"**Review head SHA:** `{R1F}`")
        parts.append(f"**Merge SHA:** `{M[1]}`")
    elif wave == "W15":
        parts.append(f"**Exact implementation head:** `{H15}`")
    else:
        parts.append(f"**Exact implementation head:** `{M[n]}`")
    parts += [
        "",
        "## Dependency proof",
        "",
        "All dependencies verified merged in the branch ancestry.",
        "",
    ]
    if wave in ("W1", "W2"):
        # Early-wave scope-exclusion rollback declaration (pre-W3 form).
        parts += [
            "## Explicit exclusions / known limitations",
            "",
        ]
        if wave == "W1":
            parts.append(
                "- W1 intentionally contains no runtime observation, "
                "telemetry, architecture graph, candidate search, assurance "
                "or experiment execution."
            )
        else:
            parts.append(
                "No runtime architecture recovery, telemetry ingestion, "
                "causal memory, candidate search/ranking, assurance engine, "
                "experimentation execution, promotion/rollback, or "
                "architecture/meta-model changes."
            )
    else:
        parts += [
            "## Risk / rollback",
            "",
            "- **Risk:** fixture risk statement.",
            f"- **Rollback:** ordinary Git revert of the W{n} PR. No data "
            "migration, no running service.",
            "",
        ]
    if wave == "W14":
        parts += [
            "## Verification",
            "",
            "Exact pass count: **100**",
            "",
        ]
    if wave == "W15":
        parts += [
            "## Verification",
            "",
            "```text",
            "$ python3 -m pytest",
            "120 passed",
            "$ python3 -m compileall -q src tests",
            "(exit code 0; no output — clean)",
            "$ python3 tools/final_gate_check.py --report "
            "spec/development-state/W15-gate-report.json",
            "```",
            "",
        ]
    return "\n".join(parts) + "\n"


def _current_state_text(
    last_completed: str = "W14",
    last_merge: str = M[14],
    frontier: str = "W15",
    live_line: str | None = None,
    machine_line: str | None = None,
) -> str:
    if live_line is None:
        live_line = (
            f"recompute from live Git — the W14 merge is `{M[14]}`; this "
            "reconciliation commit advances `main` beyond it without "
            "changing any frozen semantics."
        )
    if machine_line is None:
        machine_line = (
            "`spec/development-state/implementation-state.json` → "
            "`W15_READY_TO_DISPATCH`, `currentFrontier = [\"W15\"]`, "
            f"`W14 = COMPLETE/{M[14]}` (verified current)"
        )
    return (
        "# SOS Current State (fixture)\n\n"
        "## Repository State\n\n"
        "- Architecture Version: `1.0` frozen\n"
        f"- Last Completed Work Order: `{last_completed}` (merge "
        f"`{last_merge}`, PR #21)\n"
        f"- Live `main` SHA: {live_line}\n"
        f"- Current frontier: `{frontier}`\n"
        f"- Machine state: {machine_line}\n\n"
        "## Important\n\n"
        "This file is not an authorization source. Recompute status from "
        "actual Git and canonical machine state.\n"
    )


def _matrix_dict() -> dict:
    return {
        "schema": fgc.W14_MATRIX_SCHEMA,
        "workOrder": "spec/work-orders/W14-dogfood-adversarial-verification.md",
        "repoHead": M[14],
        "generatedBy": "tests/test_w15_final_gate_check.py fixture",
        "rows": [
            {"caseId": case_id, "case": "fixture case", "verdict": "PASS"}
            for case_id in fgc.W14_CASE_IDS
        ],
    }


def build_fixture(
    root: Path,
    *,
    impl_state: dict | None = None,
    current_state: str | None = None,
    include_report_file: bool = True,
    use_real_frozen_docs: bool = False,
    sha_map: dict[str, str] | None = None,
) -> fgc.Baseline:
    """Write the consistent mini repository state; return its baseline.

    ``use_real_frozen_docs`` copies the five actual frozen authority
    documents (whose digests equal the shipped gate baseline) so the CLI —
    which always runs on the shipped module-constant baseline — validates a
    fixture repository end-to-end. ``sha_map`` rewrites the fixture's
    synthetic DAG SHAs into real commit SHAs (for CLI tests backed by a
    temporary Git repository with a matching commit chain).
    """

    def W(text: str) -> str:
        if not sha_map:
            return text
        for old, new in sha_map.items():
            text = text.replace(old, new)
        return text

    root.mkdir(parents=True, exist_ok=True)
    frozen: dict[str, str] = {}
    for rel in fgc.FROZEN_DOC_DIGESTS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if use_real_frozen_docs:
            content = (REPO_ROOT / rel).read_text(encoding="utf-8")
        else:
            content = _frozen_doc_content(rel)
        path.write_text(content, encoding="utf-8")
        frozen[rel] = fgc.sha256_file(path) or ""
    roadmap_content = (
        (REPO_ROOT / "spec/implementation-roadmap.md").read_text(
            encoding="utf-8"
        )
        if use_real_frozen_docs
        else _roadmap_text()
    )
    (root / "spec/implementation-roadmap.md").write_text(
        roadmap_content, encoding="utf-8"
    )
    frozen["spec/implementation-roadmap.md"] = (
        fgc.sha256_file(root / "spec/implementation-roadmap.md") or ""
    )

    (root / fgc.IMPLEMENTATION_STATE_PATH).parent.mkdir(
        parents=True, exist_ok=True
    )
    (root / fgc.IMPLEMENTATION_STATE_PATH).write_text(
        W(json.dumps(impl_state or _impl_state_json(), indent=1)),
        encoding="utf-8",
    )
    for w in (f"W{i}" for i in range(1, 16)):
        checkpoint = root / (
            f"spec/development-state/W{fgc.wave_num(w)}-checkpoint.md"
        )
        checkpoint.write_text(W(_checkpoint_text(w)), encoding="utf-8")
    (root / fgc.W14_MATRIX_PATH).write_text(
        W(json.dumps(_matrix_dict(), indent=1)), encoding="utf-8"
    )
    (root / fgc.CURRENT_STATE_PATH).write_text(
        W(current_state or _current_state_text()), encoding="utf-8"
    )

    for wave, rel in fgc.WORK_ORDER_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# {wave} Work Order (fixture)\n\n"
            f"**Primary requirements:** {WO_REQUIREMENTS[wave]}\n",
            encoding="utf-8",
        )
    for wave, rel in fgc.DESIGN_FILES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = f"# {wave} design (fixture)\n\nImplemented contract.\n"
        if wave == "W14":
            text += "\n" + W14_MAPPING_TEXT + "\n"
        path.write_text(text, encoding="utf-8")

    for wave, modules in fgc.WAVE_MODULES.items():
        for module in modules:
            path = root / "src" / "sos" / module
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f'"""{wave} fixture module (empty surface)."""\n',
                encoding="utf-8",
            )

    for rel in fgc.BOOTSTRAP_ARTIFACTS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"bootstrap artifact (fixture): {rel}\n", encoding="utf-8")

    report_path = root / fgc.DEFAULT_REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if include_report_file:
        report_path.write_text(
            json.dumps(
                {
                    "schema": fgc.REPORT_SCHEMA,
                    "repoHead": TIP,
                    "commands": {
                        "pytest": {"exitCode": 0, "passed": 120},
                        "compileall": {"exitCode": 0},
                    },
                    "checks": [],
                    "overall": "PASS",
                }
            )
            + "\n",
            encoding="utf-8",
        )
    if use_real_frozen_docs:
        return fgc.Baseline()
    return fgc.Baseline(frozen_doc_digests=frozen)


FAKE_COMMANDS = fgc.CommandResults(
    pytest_exit=0, pytest_passed=120, compileall_exit=0
)


def run_checks(
    root: Path,
    baseline: fgc.Baseline,
    dag: dict[str, tuple[str, ...]] | None = None,
    commands: fgc.CommandResults | None = FAKE_COMMANDS,
    report_mode: bool = True,
    report_path: Path | None = None,
) -> dict[str, fgc.CheckResult]:
    resolver = FakeResolver(dag or DAG, TIP)
    state = fgc.load_state(
        root,
        baseline=baseline,
        commands=commands,
        report_mode=report_mode,
        report_path=report_path or (root / fgc.DEFAULT_REPORT_PATH),
    )
    results, _overall = fgc.run_gate(state, resolver)
    return {r.id: r for r in results}


def assert_targeted(
    results: dict[str, fgc.CheckResult], target: str
) -> fgc.CheckResult:
    """The targeted check FAILs; every other failure is exactly the
    composite G11 (which by design requires G01–G10 to pass) — and only when
    the target is one of G01–G10."""
    failures = {k for k, r in results.items() if r.status == fgc.STATUS_FAIL}
    expected = {target}
    if target != "G11" and target in {c[0] for c in fgc.PRIMARY_CHECKS}:
        expected.add("G11")
    assert failures == expected, (
        f"expected failures {sorted(expected)}, got {sorted(failures)}: "
        + "; ".join(
            f"{k}: {results[k].details}" for k in sorted(failures)
        )
    )
    if "G11" in failures and target != "G11":
        assert target in results["G11"].details
    return results[target]


def rewrite(path: Path, transform) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(transform(text), encoding="utf-8")


def write_impl_state(root: Path, mutate) -> None:
    state = _impl_state_json()
    mutate(state)
    (root / fgc.IMPLEMENTATION_STATE_PATH).write_text(
        json.dumps(state, indent=1), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Positive fixture
# ---------------------------------------------------------------------------


def test_positive_fixture_every_check_passes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    results = run_checks(root, baseline)
    statuses = {k: r.status for k, r in results.items()}
    assert set(results) == {f"G{i:02d}" for i in range(1, 13)}
    assert all(s == fgc.STATUS_PASS for s in statuses.values()), statuses
    # The §2 squash-era PR-head exemption is recorded, not silently passed.
    assert "ARCHITECT-REVIEW-PROTOCOL §2" in results["G04"].details
    assert "79d" not in results["G04"].details  # fixture sha, not the real one
    assert results["G10"].details.count("lags the ledger") == 0
    assert "matches the ledger" in results["G10"].details
    assert results["G06"].details.startswith("python -m pytest: exit 0, 120")


def test_positive_fixture_overall_and_report_shape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    resolver = FakeResolver(DAG, TIP)
    state = fgc.load_state(
        root, baseline=baseline, commands=FAKE_COMMANDS, report_mode=True
    )
    results, overall = fgc.run_gate(state, resolver)
    assert overall == fgc.STATUS_PASS
    report = fgc.build_report(TIP, results, FAKE_COMMANDS, overall)
    assert set(report) == {"schema", "repoHead", "commands", "checks", "overall"}
    assert report["schema"] == "sos-w15-gate-report/1.0"
    assert report["repoHead"] == TIP
    assert report["commands"] == {
        "pytest": {"exitCode": 0, "passed": 120},
        "compileall": {"exitCode": 0},
    }
    assert [c["id"] for c in report["checks"]] == [
        f"G{i:02d}" for i in range(1, 13)
    ]
    for entry in report["checks"]:
        assert set(entry) == {"id", "title", "area", "status", "details"}
    assert report["overall"] == "PASS"


# ---------------------------------------------------------------------------
# G01 — frozen authority integrity
# ---------------------------------------------------------------------------


def test_g01_detects_frozen_document_drift(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "spec/constitution.md").write_text(
        "silently rewritten constitution\n", encoding="utf-8"
    )
    result = assert_targeted(run_checks(root, baseline), "G01")
    assert "!=" in result.details and "constitution.md" in result.details


def test_g01_detects_missing_frozen_document(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "spec/architecture-lock.md").unlink()
    result = assert_targeted(run_checks(root, baseline), "G01")
    assert "missing frozen authority document" in result.details


# ---------------------------------------------------------------------------
# G02 — module surface conformance
# ---------------------------------------------------------------------------


def test_g02_detects_extra_module(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "src" / "sos" / "rogue_authority.py").write_text(
        '"""A fifth authority — must be detected."""\n', encoding="utf-8"
    )
    result = assert_targeted(run_checks(root, baseline), "G02")
    assert "rogue_authority.py" in result.details


def test_g02_detects_missing_module(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "src" / "sos" / "assurance.py").unlink()
    result = assert_targeted(run_checks(root, baseline), "G02")
    assert "assurance.py" in result.details and "missing" in result.details


# ---------------------------------------------------------------------------
# G03 — requirements covered
# ---------------------------------------------------------------------------


def test_g03_detects_uncovered_requirement(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    # R10 is owned by exactly one Work Order in the fixture distribution
    # (W12's R6–R15 range); removing it from that range uncovers it.
    rewrite(
        root / fgc.WORK_ORDER_FILES["W12"],
        lambda t: t.replace("R1, R6–R15, R18, R22–R24", "R1, R6–R9, R11–R15, R18, R22–R24"),
    )
    result = assert_targeted(run_checks(root, baseline), "G03")
    assert "R10" in result.details and "no Work-Order" in result.details


def test_g03_detects_missing_w14_mapping_requirement(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / fgc.DESIGN_FILES["W14"],
        lambda t: t.replace("R10 by the causal stage; ", ""),
    )
    result = assert_targeted(run_checks(root, baseline), "G03")
    assert "W14 verification mapping" in result.details and "R10" in (
        result.details
    )


def test_g03_detects_task_set_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root,
        lambda s: s["tasks"].update(
            {"W16": {"status": "READY", "dependencies": [], "mergedAs": None}}
        ),
    )
    result = assert_targeted(run_checks(root, baseline), "G03")
    assert "task set" in result.details


def test_g03_detects_roadmap_row_without_complete_merge(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root,
        lambda s: s["tasks"]["W7"].update(status="DISPATCHED", mergedAs=None),
    )
    # Removing W7's merge also breaks its dependents' dependency edges
    # (W8/W9/W12 depend on W7) — an honest G05 cascade.
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G03", "G05", "G11"}
    assert "W7" in results["G03"].details
    assert "COMPLETE task with a merge" in results["G03"].details


# ---------------------------------------------------------------------------
# G04 — state vs Git
# ---------------------------------------------------------------------------


def test_g04_detects_dangling_merge_sha(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)

    def mutate(s: dict) -> None:
        s["tasks"]["W15"] = {
            "status": "COMPLETE",
            "dependencies": [],
            "mergedAs": DANGLING,
        }

    write_impl_state(root, mutate)
    result = assert_targeted(run_checks(root, baseline), "G04")
    assert "does not resolve (dangling)" in result.details


def test_g04_detects_complete_task_without_merge(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)

    def mutate(s: dict) -> None:
        s["tasks"]["W15"] = {
            "status": "COMPLETE",
            "dependencies": [],
            "mergedAs": None,
        }

    write_impl_state(root, mutate)
    result = assert_targeted(run_checks(root, baseline), "G04")
    assert "COMPLETE without a valid 40-hex mergedAs" in result.details


def test_g04_detects_mergeless_complete_row_double_detection(
    tmp_path: Path,
) -> None:
    # A W1–W14 row that claims COMPLETE without a merge is detected by BOTH
    # G03 (roadmap ledger row completeness) and G04 (state-vs-Git) —
    # intentional redundant detection; G05 stays green because the variant
    # removes the dependents' edges.
    root = tmp_path / "repo"
    baseline = build_fixture(root)

    def mutate(s: dict) -> None:
        s["tasks"]["W14"].update(status="COMPLETE", mergedAs=None)
        s["tasks"]["W15"].update(dependencies=[])

    write_impl_state(root, mutate)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(
            last_completed="W13",
            last_merge=M[13],
            machine_line=(
                "`spec/development-state/implementation-state.json` → "
                "`W15_READY_TO_DISPATCH`, `currentFrontier = [\"W15\"]`, "
                f"`W13 = COMPLETE/{M[13]}` (verified current)"
            ),
        ),
        encoding="utf-8",
    )
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G03", "G04", "G11"}
    assert "W14" in results["G03"].details
    assert "W14: COMPLETE without a valid 40-hex mergedAs" in (
        results["G04"].details
    )


def test_g04_detects_duplicate_merges(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root, lambda s: s["tasks"]["W13"].update(mergedAs=M[14])
    )
    result = assert_targeted(run_checks(root, baseline), "G04")
    assert "duplicates" in result.details


def test_g04_detects_non_complete_task_with_merge(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root, lambda s: s["tasks"]["W15"].update(mergedAs=M[14])
    )
    result = assert_targeted(run_checks(root, baseline), "G04")
    assert "mergedAs is not null" in result.details


def test_g04_w0_bootstrap_dangling_cascades(tmp_path: Path) -> None:
    # W0's merge is W1's dependency edge and part of the program-ancestry
    # clause, so a dangling bootstrapCommit honestly cascades to G05.
    root = tmp_path / "repo"
    baseline = build_fixture(root)

    def mutate(s: dict) -> None:
        s["tasks"]["W0"].update(bootstrapCommit=DANGLING)
        s["tasks"]["W1"].update(dependencies=[])

    write_impl_state(root, mutate)
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G04", "G05", "G11"}
    assert "W0 bootstrapCommit does not resolve" in results["G04"].details


def test_g04_detects_stale_checkpoint_head_vs_merge(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W5-checkpoint.md",
        lambda t: t.replace(M[5], H15),
    )
    result = assert_targeted(run_checks(root, baseline), "G04")
    assert "is not ancestral to its merge" in result.details


def test_g04_records_squash_era_pr_head_exemption(tmp_path: Path) -> None:
    # A review-head reference that resolves, under a single-parent (squash)
    # merge topology, is lawful and RECORDED (not silently passed).
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W2-checkpoint.md",
        lambda t: t.replace(
            f"**Exact implementation head:** `{M[2]}`",
            f"**Review head SHA:** `{R2F}`",
        ),
    )
    results = run_checks(root, baseline)
    assert results["G04"].status == fgc.STATUS_PASS
    assert "§2" in results["G04"].details and R2F[:8] in results["G04"].details
    assert results["G08"].status == fgc.STATUS_PASS


def test_g04_review_head_reference_requires_single_parent_topology(
    tmp_path: Path,
) -> None:
    # The same review-head reference under a TRUE merge (two parents) is a
    # stale-head claim, not the §2 convention.
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W2-checkpoint.md",
        lambda t: t.replace(
            f"**Exact implementation head:** `{M[2]}`",
            f"**Review head SHA:** `{R2F}`",
        ),
    )
    dag = dict(DAG)
    dag[M[2]] = (M[1], XNODE)  # M2 becomes a true merge
    results = run_checks(root, baseline, dag=dag)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G04", "G08", "G11"}
    assert "true merge" in results["G04"].details


def test_g04_review_head_reference_must_resolve(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W2-checkpoint.md",
        lambda t: t.replace(
            f"**Exact implementation head:** `{M[2]}`",
            f"**Review head SHA:** `{DANGLING}`",
        ),
    )
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G04", "G08", "G11"}


# ---------------------------------------------------------------------------
# G05 — dependency ancestry
# ---------------------------------------------------------------------------


def test_g05_detects_non_ancestor_dependency(tmp_path: Path) -> None:
    # SIDE is merged late (at M12): ancestral of HEAD but NOT of W6's merge.
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root, lambda s: s["tasks"]["W5"].update(mergedAs=SIDE)
    )
    rewrite(
        root / "spec/development-state/W5-checkpoint.md",
        lambda t: t.replace(M[5], SIDE),
    )
    result = assert_targeted(run_checks(root, baseline), "G05")
    assert "NOT an ancestor of the task merge" in result.details


def test_g05_detects_unresolvable_dependency_merge(tmp_path: Path) -> None:
    # A dangling dependency merge is both a state-vs-Git defect (G04) and a
    # dependency-resolution defect (G05) — intentional double detection.
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root, lambda s: s["tasks"]["W13"].update(mergedAs=DANGLING)
    )
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G04", "G05", "G11"}
    assert "W13: mergedAs" in results["G04"].details
    assert "W14<-W13" in results["G05"].details
    assert "does not" in results["G05"].details


def test_g05_w15_clause_dependencies_ancestral_to_reviewed_head(
    tmp_path: Path,
) -> None:
    # W15 is READY (no merge): every dependency merge must be ancestral to
    # the reviewed head — exercised by every green run; here the W14 side
    # branch (merged late) still satisfies W15's clause but breaks W14's own
    # dependency edges (W10's merge is not an ancestor of SIDE).
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    write_impl_state(
        root, lambda s: s["tasks"]["W14"].update(mergedAs=SIDE)
    )
    rewrite(
        root / "spec/development-state/W14-checkpoint.md",
        lambda t: t.replace(M[14], SIDE),
    )
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(last_merge=SIDE),
        encoding="utf-8",
    )
    results = run_checks(root, baseline)
    assert results["G05"].status == fgc.STATUS_FAIL
    assert "W14<-W10" in results["G05"].details
    assert "NOT an ancestor of the task merge" in results["G05"].details


# ---------------------------------------------------------------------------
# G06 — suite green
# ---------------------------------------------------------------------------


def test_g06_deferred_without_command_results(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    results = run_checks(root, baseline, commands=None, report_mode=False)
    assert results["G06"].status == fgc.STATUS_DEFERRED
    assert "check-only" in results["G06"].details


@pytest.mark.parametrize(
    "commands",
    [
        fgc.CommandResults(1, 120, 0),
        fgc.CommandResults(0, 99, 0),
        fgc.CommandResults(0, None, 0),
        fgc.CommandResults(0, 120, 2),
    ],
    ids=["pytest-exit", "count-regression", "count-unparseable", "compileall"],
)
def test_g06_detects_command_failures(
    tmp_path: Path, commands: fgc.CommandResults
) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    result = assert_targeted(run_checks(root, baseline, commands=commands), "G06")
    assert result.details


def test_g06_threshold_is_parsed_from_the_w14_checkpoint(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    # Recorded count 100: 100 passed passes; 99 fails.
    ok = run_checks(
        root, baseline,
        commands=fgc.CommandResults(0, 100, 0),
    )
    assert ok["G06"].status == fgc.STATUS_PASS
    assert "W14 checkpoint recorded count 100" in ok["G06"].details
    short = run_checks(
        root, baseline,
        commands=fgc.CommandResults(0, 99, 0),
    )
    assert short["G06"].status == fgc.STATUS_FAIL


def test_g06_falls_back_to_dispatch_baseline(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W14-checkpoint.md",
        lambda t: t.replace("Exact pass count: **100**\n", ""),
    )
    results = run_checks(root, baseline)
    assert results["G06"].status == fgc.STATUS_FAIL
    assert "dispatch baseline" in results["G06"].details


# ---------------------------------------------------------------------------
# G07 — adversarial evidence
# ---------------------------------------------------------------------------


def test_g07_detects_missing_matrix_case(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    matrix = _matrix_dict()
    matrix["rows"] = [r for r in matrix["rows"] if r["caseId"] != "ADV-07-mismatched-revisions"]
    (root / fgc.W14_MATRIX_PATH).write_text(
        json.dumps(matrix, indent=1), encoding="utf-8"
    )
    result = assert_targeted(run_checks(root, baseline), "G07")
    assert "ADV-07-mismatched-revisions" in result.details


def test_g07_detects_non_pass_verdict(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    matrix = _matrix_dict()
    matrix["rows"][2]["verdict"] = "FAIL"
    (root / fgc.W14_MATRIX_PATH).write_text(
        json.dumps(matrix, indent=1), encoding="utf-8"
    )
    result = assert_targeted(run_checks(root, baseline), "G07")
    assert "ADV-03" in result.details and "FAIL" in result.details


def test_g07_detects_stale_matrix_repo_head(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    matrix = _matrix_dict()
    matrix["repoHead"] = R2F  # resolvable, but NOT ancestral of TIP
    (root / fgc.W14_MATRIX_PATH).write_text(
        json.dumps(matrix, indent=1), encoding="utf-8"
    )
    result = assert_targeted(run_checks(root, baseline), "G07")
    assert "not an ancestor of HEAD" in result.details


def test_g07_detects_wrong_schema(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    matrix = _matrix_dict()
    matrix["schema"] = "sos-w14-adversarial-evidence-matrix/0.9"
    (root / fgc.W14_MATRIX_PATH).write_text(
        json.dumps(matrix, indent=1), encoding="utf-8"
    )
    assert_targeted(run_checks(root, baseline), "G07")


def test_g07_detects_unparseable_matrix(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.W14_MATRIX_PATH).write_text("{not json", encoding="utf-8")
    # G12 also requires the matrix component — a documented cascade.
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert failures == {"G07", "G11", "G12"}
    assert "unreadable" in results["G07"].details


# ---------------------------------------------------------------------------
# G08 — checkpoints current
# ---------------------------------------------------------------------------


def test_g08_detects_missing_checkpoint(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "spec/development-state/W6-checkpoint.md").unlink()
    results = run_checks(root, baseline)
    failures = {
        k for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    # G09 (the checkpoint is W6's rollback-declaration carrier) and G12 (the
    # checkpoint chain) also fail — documented cascades.
    assert failures == {"G08", "G09", "G11", "G12"}
    assert "missing checkpoint" in results["G08"].details


def test_g08_detects_stale_unreachable_checkpoint_head(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    # W15 has no merge, so its head claim is checked directly against HEAD:
    # R2F resolves but is not ancestral of the reviewed head.
    rewrite(
        root / "spec/development-state/W15-checkpoint.md",
        lambda t: t.replace(H15, R2F),
    )
    result = assert_targeted(run_checks(root, baseline), "G08")
    assert "stale-head completion claim" in result.details


def test_g08_detects_dangling_checkpoint_head(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W15-checkpoint.md",
        lambda t: t.replace(H15, DANGLING),
    )
    result = assert_targeted(run_checks(root, baseline), "G08")
    assert "dangling SHA" in result.details


def test_g08_detects_checkpoint_without_head_claim(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W4-checkpoint.md",
        lambda t: t.replace(
            f"**Exact implementation head:** `{M[4]}`\n", ""
        ),
    )
    result = assert_targeted(run_checks(root, baseline), "G08")
    assert "records no head SHA" in result.details


def test_g08_records_dangling_narrative_citation_observation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W9-checkpoint.md",
        lambda t: t
        + f"\nA narrative note cites `{DANGLING}` outside any claim label.\n",
    )
    results = run_checks(root, baseline)
    assert results["G08"].status == fgc.STATUS_PASS
    assert DANGLING[:8] in results["G08"].details
    assert "observation" in results["G08"].details


def test_g08_detects_stale_base_sha(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W7-checkpoint.md",
        lambda t: t.replace(M[6], R2F),
    )
    result = assert_targeted(run_checks(root, baseline), "G08")
    assert "stale base claim" in result.details


# ---------------------------------------------------------------------------
# G09 — rollback safety
# ---------------------------------------------------------------------------


def test_g09_detects_missing_rollback_declaration(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W8-checkpoint.md",
        lambda t: t.replace(
            "## Risk / rollback\n\n"
            "- **Risk:** fixture risk statement.\n"
            "- **Rollback:** ordinary Git revert of the W8 PR. No data "
            "migration, no running service.\n",
            "## Risk\n\nRisk is governed at review.\n",
        ),
    )
    result = assert_targeted(run_checks(root, baseline), "G09")
    assert "no rollback declaration heading" in result.details


def test_g09_detects_declaration_without_mechanism(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W3-checkpoint.md",
        lambda t: t.replace(
            "- **Rollback:** ordinary Git revert of the W3 PR. No data "
            "migration, no running service.",
            "- **Rollback:** handled by the governing process at review "
            "time.",
        ),
    )
    result = assert_targeted(run_checks(root, baseline), "G09")
    assert "no mechanism statement" in result.details


def test_g09_detects_missing_scope_exclusion(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W2-checkpoint.md",
        lambda t: t.replace(
            "No runtime architecture recovery, telemetry ingestion, "
            "causal memory, candidate search/ranking, assurance engine, "
            "experimentation execution, promotion/rollback, or "
            "architecture/meta-model changes.",
            "W2 adds pure domain modules only.",
        ),
    )
    result = assert_targeted(run_checks(root, baseline), "G09")
    assert "scope-exclusion" in result.details


def test_g09_detects_deployment_artifact(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    deploy = root / "deploy" / "k8s" / "manifest.yaml"
    deploy.parent.mkdir(parents=True)
    deploy.write_text("apiVersion: v1\n", encoding="utf-8")
    result = assert_targeted(run_checks(root, baseline), "G09")
    assert "k8s/manifest.yaml" in result.details


def test_g09_overlay_prefix_exempts_governed_overlay_paths(
    tmp_path: Path,
) -> None:
    """PUB-01 G09 overlay-prefix reconciliation: deployment-shaped paths
    INSIDE the governed overlay roots (db/migrations/, the future Apify actor
    Dockerfile, ...) are exempt by design — the contract §D PUB-01 allowlist
    (spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md) governs them instead."""
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    overlay_paths = (
        root / "db" / "migrations" / "0001_init.sql",
        root / "db" / "migrations" / "0002_jobs.sql",
        root / "infra" / "apify" / "Dockerfile",
        root / "services" / "api" / "docker-compose.yml",
    )
    for path in overlay_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("-- overlay fixture\n", encoding="utf-8")
    results = run_checks(root, baseline)
    assert results["G09"].status == fgc.STATUS_PASS
    assert "frozen surface of the repository tree" in results["G09"].details
    assert (
        "governed by "
        "spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md" in results["G09"].details
    )


def test_g09_overlay_prefix_scoping_is_exact(tmp_path: Path) -> None:
    """A pattern-matching path OUTSIDE the overlay prefixes still fails G09 —
    the exemption is prefix-scoped (no global relaxation), and a
    deceptively-named non-prefix path (e.g. ``dbx/`` vs ``db/``) is caught."""
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    exempt = root / "db" / "migrations" / "0001_init.sql"
    exempt.parent.mkdir(parents=True)
    exempt.write_text("-- overlay fixture\n", encoding="utf-8")
    intruder = root / "dbx" / "migrations" / "evil.sql"
    intruder.parent.mkdir(parents=True)
    intruder.write_text("-- frozen-surface intrusion\n", encoding="utf-8")
    result = assert_targeted(run_checks(root, baseline), "G09")
    assert "dbx/migrations/evil.sql" in result.details
    assert "db/migrations/0001_init.sql" not in result.details


# ---------------------------------------------------------------------------
# G10 — docs reconciled
# ---------------------------------------------------------------------------


def test_g10_detects_last_completed_sha_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(last_merge=M[13]),  # wrong merge for W14
        encoding="utf-8",
    )
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "!= ledger mergedAs" in result.details


def test_g10_detects_dangling_live_main_citation(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(
            live_line=f"recompute from live Git — milestone `{DANGLING}`"
        ),
        encoding="utf-8",
    )
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "does not resolve" in result.details


def test_g10_detects_stale_literal_live_main_sha(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(live_line=f"`{M[13]}`"),
        encoding="utf-8",
    )
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "stale literal recording" in result.details


def test_g10_detects_two_wave_lag(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(
            last_completed="W12",
            last_merge=M[12],
            frontier="W14",
            machine_line=(
                "`spec/development-state/implementation-state.json` → "
                "`W15_READY_TO_DISPATCH`, `currentFrontier = [\"W14\"]`, "
                f"`W12 = COMPLETE/{M[12]}` (verified current)"
            ),
        ),
        encoding="utf-8",
    )
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "lags" in result.details


def test_g10_detects_ahead_of_ledger_completion_claim(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(last_completed="W15", last_merge=M[14]),
        encoding="utf-8",
    )
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "AHEAD of the ledger" in result.details


def test_g10_detects_missing_design_doc(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.DESIGN_FILES["W7"]).unlink()
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "missing design doc" in result.details


def test_g10_detects_missing_work_order(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.WORK_ORDER_FILES["W9"]).unlink()
    result = assert_targeted(run_checks(root, baseline), "G10")
    assert "missing Work Order" in result.details


def test_g10_records_one_wave_open_program_lag_as_pass(tmp_path: Path) -> None:
    # The repository's actual dispatch-time situation: the human-readable
    # projection lags the machine ledger by exactly one wave because the
    # merge reconciliation updates the projection AFTER the merge. G10
    # passes with the lag RECORDED and flagged for the Architect.
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(
            last_completed="W13",
            last_merge=M[13],
            frontier="W14",
            machine_line=(
                "`spec/development-state/implementation-state.json` → "
                "`W14_READY_TO_DISPATCH`, `currentFrontier = [\"W14\"]`, "
                f"`W13 = COMPLETE/{M[13]}` (verified current)"
            ),
        ),
        encoding="utf-8",
    )
    results = run_checks(root, baseline)
    assert results["G10"].status == fgc.STATUS_PASS
    details = results["G10"].details
    assert "lags ledger by one wave" in details
    assert "REVIEW-TIME FLAG" in details
    assert "final reconciliation commit closes it" in details


def test_g10_terminal_state_strict_equality(tmp_path: Path) -> None:
    # After the final reconciliation commit: ROADMAP_COMPLETE, W15 merged,
    # empty frontier, and the projection must match field-by-field.
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    m15 = sha(150)  # the true W15 merge

    def mutate(s: dict) -> None:
        s["status"] = "ROADMAP_COMPLETE"
        s["tasks"]["W15"] = {
            "status": "COMPLETE",
            "dependencies": ["W14"],
            "mergedAs": m15,
        }
        s["currentFrontier"] = []
        s["currentTask"] = None

    write_impl_state(root, mutate)
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(
            last_completed="W15",
            last_merge=m15,
            frontier="none (roadmap complete)",
            live_line=(
                f"recompute from live Git — the final W15 merge is `{m15}`; "
                "the final reconciliation commit advances `main` beyond it "
                "without changing any frozen semantics"
            ),
            machine_line=(
                "`spec/development-state/implementation-state.json` → "
                "`ROADMAP_COMPLETE`, `currentFrontier = []`"
            ),
        ),
        encoding="utf-8",
    )
    dag = dict(DAG)
    dag[m15] = (M[14], H15)
    dag[TIP] = (m15,)
    results = run_checks(root, baseline, dag=dag)
    assert results["G10"].status == fgc.STATUS_PASS
    assert "TERMINAL strict field equality enforced" in results["G10"].details


def test_g10_terminal_state_detects_stale_projection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    m15 = sha(150)

    def mutate(s: dict) -> None:
        s["status"] = "ROADMAP_COMPLETE"
        s["tasks"]["W15"] = {
            "status": "COMPLETE",
            "dependencies": ["W14"],
            "mergedAs": m15,
        }
        s["currentFrontier"] = []
        s["currentTask"] = None

    write_impl_state(root, mutate)
    # The projection still names W14 as last completed — stale at terminal.
    (root / fgc.CURRENT_STATE_PATH).write_text(
        _current_state_text(
            last_completed="W14",
            last_merge=M[14],
            frontier="none (roadmap complete)",
            machine_line=(
                "`spec/development-state/implementation-state.json` → "
                "`ROADMAP_COMPLETE`, `currentFrontier = []`"
            ),
        ),
        encoding="utf-8",
    )
    dag = dict(DAG)
    dag[m15] = (M[14], H15)
    dag[TIP] = (m15,)
    results = run_checks(root, baseline, dag=dag)
    assert results["G10"].status == fgc.STATUS_FAIL
    assert "terminal state" in results["G10"].details


# ---------------------------------------------------------------------------
# G11 — fresh-agent recoverability (mechanical proxy)
# ---------------------------------------------------------------------------


def test_g11_detects_missing_bootstrap_artifact(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "ARCHITECT_START_HERE.md").unlink()
    result = assert_targeted(run_checks(root, baseline), "G11")
    assert "ARCHITECT_START_HERE.md" in result.details


def test_g11_composites_the_prior_check_verdicts(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    (root / "src" / "sos" / "rogue.py").write_text("x = 1\n", encoding="utf-8")
    results = run_checks(root, baseline)
    assert results["G11"].status == fgc.STATUS_FAIL
    assert "G02" in results["G11"].details
    assert "mechanical recovery chain broken" in results["G11"].details


# ---------------------------------------------------------------------------
# G12 — sign-off packet readiness
# ---------------------------------------------------------------------------


def test_g12_detects_missing_command_citations(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    rewrite(
        root / "spec/development-state/W15-checkpoint.md",
        lambda t: t.replace("python3 -m pytest", "the suite"),
    )
    result = assert_targeted(run_checks(root, baseline), "G12")
    assert "pytest" in result.details


def test_g12_detects_missing_report_in_check_only_mode(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root, include_report_file=False)
    results = run_checks(root, baseline, report_mode=False)
    assert results["G12"].status == fgc.STATUS_FAIL
    assert "gate report file absent" in results["G12"].details


def test_g12_accepts_report_produced_by_this_run(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root, include_report_file=False)
    results = run_checks(root, baseline, report_mode=True)
    assert results["G12"].status == fgc.STATUS_PASS
    assert "produced by this run" in results["G12"].details


# ---------------------------------------------------------------------------
# Determinism, read-only behavior, injection boundary
# ---------------------------------------------------------------------------


def _write_gate_report(
    root: Path, baseline: fgc.Baseline, out: Path
) -> None:
    resolver = FakeResolver(DAG, TIP)
    state = fgc.load_state(
        root,
        baseline=baseline,
        commands=FAKE_COMMANDS,
        report_mode=True,
        report_path=out,
    )
    results, overall = fgc.run_gate(state, resolver)
    report = fgc.build_report(TIP, results, FAKE_COMMANDS, overall)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_report_is_deterministic_over_identical_state(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)
    out = tmp_path / "gate-report.json"
    # The first write initializes the report file (a state change: the G12
    # details record "produced by this run"); the comparison runs execute
    # over the identical post-initialization state and must be
    # byte-identical (the G12 details then record "present at the report
    # path").
    _write_gate_report(root, baseline, out)
    _write_gate_report(root, baseline, out)
    second = out.read_bytes()
    _write_gate_report(root, baseline, out)
    third = out.read_bytes()
    assert second == third
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["overall"] == fgc.STATUS_PASS
    assert payload["repoHead"] == TIP
    assert payload["commands"]["pytest"]["passed"] == 120


def test_check_logic_requires_zero_subprocesses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    baseline = build_fixture(root)

    def poisoned(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("check logic must not launch subprocesses")

    monkeypatch.setattr(fgc.subprocess, "run", poisoned)
    results = run_checks(root, baseline)
    assert all(r.status == fgc.STATUS_PASS for r in results.values()), {
        k: r.details for k, r in results.items()
    }


# ---------------------------------------------------------------------------
# The GitResolver adapter (the only Git-touching code), against a temp repo
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "commit", "--allow-empty", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def test_git_resolver_adapter_against_a_temp_repository(
    tmp_path: Path,
) -> None:
    root = tmp_path / "gitrepo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "w15-test")
    _git(root, "config", "user.email", "w15@example.invalid")
    base = _commit(root, "base")
    child = _commit(root, "child")
    _git(root, "checkout", "-q", "-b", "side", base)
    side = _commit(root, "side")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "--no-ff", "-q", "-m", "merge side", side)
    merge = _git(root, "rev-parse", "HEAD")

    resolver = fgc.GitResolver(root)
    assert resolver.head() == merge
    assert resolver.exists(base) and resolver.exists(child)
    assert resolver.exists(side) and resolver.exists(merge)
    assert not resolver.exists(DANGLING)
    assert resolver.is_ancestor(base, merge)
    assert resolver.is_ancestor(side, merge)
    assert resolver.is_ancestor(base, base)  # ancestor-or-equal semantics
    assert not resolver.is_ancestor(child, side)
    assert not resolver.is_ancestor(merge, child)
    assert not resolver.is_ancestor(DANGLING, merge)
    parents = resolver.parents(merge)
    assert len(parents) == 2
    assert side in parents and child in parents
    assert resolver.parents(base) == ()  # a root commit has no parents
    assert resolver.head() and re.fullmatch(r"[0-9a-f]{40}", resolver.head())


# ---------------------------------------------------------------------------
# CLI end-to-end (check-only; report mode with a real passing micro-suite)
# ---------------------------------------------------------------------------


def _make_git_fixture(
    tmp_path: Path, name: str, *, use_real_frozen_docs: bool = True
) -> tuple[Path, fgc.Baseline]:
    """A real temporary Git repository whose commit chain matches the
    fixture's recorded revisions (c0..c14 as the wave merges, an unmerged
    w1-review sibling for the §2 PR-head convention, h15 as the W15
    implementation head, and the fixture tree committed as the tip)."""
    root = tmp_path / name
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "w15-test")
    _git(root, "config", "user.email", "w15@example.invalid")
    c0 = _commit(root, "W0 bootstrap")
    _git(root, "checkout", "-q", "-b", "w1-review", c0)
    r1f = _commit(root, "W1 reviewed PR head (unmerged sibling)")
    _git(root, "checkout", "-q", "main")
    merges = [c0]
    for n in range(1, 15):
        merges.append(_commit(root, f"W{n} merge"))
    h15 = _commit(root, "W15 implementation head")
    sha_map = {R1F: r1f, H15: h15}
    sha_map.update({M[n]: merges[n] for n in range(15)})
    baseline = build_fixture(
        root,
        use_real_frozen_docs=use_real_frozen_docs,
        sha_map=sha_map,
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture repository state")
    return root, baseline


def test_cli_check_only_is_read_only_and_exits_zero(
    tmp_path: Path,
) -> None:
    root, _baseline = _make_git_fixture(tmp_path, "clirepo")
    tree_before = _git(root, "rev-parse", "HEAD^{tree}")
    files_before = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git/" not in str(p.relative_to(root))
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "final_gate_check.py"),
            "--root",
            str(root),
            "--check-only",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    tree_after = _git(root, "rev-parse", "HEAD^{tree}")
    files_after = sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git/" not in str(p.relative_to(root))
    )
    assert tree_before == tree_after
    assert files_before == files_after
    for check_id in (f"G{i:02d}" for i in range(1, 13)):
        assert f"{check_id} " in proc.stdout
    assert "OVERALL (check-only): PASS" in proc.stdout
    assert "DEFERRED" in proc.stdout


def test_cli_report_mode_end_to_end(tmp_path: Path) -> None:
    root, _baseline = _make_git_fixture(tmp_path, "reportrepo")
    # A real micro-suite so the G06 subprocess evidence is genuinely green,
    # with the W14 checkpoint recording a matching threshold of 1.
    tests_dir = root / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_fixture_smoke.py").write_text(
        "def test_fixture_ok() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    rewrite(
        root / "spec/development-state/W14-checkpoint.md",
        lambda t: t.replace("Exact pass count: **100**", "Exact pass count: **1**"),
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "add micro-suite")
    report_path = root / fgc.DEFAULT_REPORT_PATH
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "final_gate_check.py"),
            "--root",
            str(root),
            "--report",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(root),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OVERALL: PASS" in proc.stdout
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema"] == "sos-w15-gate-report/1.0"
    assert payload["repoHead"] == _git(root, "rev-parse", "HEAD")
    assert payload["commands"]["pytest"]["passed"] == 1
    assert payload["overall"] == fgc.STATUS_PASS
    assert [c["id"] for c in payload["checks"]] == [
        f"G{i:02d}" for i in range(1, 13)
    ]
    # Second run over the now-stable state is byte-identical.
    first = report_path.read_bytes()
    proc2 = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "final_gate_check.py"),
            "--root",
            str(root),
            "--report",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(root),
    )
    assert proc2.returncode == 0
    assert report_path.read_bytes() == first


def test_cli_exits_nonzero_on_gate_failure(tmp_path: Path) -> None:
    root, _baseline = _make_git_fixture(tmp_path, "failrepo")
    (root / "src" / "sos" / "rogue.py").write_text("x = 1\n", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "final_gate_check.py"),
            "--root",
            str(root),
            "--check-only",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 1
    assert "G02 MODULE_SURFACE_CONFORMANCE [architecture]: FAIL" in proc.stdout


def test_cli_rejects_non_repository_root(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "final_gate_check.py"),
            "--root",
            str(plain),
            "--check-only",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# Parser units
# ---------------------------------------------------------------------------


def test_expand_requirement_tokens() -> None:
    assert fgc.expand_requirement_tokens("R1–R5, R22–R23") == {
        "R1", "R2", "R3", "R4", "R5", "R22", "R23",
    }
    assert fgc.expand_requirement_tokens("R6/R7/R8 and R9/R21") == {
        "R6", "R7", "R8", "R9", "R21",
    }
    assert fgc.expand_requirement_tokens("R24 is dominant") == {"R24"}
    assert fgc.expand_requirement_tokens("R1—R3 em dash") == {
        "R1", "R2", "R3",
    }


def test_parse_checkpoint_claims_forms() -> None:
    text = (
        "# Wx checkpoint\n\n"
        "**Base SHA:** `aaaabbbbccccddddeeeeffff0000111122223333`\n"
        "**Review head SHA:** `1111222233334444555566667777888899990000`\n"
        "**Latest implementation SHA:** `2222333344445555666677778888999900001111`\n"
        "**Exact implementation head (contract code, exports, tests):**\n"
        "`3333444455556666777788889999000011112222`\n"
        "**Exact branch tip:** the commit carrying this checkpoint\n"
        "**Merge SHA:** `4444555566667777888899990000111122223333`\n"
        "A narrative citation `5555666677778888999900001111222233334444` "
        "outside any label.\n"
    )
    claims = fgc.parse_checkpoint_claims(text)
    by_label = {label: (kind, shas) for kind, label, shas, _ in claims}
    assert by_label["Base SHA:"][0] == "base"
    assert by_label["Review head SHA:"][1] == (
        "1111222233334444555566667777888899990000",
    )
    assert by_label["Latest implementation SHA:"][0] == "head"
    # Multi-line label: the SHA on the following line is claimed.
    assert by_label[
        "Exact implementation head (contract code, exports, tests):"
    ][1] == ("3333444455556666777788889999000011112222",)
    assert by_label["Merge SHA:"][0] == "merge"
    narrative = "5555666677778888999900001111222233334444"
    claimed = {sha for _, _, shas, _ in claims for sha in shas}
    assert narrative not in claimed


def test_parse_current_state_projection_fields() -> None:
    text = (
        "# SOS Current State\n\n"
        "## Repository State\n\n"
        "- Last Completed Work Order: `W14` (merge "
        "`aaaabbbbccccddddeeeeffff0000111122223333`, PR #21)\n"
        "- Live `main` SHA: recompute from live Git — the W14 merge is "
        "`bbbbeeeeccccddddeeeeffff0000111122223333`\n"
        "- Current frontier: `W15`\n"
        "- Machine state: `spec/development-state/implementation-state.json` "
        "→ `W15_READY_TO_DISPATCH`\n"
    )
    fields = fgc.parse_current_state_projection(text)
    assert "W14" in fields["last_completed"]
    assert "recompute" in fields["live_main"]
    assert fields["frontier"].strip("`") == "W15"
    assert "implementation-state.json" in fields["machine_state"]


def test_parse_roadmap_ledger_waves() -> None:
    waves = fgc.parse_roadmap_ledger_waves(_roadmap_text())
    assert waves == [f"W{i}" for i in range(16)]


# ---------------------------------------------------------------------------
# The shipped baseline vs the actual repository (self-verifying constants)
# ---------------------------------------------------------------------------


def test_shipped_baseline_matches_the_actual_repository() -> None:
    for rel, digest in fgc.FROZEN_DOC_DIGESTS.items():
        path = REPO_ROOT / rel
        assert path.is_file(), rel
        assert fgc.sha256_file(path) == digest, rel
    expected_modules = {
        name for mods in fgc.WAVE_MODULES.values() for name in mods
    }
    actual_modules = {
        p.name
        for p in (REPO_ROOT / "src" / "sos").glob("*.py")
        if p.name != "__init__.py"
    }
    assert actual_modules == expected_modules
    matrix = json.loads(
        (REPO_ROOT / fgc.W14_MATRIX_PATH).read_text(encoding="utf-8")
    )
    assert tuple(r["caseId"] for r in matrix["rows"]) == fgc.W14_CASE_IDS
    w14_checkpoint = (
        REPO_ROOT / "spec/development-state/W14-checkpoint.md"
    ).read_text(encoding="utf-8")
    assert fgc.parse_w14_recorded_count(w14_checkpoint) == (
        fgc.W14_BASELINE_TEST_COUNT
    )


def test_real_repository_gate_logic_with_git_resolver() -> None:
    """The real repository passes the machine checks (except the subprocess
    G06, deferred here) once the W15 artifacts are committed.

    Skipped at the implementation head, where the W15 checkpoint/report do
    not exist yet — at the branch tip (and after merge) this re-proves the
    committed gate report's verdicts through the real Git plumbing.
    """
    w15_checkpoint = REPO_ROOT / "spec/development-state/W15-checkpoint.md"
    if not w15_checkpoint.is_file():
        pytest.skip(
            "W15 checkpoint/report not committed at this branch state "
            "(implementation head)"
        )
    resolver = fgc.GitResolver(REPO_ROOT)
    state = fgc.load_state(
        REPO_ROOT, baseline=fgc.Baseline(), commands=None, report_mode=False
    )
    results_list, _overall = fgc.run_gate(state, resolver)
    results = {r.id: r for r in results_list}
    failures = {
        k: r.details for k, r in results.items() if r.status == fgc.STATUS_FAIL
    }
    assert not failures, failures
    deferred = [k for k, r in results.items() if r.status == fgc.STATUS_DEFERRED]
    assert deferred == ["G06"]
    assert results["G06"].status == fgc.STATUS_DEFERRED
    # G10 records the open-program projection lag explicitly (open state);
    # at the terminal ROADMAP_COMPLETE state (post-final-reconciliation
    # main, where the final reconciliation commit closed the recorded lag
    # and the ledger enforces strict field equality) the details carry the
    # terminal form instead. State-aware since 2026-10-01 (terminal-state
    # adaptation under post-merge Architect/TL authority — disclosed in
    # spec/development-state/W15-final-sign-off.md; expectation strength
    # preserved: exactly one of the two G10 detail forms must be present).
    _ledger_status = (state.impl_state or {}).get("status")
    if _ledger_status == "ROADMAP_COMPLETE":
        assert "TERMINAL strict field equality enforced" in results["G10"].details
    else:
        assert "lags ledger by one wave" in results["G10"].details
