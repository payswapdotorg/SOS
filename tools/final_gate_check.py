#!/usr/bin/env python3
"""W15 — the final architect gate: machine-checkable reconciliation checklist.

Repository tool (NOT SOS product code): never imported by ``src/sos/``, adds
no ``sos`` exports, lives under ``tools/`` per the W15 Work Order's allowed
surface. It implements the G01–G12 checklist mandated by
``spec/work-orders/W15-final-architect-gate.md`` (the normative Work Order)
and specified by ``docs/implementation/W15-FINAL-GATE-DESIGN.md`` §2; the
implemented contract (including every reconciliation of the prepared design
to the repository's actually recorded conventions) is documented in that
design doc §8+, extended by this Work Order — never weakened.

Design invariants (Work Order acceptance criteria C1–C10):

- OFFLINE, READ-ONLY, DETERMINISTIC, STDLIB-ONLY. No network, no clocks, no
  randomness; apart from writing its own report file the tool mutates
  nothing; two runs over identical repository state produce byte-identical
  reports (the pytest/compileall exit codes and parsed counts are the only
  environment-derived inputs, and both are stable for a fixed head).
- PURITY BOUNDARY: every primary check is a pure function
  ``check(state: GateState, resolver: RevisionResolver) -> CheckResult``;
  ``GateState`` is the parsed repository content plus the (injected) command
  results, and ``RevisionResolver`` is an injected protocol. The CLI wires a
  Git-backed resolver built exclusively from read-only plumbing
  (``rev-parse``, ``cat-file -t``, ``merge-base --is-ancestor``, ``log``);
  the tests wire an in-memory DAG resolver — so all check logic is testable
  with zero subprocesses, and the only Git-touching code is the thin
  resolver adapter (unit-tested separately against a temp git repository).
- G06 SUBPROCESS BOUNDARY: ``pytest``/``compileall`` are launched as local
  subprocesses from the repository root only in report mode (per design
  §3); a check-only run launches no subprocess and records G06 as DEFERRED.
- THE GATE NEVER APPROVES: PASS is mechanical evidence for the Architect's
  sign-off, never a substitute (SOS-IMPLEMENTATION-PROCESS §11
  "Reconciliation is bookkeeping and cannot approve or widen scope").
  Review-time-only items (the human zero-history walkthrough, the
  Architect-authored sign-off record, open-PR/PR-identity reconciliation)
  are explicitly marked in check details and in the stdout summary — they
  are named in the Work Order's sign-off protocol, never silently assumed
  mechanical.

Exit code: 0 iff every check passes (report mode); 0 iff no check FAILs
(check-only mode, G06 DEFERRED is tolerated); 1 on any FAIL; 2 on tool
misuse (unreadable repository root / no Git head).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

REPORT_SCHEMA = "sos-w15-gate-report/1.0"
DEFAULT_REPORT_PATH = "spec/development-state/W15-gate-report.json"

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_DEFERRED = "DEFERRED"

# ---------------------------------------------------------------------------
# Gate baseline (module-level constant table, Work Order / design §3)
#
# Frozen-document sha256 digests recorded at W15 dispatch from the verified
# repository facts at the dispatch base (live main AFTER the W14 merge,
# c04ddf1314ebda2c23467367099bfbe7b32972b5). The baseline records DATA; it
# authorizes nothing, and any change to it is a review-visible diff. The
# Architect verifies these digests against the frozen v1.0 documents at
# review (sign-off protocol step 2).
# ---------------------------------------------------------------------------

FROZEN_DOC_DIGESTS: dict[str, str] = {
    "spec/architecture.md":
        "c711b626d430f58046ae5532bd0c4bc30782a2d82248f84689e4f9a37cf7218d",
    "spec/architecture-lock.md":
        "83f88bd6de7e2a770911d77dc619fec7613593f87df76bfb154dd2269e219382",
    "spec/constitution.md":
        "3c1067f59fbdb8f818032a1a7c33a4ae127887aa0c25bbe740f382e52be4d63d",
    "spec/requirements.md":
        "21af44a902561788e09e36a9d9caab892647c3ab21565b12d1a022667427fd30",
    "spec/implementation-roadmap.md":
        "22d8d90afcfcd19828ac5104d324bc835c89c5abe181bb64ca33ef37e1cb0cff",
}

# The frozen per-wave module surface (design G02). W12/W13 modules are taken
# from their merged Work Orders' allowed surfaces (W12 optimization.py;
# W13 selfevolution.py); W14/W15 add no modules (verification/governance
# waves with no product surface).
WAVE_MODULES: dict[str, tuple[str, ...]] = {
    "W1": ("model.py",),
    "W2": ("graph.py",),
    "W3": ("recovery.py",),
    "W4": ("evidence.py",),
    "W5": ("causal.py",),
    "W6": ("candidates.py",),
    "W7": ("assurance.py",),
    "W8": ("experimentation.py",),
    "W9": ("autonomy.py",),
    "W10": ("personalization.py", "platform.py"),
    "W11": ("execution.py",),
    "W12": ("optimization.py",),
    "W13": ("selfevolution.py",),
    "W14": (),
    "W15": (),
}

# The sixteen W14 frozen adversarial case names, in the operator-mandated
# catalog order, in their persisted matrix realization
# (spec/development-state/W14-adversarial-evidence-matrix.json row ids).
W14_CASE_IDS: tuple[str, ...] = (
    "ADV-01-missing-evidence",
    "ADV-02-failed-evidence",
    "ADV-03-unknown-evidence",
    "ADV-04-unavailable-provider",
    "ADV-05-unsupported-capability",
    "ADV-06-forged-authority-references",
    "ADV-07-mismatched-revisions",
    "ADV-08-mismatched-candidates",
    "ADV-09-platform-widening-attempts",
    "ADV-10-provider-self-authorization",
    "ADV-11-ask-bypass-attempts",
    "ADV-12-rollback-bypass-attempts",
    "ADV-13-self-evolution-boundary-violations",
    "ADV-14-non-deterministic-outputs",
    "ADV-15-stale-state-recovery",
    "ADV-16-partial-failure-recovery",
)
W14_MATRIX_SCHEMA = "sos-w14-adversarial-evidence-matrix/1.0"
W14_MATRIX_PATH = "spec/development-state/W14-adversarial-evidence-matrix.json"
W14_CHECKPOINT_PATH = "spec/development-state/W14-checkpoint.md"

# Dispatch-time floor for the extend-never-weaken test-count rule (G06 also
# re-parses the W14 checkpoint's recorded count at run time and uses the
# parsed value when present; the constant is the verified fallback and a
# regression guard).
W14_BASELINE_TEST_COUNT = 478

# Per-wave Work Order / design-doc / checkpoint file names (existence
# reconciliation, G08/G10; the design-doc and Work-Order file names are
# recorded in the gate baseline per design G10).
WORK_ORDER_FILES: dict[str, str] = {
    "W1": "spec/work-orders/W1-mission-value-context-model.md",
    "W2": "spec/work-orders/W2-system-state-architecture-graph.md",
    "W3": "spec/work-orders/W3-architecture-recovery.md",
    "W4": "spec/work-orders/W4-evidence-observability.md",
    "W5": "spec/work-orders/W5-causal-knowledge-memory.md",
    "W6": "spec/work-orders/W6-candidate-generation-search.md",
    "W7": "spec/work-orders/W7-assurance-impact-analysis.md",
    "W8": "spec/work-orders/W8-experiment-promotion-rollback.md",
    "W9": "spec/work-orders/W9-autonomy-ask.md",
    "W10": "spec/work-orders/W10-personalization-platform.md",
    "W11": "spec/work-orders/W11-execution-substrate.md",
    "W12": "spec/work-orders/W12-optimization-loop.md",
    "W13": "spec/work-orders/W13-self-evolution.md",
    "W14": "spec/work-orders/W14-dogfood-adversarial-verification.md",
    "W15": "spec/work-orders/W15-final-architect-gate.md",
}
DESIGN_FILES: dict[str, str] = {
    "W1": "docs/implementation/W1-MISSION-VALUE-CONTEXT-DESIGN.md",
    "W2": "docs/implementation/W2-SYSTEM-STATE-ARCHITECTURE-GRAPH-DESIGN.md",
    "W3": "docs/implementation/W3-ARCHITECTURE-RECOVERY-DESIGN.md",
    "W4": "docs/implementation/W4-EVIDENCE-OBSERVABILITY-DESIGN.md",
    "W5": "docs/implementation/W5-CAUSAL-KNOWLEDGE-MEMORY-DESIGN.md",
    "W6": "docs/implementation/W6-CANDIDATE-GENERATION-SEARCH-DESIGN.md",
    "W7": "docs/implementation/W7-ASSURANCE-IMPACT-ANALYSIS-DESIGN.md",
    "W8": "docs/implementation/W8-EXPERIMENT-PROMOTION-ROLLBACK-DESIGN.md",
    "W9": "docs/implementation/W9-AUTONOMY-ASK-DESIGN.md",
    "W10": "docs/implementation/W10-PERSONALIZATION-PLATFORM-DESIGN.md",
    "W11": "docs/implementation/W11-EXECUTION-SUBSTRATE-DESIGN.md",
    "W12": "docs/implementation/W12-OPTIMIZATION-LOOP-DESIGN.md",
    "W13": "docs/implementation/W13-SELF-EVOLUTION-DESIGN.md",
    "W14": "docs/implementation/W14-DOGFOOD-ADVERSARIAL-DESIGN.md",
    "W15": "docs/implementation/W15-FINAL-GATE-DESIGN.md",
}

# Per-wave rollback-declaration carrier (design G09: "the checkpoint (or the
# wave's design doc, recorded in the gate baseline which file carries it)").
# W1/W2 predate the Risk/rollback checkpoint-heading convention (which
# crystallized at W3): their rollback-safety declaration takes the early-wave
# scope-exclusion form ("contains no runtime ... / No runtime ... changes"),
# which — combined with G02 (exactly the additive module surface) and G06
# (the suite green, including every wave's invariants) — demonstrates the
# same fact: the wave introduced nothing unrevertable, so ordinary Git
# revert is complete recovery.
ROLLBACK_CARRIERS: dict[str, tuple[str, str]] = {
    **{w: ("checkpoint", "rollback-section") for w in (
        "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11", "W12",
        "W13", "W14", "W15")},
    "W1": ("checkpoint", "scope-exclusion"),
    "W2": ("checkpoint", "scope-exclusion"),
}

# Repository-wide forbidden deployment/migration/network artifacts (G09's
# "no merged wave introduced deployment/migration/network state beyond its
# frozen surface"). Lowercase substrings matched against POSIX relative
# paths; .git/.github/__pycache__/.pytest_cache are excluded (CI workflow
# configuration is sanctioned repository machinery, not deployment state).
DEPLOYMENT_ARTIFACT_PATTERNS: tuple[str, ...] = (
    "dockerfile",
    "docker-compose",
    "terraform",
    ".tf",
    ".tfvars",
    "helm/",
    "k8s/",
    "kubernetes/",
    "migrations/",
    "alembic",
    ".sql",
)

REQUIREMENT_IDS: tuple[str, ...] = tuple(f"R{i}" for i in range(1, 25))
ROADMAP_LEDGER_WAVES: tuple[str, ...] = tuple(f"W{i}" for i in range(0, 16))
W0_TASK = "W0"
WAVES_W1_W15: tuple[str, ...] = tuple(f"W{i}" for i in range(1, 16))

# Fresh-agent bootstrap chain artifacts (G11 mechanical proxy).
BOOTSTRAP_ARTIFACTS: tuple[str, ...] = (
    "ARCHITECT_START_HERE.md",
    "AGENTS.md",
    "spec/development-state/README.md",
)

IMPLEMENTATION_STATE_PATH = "spec/development-state/implementation-state.json"
CURRENT_STATE_PATH = "spec/development-state/current-state.md"

SHA40_RE = re.compile(r"\b[0-9a-f]{40}\b")

# A checkpoint "claim line": a bold label whose text names a base / head /
# tip / merge / implementation-SHA revision claim (the repository's recorded
# conventions, W1–W15; the SHA may sit on the claim line itself or on the
# immediately following line — the W11–W15 multi-line form).
_CLAIM_LINE_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*(.+?)\*\*\s*:?\s*(.*)$")


def _claim_kind(label: str) -> str | None:
    low = label.lower()
    if "base" in low:
        return "base"
    if "merge" in low:
        return "merge"
    if "head" in low or "tip" in low:
        return "head"
    if "implementation" in low and "sha" in low:
        return "head"
    return None


# The review/PR-head reference convention (ARCHITECT-REVIEW-PROTOCOL §2: the
# exact PR head under review). A head claim that is not ancestral may be
# lawful ONLY under this convention AND only when the wave's merge is a
# single-parent commit (squash-era topology: the merge replays the branch
# content without containing the branch head).
_REVIEW_HEAD_REFERENCE_RE = re.compile(
    r"(?i)review(?:ed)?\s+head|pr\s+`?head\.sha|"
    r"architect-review-protocol\s*§\s*2|authoritative\s+review\s+head"
)

_ROLLBACK_HEADING_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*[^\n]*?\brisk\s*/\s*rollback\b[^\n]*"
    r"|#{1,6}\s*rollback\b[^\n]*"
    r"|[-*]\s*\*\*\s*rollback\s*\**\s*:)"
)
_ROLLBACK_MECHANISM_RE = re.compile(
    r"(?i)\brevert\b|\bgit\s+revert\b|recovery\s+is\s+complete|"
    r"revert\s+is\s+complete|removes?\s+(?:the\s+)?(?:mechanical\s+)?gate"
)
_SCOPE_EXCLUSION_RE = re.compile(
    r"(?im)^(?:[-*]\s*)?(?:W\d+\s+)?(?:intentionally\s+)?"
    r"(?:contains\s+no|no\s+runtime)\b.{0,400}\b(?:changes|execution)\b"
)

_W14_COUNT_RE = re.compile(r"(?i)exact\s+pass\s+count:\s*\*\*(\d+)\*\*")
_REQUIREMENTS_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?(?:Primary\s+)?[Rr]equirements(?:\*\*)?"
    r"\s*:\s*(.+)$"
)
_ROADMAP_LEDGER_ROW_RE = re.compile(r"(?im)^\|\s*(W\d+)\s*\|")
_CURRENT_STATE_FIELDS = {
    "live_main": re.compile(r"(?im)^-?\s*\**Live `main` SHA:\**\s*(.+)$"),
    "last_completed": re.compile(
        r"(?im)^-?\s*\**Last Completed Work Order:\**\s*(.+)$"
    ),
    "frontier": re.compile(r"(?im)^-?\s*\**Current frontier:\**\s*(.+)$"),
    "machine_state": re.compile(
        r"(?im)^-?\s*\**Machine state:\**\s*(.+)$"
    ),
}
_FRONTIER_NONE_RE = re.compile(r"(?i)\bnone\b|\bcomplete\b|\[\]|^—+$|^-$")


# ---------------------------------------------------------------------------
# Result/state types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    id: str
    title: str
    area: str
    status: str
    details: str


@dataclass(frozen=True)
class CommandResults:
    """Results of the exact-head verification commands (G06)."""

    pytest_exit: int | None
    pytest_passed: int | None
    compileall_exit: int | None
    note: str = ""

    @property
    def as_report(self) -> dict[str, object]:
        return {
            "pytest": {"exitCode": self.pytest_exit, "passed": self.pytest_passed},
            "compileall": {"exitCode": self.compileall_exit},
        }


@dataclass(frozen=True)
class Baseline:
    """The gate baseline table (design §3), injectable for tests."""

    frozen_doc_digests: Mapping[str, str] = field(
        default_factory=lambda: FROZEN_DOC_DIGESTS
    )
    wave_modules: Mapping[str, Sequence[str]] = field(
        default_factory=lambda: WAVE_MODULES
    )
    w14_case_ids: Sequence[str] = field(default_factory=lambda: W14_CASE_IDS)
    w14_matrix_schema: str = W14_MATRIX_SCHEMA
    w14_baseline_test_count: int = W14_BASELINE_TEST_COUNT
    work_order_files: Mapping[str, str] = field(
        default_factory=lambda: WORK_ORDER_FILES
    )
    design_files: Mapping[str, str] = field(
        default_factory=lambda: DESIGN_FILES
    )
    rollback_carriers: Mapping[str, tuple[str, str]] = field(
        default_factory=lambda: ROLLBACK_CARRIERS
    )
    deployment_artifact_patterns: Sequence[str] = field(
        default_factory=lambda: DEPLOYMENT_ARTIFACT_PATTERNS
    )
    requirement_ids: Sequence[str] = field(
        default_factory=lambda: REQUIREMENT_IDS
    )
    roadmap_ledger_waves: Sequence[str] = field(
        default_factory=lambda: ROADMAP_LEDGER_WAVES
    )
    w14_checkpoint_path: str = W14_CHECKPOINT_PATH
    w14_matrix_path: str = W14_MATRIX_PATH


@dataclass(frozen=True)
class GateState:
    """Parsed repository content plus injected command results."""

    root: Path
    baseline: Baseline
    impl_state: dict | None
    impl_state_error: str
    roadmap_text: str
    checkpoint_texts: dict[str, str]
    current_state_text: str
    matrix: dict | None
    matrix_error: str
    module_names: frozenset[str]
    work_order_texts: dict[str, str]
    w14_design_text: str
    w14_checkpoint_text: str
    commands: CommandResults | None
    report_mode: bool
    report_exists: bool
    repo_paths: tuple[str, ...]


def sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def wave_num(wave: str) -> int:
    m = re.fullmatch(r"W(\d+)", wave)
    return int(m.group(1)) if m else -1


def is_hex40(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value))


def short(sha: str) -> str:
    return sha[:8] if isinstance(sha, str) else str(sha)


def expand_requirement_tokens(text: str) -> set[str]:
    """Expand ``Rn`` tokens, ``Rn–Rm`` ranges and ``Rn/Rm`` slash pairs."""
    found: set[int] = set()
    for m in re.finditer(r"R(\d+)\s*[–—-]\s*R(\d+)", text):
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo <= hi and hi - lo < 200:
            found.update(range(lo, hi + 1))
    for m in re.finditer(r"(?:R(\d+)\s*/\s*)+R(\d+)", text):
        for g in m.groups():
            if g:
                found.add(int(g))
    for m in re.finditer(r"\bR(\d+)\b", text):
        found.add(int(m.group(1)))
    return {f"R{n}" for n in found}


def parse_checkpoint_claims(
    text: str,
) -> list[tuple[str, str, tuple[str, ...], str]]:
    """Extract ``(kind, label, shas, line_text)`` revision claims.

    A claim line is a bold label naming a base / head / tip / merge /
    implementation-SHA claim; the claimed 40-hex SHAs are those on the claim
    line plus the immediately following line (the W11–W15 multi-line form).
    ``line_text`` is the label plus both scanned lines — the ONLY text in
    which the review/PR-head reference convention (ARCHITECT-REVIEW-PROTOCOL
    §2) is recognized for a non-ancestral head claim.
    """
    lines = text.splitlines()
    claims: list[tuple[str, str, tuple[str, ...], str]] = []
    for i, line in enumerate(lines):
        m = _CLAIM_LINE_RE.match(line)
        if not m:
            continue
        label, rest = m.group(1), m.group(2)
        kind = _claim_kind(label)
        if kind is None:
            continue
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        shas = tuple(SHA40_RE.findall(rest)) or tuple(
            SHA40_RE.findall(next_line)
        )
        claims.append((kind, label, shas, label + " " + rest + " " + next_line))
    return claims


def parse_current_state_projection(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name, rx in _CURRENT_STATE_FIELDS.items():
        m = rx.search(text)
        fields[name] = m.group(1).strip() if m else ""
    return fields


def parse_roadmap_ledger_waves(roadmap_text: str) -> list[str]:
    section = ""
    marker = re.search(r"(?im)^##\s.*ledger.*$", roadmap_text)
    if marker:
        tail = roadmap_text[marker.end():]
        nxt = re.search(r"(?im)^##\s", tail)
        section = tail[: nxt.start()] if nxt else tail
    else:
        section = roadmap_text
    return _ROADMAP_LEDGER_ROW_RE.findall(section)


def parse_w14_recorded_count(w14_checkpoint_text: str) -> int | None:
    m = _W14_COUNT_RE.search(w14_checkpoint_text)
    return int(m.group(1)) if m else None


def _walk_repo_paths(root: Path) -> tuple[str, ...]:
    skip = {".git", ".github", "__pycache__", ".pytest_cache"}
    paths: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in skip for part in rel.parts):
            continue
        paths.append(rel.as_posix())
    return tuple(sorted(paths))


def load_state(
    root: Path,
    baseline: Baseline | None = None,
    commands: CommandResults | None = None,
    report_mode: bool = False,
    report_path: Path | None = None,
) -> GateState:
    """Parse repository content (pure file reads — no Git, no subprocess)."""
    baseline = baseline or Baseline()
    impl_state: dict | None = None
    impl_state_error = ""
    try:
        impl_state = json.loads(
            (root / IMPLEMENTATION_STATE_PATH).read_text(encoding="utf-8")
        )
    except OSError as exc:
        impl_state_error = f"{IMPLEMENTATION_STATE_PATH}: {exc}"
    except json.JSONDecodeError as exc:
        impl_state_error = f"{IMPLEMENTATION_STATE_PATH}: parse error: {exc}"

    checkpoint_texts = {
        w: read_text(root / f"spec/development-state/W{wave_num(w)}-checkpoint.md")
        for w in WAVES_W1_W15
    }
    matrix: dict | None = None
    matrix_error = ""
    try:
        matrix = json.loads(
            (root / baseline.w14_matrix_path).read_text(encoding="utf-8")
        )
    except OSError as exc:
        matrix_error = f"{baseline.w14_matrix_path}: {exc}"
    except json.JSONDecodeError as exc:
        matrix_error = f"{baseline.w14_matrix_path}: parse error: {exc}"

    module_names = frozenset(
        p.name
        for p in (root / "src" / "sos").glob("*.py")
        if p.name != "__init__.py"
    ) if (root / "src" / "sos").is_dir() else frozenset()

    work_order_texts = {
        w: read_text(root / rel) for w, rel in baseline.work_order_files.items()
    }
    resolved_report = report_path or (root / DEFAULT_REPORT_PATH)
    return GateState(
        root=root,
        baseline=baseline,
        impl_state=impl_state,
        impl_state_error=impl_state_error,
        roadmap_text=read_text(root / "spec/implementation-roadmap.md"),
        checkpoint_texts=checkpoint_texts,
        current_state_text=read_text(root / CURRENT_STATE_PATH),
        matrix=matrix,
        matrix_error=matrix_error,
        module_names=module_names,
        work_order_texts=work_order_texts,
        w14_design_text=read_text(
            root / (baseline.design_files.get("W14", ""))
        ) if baseline.design_files.get("W14") else "",
        w14_checkpoint_text=checkpoint_texts.get("W14", ""),
        commands=commands,
        report_mode=report_mode,
        report_exists=resolved_report.is_file(),
        repo_paths=_walk_repo_paths(root),
    )


# ---------------------------------------------------------------------------
# Revision resolver (the only Git-touching code) and command runner
# ---------------------------------------------------------------------------


class RevisionResolver:
    """Injected protocol (structural typing): read-only revision queries.

    ``is_ancestor(a, b)`` follows Git plumbing semantics: true when ``a`` is
    an ancestor of ``b`` OR equal to ``b``. ``parents`` is the plumbing
    ``git log -n1 --format=%P`` (used only for the squash-era topology test
    in the review-head exemption).
    """

    def head(self) -> str: ...
    def exists(self, sha: str) -> bool: ...
    def is_ancestor(self, ancestor: str, descendant: str) -> bool: ...
    def parents(self, sha: str) -> tuple[str, ...]: ...


class GitResolver(RevisionResolver):
    """Git-backed resolver: read-only plumbing only (design §3)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
        )

    def head(self) -> str:
        result = self._git("rev-parse", "HEAD")
        return result.stdout.strip() if result.returncode == 0 else ""

    def exists(self, sha: str) -> bool:
        return self._git("cat-file", "-t", sha).returncode == 0

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        return self._git(
            "merge-base", "--is-ancestor", ancestor, descendant
        ).returncode == 0

    def parents(self, sha: str) -> tuple[str, ...]:
        result = self._git("log", "-n1", "--format=%P", sha)
        if result.returncode != 0:
            return ()
        return tuple(result.stdout.split())


def run_verification_commands(root: Path) -> CommandResults:
    """Run the exact-head verification commands (report mode only).

    Local subprocesses from the repository root; the suite is hermetic
    (W14 C9 precedent: zero network / provider / wall-clock dependence).
    The tool never edits anything to make them pass.
    """
    pytest_res = None
    passed: int | None = None
    note = ""
    try:
        pytest_res = subprocess.run(
            [sys.executable, "-m", "pytest"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
        )
        matches = re.findall(r"(\d+) passed", pytest_res.stdout)
        if matches:
            passed = int(matches[-1])
        else:
            note = "pytest count not parseable from stdout"
    except subprocess.TimeoutExpired:
        note = "pytest timed out after 600s"
    except OSError as exc:
        note = f"pytest could not be launched: {exc}"

    compileall_exit: int | None = None
    try:
        comp = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", "src", "tests"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
        )
        compileall_exit = comp.returncode
    except subprocess.TimeoutExpired:
        if not note:
            note = "compileall timed out after 600s"
    except OSError as exc:
        if not note:
            note = f"compileall could not be launched: {exc}"

    return CommandResults(
        pytest_exit=(pytest_res.returncode if pytest_res else None),
        pytest_passed=passed,
        compileall_exit=compileall_exit,
        note=note,
    )


# ---------------------------------------------------------------------------
# The checks (G01–G12). Primary checks are pure functions
# (GateState, RevisionResolver) -> CheckResult; G11 is the composite (takes
# the prior results) and G12 takes packet facts — both remain deterministic
# pure functions of their explicit inputs.
# ---------------------------------------------------------------------------


def check_g01_frozen_authority_integrity(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    problems: list[str] = []
    ok: list[str] = []
    for rel in sorted(state.baseline.frozen_doc_digests):
        expected = state.baseline.frozen_doc_digests[rel]
        path = state.root / rel
        if not path.is_file():
            problems.append(f"missing frozen authority document {rel}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            problems.append(
                f"{rel}: sha256 {actual} != dispatch baseline {expected}"
            )
        else:
            ok.append(rel)
    details = (
        f"{len(ok)}/{len(state.baseline.frozen_doc_digests)} frozen authority "
        "documents byte-identical to the dispatch-time gate baseline "
        "(Architect-verified against frozen v1.0 at review)"
        if not problems
        else "; ".join(problems)
    )
    return CheckResult(
        "G01", "FROZEN_AUTHORITY_INTEGRITY", "architecture",
        STATUS_PASS if not problems else STATUS_FAIL, details,
    )


def check_g02_module_surface_conformance(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    expected = {
        name
        for mods in state.baseline.wave_modules.values()
        for name in mods
    }
    actual = set(state.module_names)
    extra = sorted(actual - expected)
    missing = sorted(expected - actual)
    if extra or missing:
        problems = []
        if extra:
            problems.append(
                "extra src/sos module(s) outside the frozen per-wave surface: "
                + ", ".join(extra)
            )
        if missing:
            problems.append(
                "missing src/sos module(s) from the frozen per-wave surface: "
                + ", ".join(missing)
            )
        details = "; ".join(problems)
        status = STATUS_FAIL
    else:
        per_wave = ", ".join(
            f"{w}:{'+'.join(state.baseline.wave_modules[w]) or 'none'}"
            for w in sorted(state.baseline.wave_modules, key=wave_num)
        )
        details = (
            f"src/sos contains exactly the baseline per-wave module surface "
            f"({len(actual)} modules + __init__.py; {per_wave}) — no fifth "
            "authority, no unmapped subsystem, none missing"
        )
        status = STATUS_PASS
    return CheckResult(
        "G02", "MODULE_SURFACE_CONFORMANCE", "architecture", status, details,
    )


def check_g03_requirements_covered(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    problems: list[str] = []
    tasks = state.impl_state.get("tasks", {}) if state.impl_state else {}
    roadmap_waves = parse_roadmap_ledger_waves(state.roadmap_text)
    ledger_waves = set(tasks)
    if set(roadmap_waves) != ledger_waves:
        problems.append(
            "implementation-state task set != frozen roadmap task ledger set: "
            f"roadmap={sorted(roadmap_waves, key=wave_num)} "
            f"ledger={sorted(ledger_waves, key=wave_num)}"
        )
    for wave in state.baseline.roadmap_ledger_waves:
        if wave == "W15":
            continue
        task = tasks.get(wave)
        if task is None:
            problems.append(f"roadmap ledger row {wave} has no task")
            continue
        if wave == W0_TASK:
            if task.get("status") != "BOOTSTRAP_COMPLETE" or not task.get(
                "bootstrapCommit"
            ):
                problems.append(
                    f"{wave}: bootstrap completion evidence missing "
                    "(status/bootstrapCommit)"
                )
        elif task.get("status") != "COMPLETE" or not task.get("mergedAs"):
            problems.append(
                f"roadmap ledger row {wave} lacks a COMPLETE task with a "
                f"merge (status={task.get('status')!r}, "
                f"mergedAs={task.get('mergedAs')!r})"
            )

    wo_union: set[str] = set()
    for wave in sorted(state.work_order_texts, key=wave_num):
        text = state.work_order_texts[wave]
        line = _REQUIREMENTS_LINE_RE.search(text)
        if not line:
            continue
        reqs = expand_requirement_tokens(line.group(1))
        reqs = {r for r in reqs if r in set(state.baseline.requirement_ids)}
        wo_union.update(reqs)
    missing_wo = [
        r for r in state.baseline.requirement_ids if r not in wo_union
    ]
    if missing_wo:
        problems.append(
            "requirements with no Work-Order primary-requirements coverage: "
            + ", ".join(missing_wo)
        )

    w14_mapping = expand_requirement_tokens(
        state.w14_design_text + "\n" + state.w14_checkpoint_text
    )
    w14_mapping = {
        r for r in w14_mapping if r in set(state.baseline.requirement_ids)
    }
    missing_map = [
        r for r in state.baseline.requirement_ids if r not in w14_mapping
    ]
    if missing_map:
        problems.append(
            "requirements missing from the W14 verification mapping "
            "(W14 design §1 / W14 checkpoint tables): " + ", ".join(missing_map)
        )

    if problems:
        return CheckResult(
            "G03", "REQUIREMENTS_COVERED", "requirements", STATUS_FAIL,
            "; ".join(problems),
        )
    return CheckResult(
        "G03", "REQUIREMENTS_COVERED", "requirements", STATUS_PASS,
        f"all {len(state.baseline.requirement_ids)} requirements R1–R24 "
        "appear in at least one Work Order's primary-requirements line and in "
        "the W14 verification mapping; the implementation-state task set "
        f"equals the frozen roadmap ledger set ({sorted(roadmap_waves, key=wave_num)}); "
        "every roadmap ledger row W0–W14 has a COMPLETE task with a merge "
        "(W0 via the recorded bootstrapCommit exception)",
    )


def _merge_of(tasks: Mapping[str, dict], wave: str) -> str | None:
    task = tasks.get(wave)
    if task is None:
        return None
    if wave == W0_TASK:
        return task.get("bootstrapCommit")
    return task.get("mergedAs")


def _squash_era_head_exempt(
    resolver: RevisionResolver,
    merge: str,
    head_sha: str,
    label: str,
    claim_line_text: str,
) -> tuple[bool, str]:
    """Lawful non-ancestral head: the ARCHITECT-REVIEW-PROTOCOL §2 PR-head
    reference under squash-era topology (single-parent merge)."""
    if not _REVIEW_HEAD_REFERENCE_RE.search(label + " " + claim_line_text):
        return False, ""
    if not resolver.exists(head_sha):
        return False, "review-head reference does not resolve"
    parents = resolver.parents(merge)
    if len(parents) != 1:
        return False, (
            f"merge {short(merge)} is a true merge "
            f"({len(parents)} parents) — a non-ancestral head claim is a "
            "stale-head claim, not the §2 PR-head convention"
        )
    return True, (
        f"{label!r} cites the PR head {short(head_sha)} under "
        "ARCHITECT-REVIEW-PROTOCOL §2 (squash-era single-parent merge "
        f"{short(merge)}); resolvable, topology-verified, recorded"
    )


def check_g04_state_vs_git(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    if state.impl_state is None:
        return CheckResult(
            "G04", "STATE_VS_GIT", "implementation state", STATUS_FAIL,
            f"implementation-state.json unreadable: {state.impl_state_error}",
        )
    problems: list[str] = []
    recorded: list[str] = []
    exemptions: list[str] = []
    tasks: dict[str, dict] = state.impl_state.get("tasks", {})
    head = resolver.head()
    if not head:
        return CheckResult(
            "G04", "STATE_VS_GIT", "implementation state", STATUS_FAIL,
            "no Git HEAD resolvable in the repository root",
        )
    seen_merges: dict[str, str] = {}

    for wave in sorted(tasks, key=wave_num):
        task = tasks[wave]
        status = task.get("status")
        merged = task.get("mergedAs")
        if wave == W0_TASK:
            bootstrap = task.get("bootstrapCommit")
            if not is_hex40(bootstrap) or not resolver.exists(bootstrap):
                problems.append(
                    "W0 bootstrapCommit does not resolve "
                    f"({bootstrap!r})"
                )
            elif not resolver.is_ancestor(bootstrap, head):
                problems.append(
                    "W0 bootstrapCommit is not ancestral to HEAD"
                )
            else:
                recorded.append(
                    f"W0 bootstrap {short(bootstrap)} ancestral of HEAD"
                )
            if merged is not None:
                problems.append(
                    "W0 mergedAs must be null (bootstrapCommit is the "
                    "recorded completion evidence)"
                )
            continue
        if status == "COMPLETE":
            if not is_hex40(merged):
                problems.append(
                    f"{wave}: COMPLETE without a valid 40-hex mergedAs "
                    f"({merged!r})"
                )
                continue
            if not resolver.exists(merged):
                problems.append(
                    f"{wave}: mergedAs {merged} does not resolve (dangling)"
                )
            if not resolver.is_ancestor(merged, head):
                problems.append(
                    f"{wave}: mergedAs {merged} is not reachable from HEAD"
                )
            if merged in seen_merges:
                problems.append(
                    f"{wave}: mergedAs {merged} duplicates {seen_merges[merged]}"
                )
            else:
                seen_merges[merged] = wave
                recorded.append(f"{wave} merged {short(merged)}")
            claims = parse_checkpoint_claims(
                state.checkpoint_texts.get(wave, "")
            )
            for kind, label, shas, line_text in claims:
                if kind != "head" or not shas:
                    continue
                for head_sha in shas:
                    if resolver.is_ancestor(head_sha, merged):
                        continue
                    ok, why = _squash_era_head_exempt(
                        resolver, merged, head_sha, label, line_text
                    )
                    if ok:
                        exemptions.append(why)
                    else:
                        problems.append(
                            f"{wave}: checkpoint head {head_sha} ({label!r}) "
                            f"is not ancestral to its merge {merged}"
                            + (f" [{why}]" if why else "")
                        )
            for kind, label, shas, _line_text in claims:
                if kind != "merge" or not shas:
                    continue
                for merge_sha in shas:
                    if merge_sha != merged:
                        problems.append(
                            f"{wave}: checkpoint {label!r} cites merge "
                            f"{merge_sha} != ledger mergedAs {merged}"
                        )
                    else:
                        recorded.append(
                            f"{wave} checkpoint merge-label reconciles"
                        )
        else:
            if merged is not None:
                problems.append(
                    f"{wave}: status {status!r} but mergedAs is not null — "
                    "machine state must not assert completion Git cannot "
                    "confirm"
                )

    coverage_note = (
        "coverage direction (every wave W1–W15 has Work Order + checkpoint + "
        "design doc; task-set equality) is enforced by G08/G10/G03 and cited "
        "here per design G04"
    )
    if problems:
        return CheckResult(
            "G04", "STATE_VS_GIT", "implementation state", STATUS_FAIL,
            "; ".join(problems),
        )
    merge_count = sum(
        1
        for w, t in tasks.items()
        if t.get("status") == "COMPLETE" and is_hex40(t.get("mergedAs"))
    )
    details = (
        f"{merge_count} COMPLETE task merges resolve, are reachable from "
        "HEAD and pairwise unique; every checkpoint-recorded implementation "
        "head is ancestral-or-equal to its wave's merge"
        + (
            "; recorded §2 squash-era PR-head exemption(s): "
            + " | ".join(sorted(set(exemptions)))
            if exemptions
            else ""
        )
        + f"; W0 bootstrapCommit exception honored; {coverage_note}"
    )
    return CheckResult(
        "G04", "STATE_VS_GIT", "implementation state", STATUS_PASS, details,
    )


def check_g05_dependency_ancestry(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    if state.impl_state is None:
        return CheckResult(
            "G05", "DEPENDENCY_ANCESTRY", "dependency ancestry", STATUS_FAIL,
            f"implementation-state.json unreadable: {state.impl_state_error}",
        )
    problems: list[str] = []
    edges_ok = 0
    tasks: dict[str, dict] = state.impl_state.get("tasks", {})
    head = resolver.head()
    for wave in sorted(tasks, key=wave_num):
        deps = tasks[wave].get("dependencies") or []
        own_merge = _merge_of(tasks, wave)
        for dep in deps:
            dep_merge = _merge_of(tasks, dep)
            if not is_hex40(dep_merge) or not resolver.exists(dep_merge):
                problems.append(
                    f"{wave}<-{dep}: dependency merge {dep_merge!r} does not "
                    "resolve"
                )
                continue
            if own_merge is not None and is_hex40(own_merge):
                if not resolver.is_ancestor(dep_merge, own_merge):
                    problems.append(
                        f"{wave}<-{dep}: dependency merge {short(dep_merge)} "
                        f"is NOT an ancestor of the task merge "
                        f"{short(own_merge)}"
                    )
                else:
                    edges_ok += 1
            else:
                # Active/unmerged task (e.g. W15 at the reviewed head): every
                # dependency merge must be ancestral to the reviewed head.
                if not resolver.is_ancestor(dep_merge, head):
                    problems.append(
                        f"{wave}<-{dep}: dependency merge {short(dep_merge)} "
                        "is NOT an ancestor of the reviewed head "
                        f"{short(head)}"
                    )
                else:
                    edges_ok += 1
    all_ancestral = True
    for wave_key in tasks:
        if wave_key == "W15":
            continue
        own = _merge_of(tasks, wave_key)
        if own is None:
            continue
        if not is_hex40(own) or not resolver.is_ancestor(own, head):
            all_ancestral = False
            break
    if not all_ancestral:
        problems.append(
            "not every W0–W14 merge is ancestral to the W15 reviewed head"
        )
    if problems:
        return CheckResult(
            "G05", "DEPENDENCY_ANCESTRY", "dependency ancestry", STATUS_FAIL,
            "; ".join(problems),
        )
    return CheckResult(
        "G05", "DEPENDENCY_ANCESTRY", "dependency ancestry", STATUS_PASS,
        f"all {edges_ok} declared dependency edges are real Git ancestry "
        "relations (the frozen sequencing rule mechanically proven); every "
        "W0–W14 merge is ancestral to the W15 reviewed head",
    )


def check_g06_suite_green(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    if state.commands is None:
        return CheckResult(
            "G06", "SUITE_GREEN", "tests", STATUS_DEFERRED,
            "check-only mode: pytest/compileall subprocess evidence is "
            "collected in report mode only (design §3 G06 subprocess "
            "boundary)",
        )
    commands = state.commands
    recorded = parse_w14_recorded_count(state.w14_checkpoint_text)
    threshold = (
        recorded
        if recorded is not None
        else state.baseline.w14_baseline_test_count
    )
    threshold_src = (
        f"W14 checkpoint recorded count {threshold}"
        if recorded is not None
        else f"dispatch baseline {state.baseline.w14_baseline_test_count} "
        "(W14 checkpoint count not parseable)"
    )
    problems: list[str] = []
    if commands.pytest_exit != 0:
        problems.append(f"pytest exit code {commands.pytest_exit}")
    if commands.pytest_passed is None:
        problems.append("pytest pass count not parseable")
    elif commands.pytest_passed < threshold:
        problems.append(
            f"pytest passed {commands.pytest_passed} < {threshold_src} "
            "(extend-never-weaken violated)"
        )
    if commands.compileall_exit != 0:
        problems.append(f"compileall exit code {commands.compileall_exit}")
    if commands.note:
        problems.append(commands.note)
    if problems:
        return CheckResult(
            "G06", "SUITE_GREEN", "tests", STATUS_FAIL, "; ".join(problems),
        )
    return CheckResult(
        "G06", "SUITE_GREEN", "tests", STATUS_PASS,
        f"python -m pytest: exit 0, {commands.pytest_passed} passed "
        f"(>= {threshold_src}); python -m compileall -q src tests: exit 0 — "
        "exact-head counts recorded in the report; the Worker also runs both "
        "commands manually for the checkpoint (exact-head discipline)",
    )


def check_g07_adversarial_evidence(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    if state.matrix is None:
        return CheckResult(
            "G07", "ADVERSARIAL_EVIDENCE", "adversarial evidence", STATUS_FAIL,
            f"W14 adversarial-evidence matrix unreadable: {state.matrix_error}",
        )
    problems: list[str] = []
    matrix = state.matrix
    schema = matrix.get("schema")
    if schema != state.baseline.w14_matrix_schema:
        problems.append(
            f"matrix schema {schema!r} != {state.baseline.w14_matrix_schema!r}"
        )
    rows = matrix.get("rows")
    if not isinstance(rows, list):
        problems.append("matrix has no rows array")
        rows = []
    case_field = "caseId" if rows and isinstance(rows[0], dict) and "caseId" in rows[0] else "case"
    present: dict[str, int] = {}
    failing: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            problems.append(f"non-object row: {row!r}")
            continue
        case = row.get(case_field) or row.get("caseId") or row.get("case")
        if isinstance(case, str):
            present[case] = present.get(case, 0) + 1
        verdict = row.get("verdict")
        if verdict != STATUS_PASS:
            failing.append(f"{case}={verdict!r}")
    for case_id in state.baseline.w14_case_ids:
        if present.get(case_id, 0) < 1:
            problems.append(f"missing frozen case {case_id}")
    if failing:
        problems.append("non-PASS verdicts: " + ", ".join(sorted(failing)))
    repo_head = matrix.get("repoHead")
    head = resolver.head()
    if not is_hex40(repo_head):
        problems.append(f"matrix repoHead {repo_head!r} is not a 40-hex SHA")
    elif head and not resolver.is_ancestor(repo_head, head):
        problems.append(
            f"matrix repoHead {repo_head} is not an ancestor of HEAD"
        )
    if problems:
        return CheckResult(
            "G07", "ADVERSARIAL_EVIDENCE", "adversarial evidence", STATUS_FAIL,
            "; ".join(problems),
        )
    return CheckResult(
        "G07", "ADVERSARIAL_EVIDENCE", "adversarial evidence", STATUS_PASS,
        f"matrix parses with schema {state.baseline.w14_matrix_schema}; "
        f"{len(rows)} rows contain each of the "
        f"{len(state.baseline.w14_case_ids)} frozen case names at least once; "
        f"every verdict PASS; repoHead {short(str(repo_head))} is an ancestor "
        "of HEAD",
    )


def check_g08_checkpoints_current(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    problems: list[str] = []
    observations: list[str] = []
    recorded: list[str] = []
    head = resolver.head()
    tasks = state.impl_state.get("tasks", {}) if state.impl_state else {}

    for wave in WAVES_W1_W15:
        text = state.checkpoint_texts.get(wave, "")
        path = f"spec/development-state/W{wave_num(wave)}-checkpoint.md"
        if not text:
            problems.append(f"missing checkpoint {path}")
            continue
        claims = parse_checkpoint_claims(text)
        head_claims = [c for c in claims if c[0] == "head" and c[2]]
        base_claims = [c for c in claims if c[0] == "base" and c[2]]
        if not base_claims:
            problems.append(f"{wave}: checkpoint records no base SHA")
        if not head_claims:
            problems.append(f"{wave}: checkpoint records no head SHA")
        wave_merge = _merge_of(tasks, wave) if tasks else None
        for kind, label, shas, line_text in claims:
            if kind not in ("head", "base") or not shas:
                continue
            for sha in shas:
                if not resolver.exists(sha):
                    problems.append(
                        f"{wave}: {kind} claim {label!r} cites dangling SHA "
                        f"{sha}"
                    )
                    continue
                if resolver.is_ancestor(sha, head):
                    recorded.append(f"{wave}:{kind}:{short(sha)}")
                    continue
                if kind == "base":
                    problems.append(
                        f"{wave}: base SHA {sha} is not reachable from HEAD "
                        "(stale base claim)"
                    )
                    continue
                ok, why = _squash_era_head_exempt(
                    resolver, wave_merge or head, sha, label, line_text
                )
                if ok:
                    observations.append(why)
                else:
                    problems.append(
                        f"{wave}: head SHA {sha} ({label!r}) is not "
                        "reachable from HEAD (stale-head completion claim)"
                        + (f" [{why}]" if why else "")
                    )
        label_shas = {
            sha for _, _, shas, _ in claims for sha in shas
        }
        for sha in SHA40_RE.findall(text):
            if sha in label_shas:
                continue
            if not resolver.exists(sha):
                observations.append(
                    f"{wave}: non-head narrative citation {sha} does not "
                    "resolve (outside the head-claim semantics; recorded as "
                    "an observation for the Architect)"
                )
    if problems:
        return CheckResult(
            "G08", "CHECKPOINTS_CURRENT", "exact revisions", STATUS_FAIL,
            "; ".join(problems),
        )
    details = (
        "15/15 checkpoints (W1–W15) exist and record exact base/head "
        "revisions; every base SHA resolves and is reachable from HEAD; "
        f"{len(recorded)} head/base claims resolve and are ancestor-or-equal "
        "of HEAD (no stale-head completion claim survives)"
        + (
            "; §2 squash-era PR-head exemption(s): "
            + " | ".join(sorted(set(observations)))
            if observations
            else ""
        )
    )
    return CheckResult(
        "G08", "CHECKPOINTS_CURRENT", "exact revisions", STATUS_PASS, details,
    )


def check_g09_rollback_safety(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    problems: list[str] = []
    recorded: list[str] = []
    for wave in sorted(state.baseline.rollback_carriers, key=wave_num):
        carrier, form = state.baseline.rollback_carriers[wave]
        if carrier == "checkpoint":
            text = state.checkpoint_texts.get(wave, "")
            carrier_name = (
                f"spec/development-state/W{wave_num(wave)}-checkpoint.md"
            )
        else:
            carrier_name = state.baseline.design_files.get(wave, "")
            text = read_text(state.root / carrier_name)
        if not text:
            problems.append(
                f"{wave}: rollback-declaration carrier {carrier_name} is "
                "missing/empty"
            )
            continue
        if form == "rollback-section":
            heading = _ROLLBACK_HEADING_RE.search(text)
            if not heading:
                problems.append(
                    f"{wave}: no rollback declaration heading in "
                    f"{carrier_name}"
                )
                continue
            section = text[heading.start():]
            first_line, _, rest = section.partition("\n")
            nxt = re.search(r"(?im)^#{1,6}\s", rest)
            body = first_line + "\n" + (
                rest[: nxt.start()] if nxt else rest[:2000]
            )
            if not _ROLLBACK_MECHANISM_RE.search(body):
                problems.append(
                    f"{wave}: rollback declaration in {carrier_name} carries "
                    "no mechanism statement"
                )
            else:
                recorded.append(f"{wave}:section")
        elif form == "scope-exclusion":
            if not _SCOPE_EXCLUSION_RE.search(text):
                problems.append(
                    f"{wave}: no early-wave scope-exclusion declaration in "
                    f"{carrier_name}"
                )
            else:
                recorded.append(f"{wave}:scope-exclusion")
    artifact_hits = [
        p
        for p in state.repo_paths
        if any(pat in p.lower() for pat in state.baseline.deployment_artifact_patterns)
    ]
    if artifact_hits:
        problems.append(
            "deployment/migration artifacts present in the repository tree: "
            + ", ".join(artifact_hits)
        )
    if problems:
        return CheckResult(
            "G09", "ROLLBACK_SAFETY", "rollback safety", STATUS_FAIL,
            "; ".join(problems),
        )
    return CheckResult(
        "G09", "ROLLBACK_SAFETY", "rollback safety", STATUS_PASS,
        f"every wave W1–W15 carries its rollback declaration in the "
        f"baseline-recorded carrier ({len(recorded)} declarations: "
        + ", ".join(recorded)
        + "); no deployment/migration/network artifact exists anywhere in "
        "the repository tree; combined with G02 (exactly the frozen module "
        "surface) and G06 (suite green, including every wave's "
        "rollback-invariant tests) each merged authority is revertable by "
        "ordinary Git with no unrevertable external state",
    )


def check_g10_docs_reconciled(
    state: GateState, resolver: RevisionResolver
) -> CheckResult:
    problems: list[str] = []
    flags: list[str] = []
    recorded: list[str] = []
    head = resolver.head()
    baseline = state.baseline

    for wave in sorted(baseline.work_order_files, key=wave_num):
        if not (state.root / baseline.work_order_files[wave]).is_file():
            problems.append(
                f"missing Work Order {baseline.work_order_files[wave]}"
            )
    for wave in sorted(baseline.design_files, key=wave_num):
        if not (state.root / baseline.design_files[wave]).is_file():
            problems.append(
                f"missing design doc {baseline.design_files[wave]}"
            )

    if not state.current_state_text:
        problems.append(f"missing {CURRENT_STATE_PATH}")
        return CheckResult(
            "G10", "DOCS_RECONCILED", "documentation", STATUS_FAIL,
            "; ".join(problems),
        )
    if state.impl_state is None:
        problems.append(
            f"implementation-state.json unreadable: {state.impl_state_error}"
        )
        return CheckResult(
            "G10", "DOCS_RECONCILED", "documentation", STATUS_FAIL,
            "; ".join(problems),
        )

    tasks: dict[str, dict] = state.impl_state.get("tasks", {})
    complete_waves = [
        w for w, t in tasks.items() if t.get("status") == "COMPLETE"
    ]
    highest_complete = (
        max(complete_waves, key=wave_num) if complete_waves else None
    )
    ledger_frontier = [
        w for w in (state.impl_state.get("currentFrontier") or []) if isinstance(w, str)
    ]
    ledger_frontier_wave = (
        max(ledger_frontier, key=wave_num) if ledger_frontier else None
    )
    terminal = state.impl_state.get("status") == "ROADMAP_COMPLETE"

    projection = parse_current_state_projection(state.current_state_text)
    for name in ("live_main", "last_completed", "frontier", "machine_state"):
        if not projection.get(name):
            problems.append(
                f"current-state.md is missing its {name!r} projection field"
            )

    # (i) the recorded Live `main` SHA line.
    live_line = projection.get("live_main", "")
    if live_line:
        cited = SHA40_RE.findall(live_line)
        if "recompute" in live_line.lower():
            # The repository's recorded convention (since the W12-era
            # reconciliation commits): the line instructs recomputation and
            # cites milestone SHAs, because a commit cannot embed its own
            # SHA. Every cited milestone must resolve and be ancestral.
            for sha in cited:
                if not resolver.exists(sha):
                    problems.append(
                        f"current-state.md live-main citation {sha} does "
                        "not resolve"
                    )
                elif head and not resolver.is_ancestor(sha, head):
                    problems.append(
                        f"current-state.md live-main citation {sha} is not "
                        "ancestral of HEAD"
                    )
            if cited and not problems:
                recorded.append(
                    "live-main line follows the recorded recompute "
                    f"convention with {len(cited)} ancestral milestone SHA(s)"
                )
        elif cited:
            if len(cited) != 1 or cited[0] != head:
                problems.append(
                    "current-state.md live-main SHA "
                    f"{cited[0] if cited else None!r} != actual HEAD {head} "
                    "(stale literal recording)"
                )
            else:
                recorded.append("live-main SHA equals actual HEAD (strict)")
        else:
            problems.append(
                "current-state.md live-main line records neither a SHA nor "
                "the recompute convention"
            )

    # (ii) the Last Completed Work Order line.
    last_line = projection.get("last_completed", "")
    if last_line:
        m_wave = re.search(r"\bW(\d+)\b", last_line)
        last_sha = SHA40_RE.findall(last_line)
        if not m_wave:
            problems.append(
                "current-state.md last-completed line names no wave"
            )
        else:
            lc_wave = f"W{m_wave.group(1)}"
            task = tasks.get(lc_wave)
            if task is None:
                problems.append(
                    f"current-state.md last-completed wave {lc_wave} is not "
                    "a ledger task"
                )
            elif task.get("status") != "COMPLETE" or not task.get("mergedAs"):
                problems.append(
                    f"current-state.md last-completed wave {lc_wave} is "
                    "AHEAD of the ledger (claimed complete; ledger says "
                    f"{task.get('status')!r}) — false completion claim"
                )
            elif last_sha and last_sha[0] != task.get("mergedAs"):
                problems.append(
                    f"current-state.md last-completed merge {last_sha[0]} != "
                    f"ledger mergedAs {task.get('mergedAs')} for {lc_wave}"
                )
            else:
                if last_sha:
                    sha = last_sha[0]
                    if not resolver.exists(sha) or (
                        head and not resolver.is_ancestor(sha, head)
                    ):
                        problems.append(
                            f"current-state.md last-completed merge {sha} "
                            "does not resolve / is not ancestral of HEAD"
                        )
                if not problems:
                    if terminal:
                        if lc_wave != highest_complete:
                            problems.append(
                                f"terminal state: current-state.md "
                                f"last-completed {lc_wave} != highest "
                                f"COMPLETE {highest_complete}"
                            )
                    else:
                        lag = (
                            wave_num(highest_complete) - wave_num(lc_wave)
                            if highest_complete
                            else 0
                        )
                        if lag < 0 or lag > 1:
                            problems.append(
                                f"current-state.md last-completed {lc_wave} "
                                f"lags the ledger highest COMPLETE "
                                f"{highest_complete} by {lag} waves (bounded "
                                "tolerance is 1 — the merge-reconciliation "
                                "boundary)"
                            )
                        elif lag == 1:
                            flags.append(
                                f"projection lags ledger by one wave "
                                f"(last-completed {lc_wave} vs "
                                f"{highest_complete}) — tolerated under the "
                                "open-program merge-reconciliation boundary; "
                                "the final reconciliation commit closes it "
                                "(Work Order Risk section); REVIEW-TIME FLAG "
                                "for the Architect"
                            )
                        else:
                            recorded.append(
                                f"last-completed {lc_wave} matches the ledger"
                            )

    # (iii) the Current frontier line.
    frontier_line = projection.get("frontier", "")
    if frontier_line:
        m_wave = re.search(r"\bW(\d+)\b", frontier_line)
        if m_wave:
            f_wave = f"W{m_wave.group(1)}"
            if f_wave not in tasks:
                problems.append(
                    f"current-state.md frontier {f_wave} is not a ledger task"
                )
            else:
                ahead_of = (
                    ledger_frontier_wave
                    and wave_num(f_wave) > wave_num(ledger_frontier_wave)
                )
                if ahead_of:
                    problems.append(
                        f"current-state.md frontier {f_wave} is AHEAD of the "
                        f"ledger frontier {ledger_frontier_wave}"
                    )
                elif terminal:
                    if ledger_frontier:
                        problems.append(
                            "terminal state: the ledger frontier is "
                            f"non-empty ({ledger_frontier}) while status "
                            "is ROADMAP_COMPLETE"
                        )
                    else:
                        problems.append(
                            "terminal state: current-state.md frontier "
                            f"names {f_wave} while the roadmap is complete "
                            "(the final projection must be the none-form)"
                        )
                else:
                    lag = (
                        wave_num(ledger_frontier_wave) - wave_num(f_wave)
                        if ledger_frontier_wave
                        else 0
                    )
                    if lag < 0 or lag > 1:
                        problems.append(
                            f"current-state.md frontier {f_wave} lags the "
                            f"ledger frontier {ledger_frontier_wave} by "
                            f"{lag} waves (bounded tolerance is 1)"
                        )
                    elif lag == 1:
                        flags.append(
                            f"projection frontier {f_wave} lags the ledger "
                            f"frontier {ledger_frontier_wave} by one wave — "
                            "tolerated under the open-program boundary; the "
                            "final reconciliation commit closes it; "
                            "REVIEW-TIME FLAG for the Architect"
                        )
                    else:
                        recorded.append(
                            f"frontier {f_wave} matches the ledger frontier"
                        )
        else:
            if terminal:
                if not _FRONTIER_NONE_RE.search(frontier_line):
                    problems.append(
                        "terminal state: current-state.md frontier line is "
                        "neither a none-form nor a ledger wave"
                    )
                else:
                    recorded.append("terminal frontier none-form accepted")
            else:
                problems.append(
                    "current-state.md frontier line names no wave (open "
                    "program)"
                )

    # (iv) the Machine state pointer line: its COMPLETE/<sha> claims must be
    # true, and its snapshot frontier may lag by the same bounded boundary.
    machine_line = projection.get("machine_state", "")
    if machine_line:
        if "implementation-state.json" not in machine_line:
            problems.append(
                "current-state.md machine-state line does not point at "
                "implementation-state.json"
            )
        for wave, sha in re.findall(
            r"\bW(\d+)\s*=\s*COMPLETE/([0-9a-f]{40})", machine_line
        ):
            w = f"W{wave}"
            task = tasks.get(w)
            if task is None or task.get("status") != "COMPLETE":
                problems.append(
                    f"machine-state snapshot claims {w}=COMPLETE ahead of "
                    "the ledger"
                )
            elif task.get("mergedAs") != sha:
                problems.append(
                    f"machine-state snapshot claims {w}=COMPLETE/{sha} != "
                    f"ledger mergedAs {task.get('mergedAs')}"
                )
        snap = re.search(
            r'currentFrontier\s*=\s*\[\s*"?(W\d+)"?', machine_line
        )
        if snap:
            snap_wave = snap.group(1)
            if snap_wave not in tasks:
                problems.append(
                    f"machine-state snapshot frontier {snap_wave} is not a "
                    "ledger task"
                )
            elif terminal:
                problems.append(
                    "terminal state: machine-state snapshot frontier is "
                    f"non-empty ({snap_wave})"
                )
            elif ledger_frontier_wave and (
                wave_num(ledger_frontier_wave) - wave_num(snap_wave)
            ) not in (0, 1):
                problems.append(
                    f"machine-state snapshot frontier {snap_wave} lags the "
                    f"ledger frontier {ledger_frontier_wave} beyond the "
                    "bounded tolerance"
                )
            elif (
                ledger_frontier_wave
                and wave_num(ledger_frontier_wave) - wave_num(snap_wave) == 1
            ):
                flags.append(
                    f"machine-state snapshot frontier {snap_wave} lags the "
                    f"ledger frontier {ledger_frontier_wave} by one wave "
                    "(open-program boundary; closed by the final "
                    "reconciliation commit)"
                )

    if problems:
        return CheckResult(
            "G10", "DOCS_RECONCILED", "documentation", STATUS_FAIL,
            "; ".join(problems),
        )
    details = (
        f"every wave W1–W15 has its Work Order and design doc "
        f"({len(baseline.work_order_files)}+{len(baseline.design_files)} "
        "baseline filenames present); current-state.md projection: "
        + "; ".join(recorded)
        + (
            "; OBSERVED (recorded, non-blocking): " + " | ".join(flags)
            if flags
            else ""
        )
        + (
            "; TERMINAL strict field equality enforced (ledger status "
            "ROADMAP_COMPLETE)"
            if terminal
            else "; strict field equality is enforced in the terminal "
            "(ROADMAP_COMPLETE) state; in the open state the projection may "
            "lag the ledger by at most the single merge-reconciliation "
            "boundary and every lag is recorded above"
        )
    )
    return CheckResult(
        "G10", "DOCS_RECONCILED", "documentation", STATUS_PASS, details,
    )


def check_g11_fresh_agent_recoverable(
    state: GateState,
    resolver: RevisionResolver,
    prior: Sequence[CheckResult],
) -> CheckResult:
    problems: list[str] = []
    for rel in BOOTSTRAP_ARTIFACTS:
        if not (state.root / rel).is_file():
            problems.append(f"missing bootstrap artifact {rel}")
    if state.impl_state is None:
        problems.append("implementation-state.json unreadable")
    if not state.current_state_text:
        problems.append("current-state.md missing")
    if not state.roadmap_text:
        problems.append("frozen roadmap missing")
    failed = [c.id for c in prior if c.status == STATUS_FAIL]
    deferred = [c.id for c in prior if c.status == STATUS_DEFERRED]
    if failed:
        problems.append(
            "mechanical recovery chain broken: " + ", ".join(failed)
        )
    if problems:
        return CheckResult(
            "G11", "FRESH_AGENT_RECOVERABLE", "fresh-agent recovery",
            STATUS_FAIL, "; ".join(problems),
        )
    chain_state = (
        "G01–G10 all PASS"
        if not deferred
        else "G01–G10 PASS with G06 DEFERRED (check-only mode: the "
        "subprocess evidence is collected in report mode)"
    )
    return CheckResult(
        "G11", "FRESH_AGENT_RECOVERABLE", "fresh-agent recovery", STATUS_PASS,
        "the mechanical zero-history recovery chain is complete and "
        "contradiction-free (ARCHITECT_START_HERE.md, AGENTS.md, dev-state "
        "README, frozen specs G01, roadmap G01, implementation-state G04, "
        "current-state G10, Work Orders G10, checkpoints G08, and "
        + chain_state
        + ") — repository state alone answers SOS-IMPLEMENTATION-"
        "PROCESS §14 (active Work Order, merged dependencies, exact heads, "
        "verification evidence, frontier); REVIEW-TIME (not machine-"
        "decidable): the human zero-history walkthrough — a fresh reviewer "
        "bootstraps via ARCHITECT_START_HERE.md and states the frontier from "
        "repository state alone — is executed and recorded in the sign-off "
        "record (packet item 6), never assumed",
    )


def check_g12_signoff_packet_ready(
    state: GateState,
    resolver: RevisionResolver,
) -> CheckResult:
    problems: list[str] = []
    components: list[str] = []
    if state.matrix is not None:
        components.append("W14 adversarial-evidence matrix present (G07)")
    else:
        problems.append("W14 adversarial-evidence matrix missing (G07)")
    w15_checkpoint = state.checkpoint_texts.get("W15", "")
    if not w15_checkpoint:
        problems.append("W15 checkpoint missing")
    else:
        has_pytest = bool(
            re.search(r"(?i)python3?\s+-m\s+pytest", w15_checkpoint)
        )
        has_compileall = bool(
            re.search(r"(?i)python3?\s+-m\s+compileall", w15_checkpoint)
        )
        has_gate = bool(
            re.search(r"(?i)final_gate_check", w15_checkpoint)
        )
        if has_pytest and has_compileall and has_gate:
            components.append(
                "W15 checkpoint cites the three verification commands' "
                "results (pytest / compileall / final_gate_check)"
            )
        else:
            missing = [
                n for n, ok in (
                    ("pytest", has_pytest),
                    ("compileall", has_compileall),
                    ("final_gate_check", has_gate),
                ) if not ok
            ]
            problems.append(
                "W15 checkpoint does not cite the verification command(s): "
                + ", ".join(missing)
            )
    missing_checkpoints = [
        w for w in WAVES_W1_W15 if not state.checkpoint_texts.get(w, "")
    ]
    if missing_checkpoints:
        problems.append(
            "checkpoint chain incomplete: " + ", ".join(missing_checkpoints)
        )
    else:
        components.append("complete W1–W15 checkpoint chain (G08)")
    if state.report_exists:
        components.append("gate report present at the report path")
    elif state.report_mode:
        components.append(
            "gate report produced by this run (report mode)"
        )
    else:
        problems.append(
            "gate report file absent and this run does not produce it "
            "(check-only mode)"
        )
    if problems:
        return CheckResult(
            "G12", "SIGNOFF_PACKET_READY", "final sign-off", STATUS_FAIL,
            "; ".join(problems),
        )
    return CheckResult(
        "G12", "SIGNOFF_PACKET_READY", "final sign-off", STATUS_PASS,
        "the Worker-owned sign-off packet components exist at the head: "
        + "; ".join(components)
        + ". REVIEW-TIME (deliberately NOT script checks): the sign-off "
        "record itself is Architect-authored at approval "
        "(spec/development-state/W15-final-sign-off.md, outside the Worker's "
        "surface) and open-PR / PR-identity reconciliation is an Architect "
        "review-time check — the gate never approves (process §11)",
    )


# ---------------------------------------------------------------------------
# Gate orchestration
# ---------------------------------------------------------------------------

CheckFn = Callable[[GateState, RevisionResolver], CheckResult]

PRIMARY_CHECKS: tuple[tuple[str, str, str, CheckFn], ...] = (
    ("G01", "FROZEN_AUTHORITY_INTEGRITY", "architecture",
     check_g01_frozen_authority_integrity),
    ("G02", "MODULE_SURFACE_CONFORMANCE", "architecture",
     check_g02_module_surface_conformance),
    ("G03", "REQUIREMENTS_COVERED", "requirements",
     check_g03_requirements_covered),
    ("G04", "STATE_VS_GIT", "implementation state", check_g04_state_vs_git),
    ("G05", "DEPENDENCY_ANCESTRY", "dependency ancestry",
     check_g05_dependency_ancestry),
    ("G06", "SUITE_GREEN", "tests", check_g06_suite_green),
    ("G07", "ADVERSARIAL_EVIDENCE", "adversarial evidence",
     check_g07_adversarial_evidence),
    ("G08", "CHECKPOINTS_CURRENT", "exact revisions",
     check_g08_checkpoints_current),
    ("G09", "ROLLBACK_SAFETY", "rollback safety", check_g09_rollback_safety),
    ("G10", "DOCS_RECONCILED", "documentation", check_g10_docs_reconciled),
)


def run_gate(
    state: GateState, resolver: RevisionResolver
) -> tuple[list[CheckResult], str]:
    """Run G01–G12 in order; G11 composites G01–G10; G12 closes the packet."""
    results: list[CheckResult] = []
    for check_id, title, area, fn in PRIMARY_CHECKS:
        results.append(fn(state, resolver))
    results.append(
        check_g11_fresh_agent_recoverable(state, resolver, results[:10])
    )
    results.append(check_g12_signoff_packet_ready(state, resolver))
    overall = (
        STATUS_PASS if all(r.status == STATUS_PASS for r in results)
        else STATUS_FAIL
    )
    return results, overall


def build_report(
    repo_head: str,
    results: Sequence[CheckResult],
    commands: CommandResults | None,
    overall: str,
) -> dict[str, object]:
    return {
        "schema": REPORT_SCHEMA,
        "repoHead": repo_head,
        "commands": (
            commands.as_report
            if commands is not None
            else {
                "pytest": {"exitCode": None, "passed": None},
                "compileall": {"exitCode": None},
            }
        ),
        "checks": [
            {
                "id": r.id,
                "title": r.title,
                "area": r.area,
                "status": r.status,
                "details": r.details,
            }
            for r in results
        ],
        "overall": overall,
    }


REVIEW_TIME_ITEMS = (
    "G11 human zero-history walkthrough (fresh reviewer bootstraps via "
    "ARCHITECT_START_HERE.md and states the frontier from repository state "
    "alone) — recorded in the sign-off record, packet item 6",
    "G12 Architect-authored sign-off record "
    "(spec/development-state/W15-final-sign-off.md) + open-PR / PR-identity "
    "reconciliation — Architect review-time checks",
    "G01 baseline digest verification against the frozen v1.0 documents "
    "(Architect verifies the dispatch-time digests at review)",
    "G10 final reconciliation commit (post-merge, Architect/TL authority) "
    "closes the recorded open-program projection lag",
)


def print_summary(
    results: Sequence[CheckResult],
    overall: str,
    repo_head: str,
    report_path: Path | None,
    check_only: bool = False,
) -> None:
    import textwrap

    print("W15 final gate — machine-checkable reconciliation checklist")
    for r in results:
        print(f"{r.id} {r.title} [{r.area}]: {r.status}")
        for line in textwrap.wrap(
            r.details, width=96, initial_indent="    ", subsequent_indent="    "
        ):
            print(line)
    passed = sum(1 for r in results if r.status == STATUS_PASS)
    failed = sum(1 for r in results if r.status == STATUS_FAIL)
    deferred = sum(1 for r in results if r.status == STATUS_DEFERRED)
    if check_only:
        verdict = STATUS_PASS if failed == 0 else STATUS_FAIL
        print(
            f"OVERALL (check-only): {verdict} — {passed}/{len(results)} "
            f"checks PASS ({failed} FAIL, {deferred} DEFERRED; DEFERRED is "
            f"tolerated in check-only mode) at {repo_head}"
        )
    else:
        print(
            f"OVERALL: {overall} — {passed}/{len(results)} checks PASS "
            f"({failed} FAIL, {deferred} DEFERRED) at {repo_head}"
        )
    print(
        "review-time items (not machine-decidable; named in the sign-off "
        "protocol):"
    )
    for item in REVIEW_TIME_ITEMS:
        print(f"  - {item}")
    if report_path is not None:
        print(f"report written: {report_path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "W15 final architect gate: offline, read-only, deterministic "
            "reconciliation checklist (G01–G12). Exit 0 iff every check "
            "passes (report mode)."
        ),
    )
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument(
        "--root",
        default=str(default_root),
        help="repository root (default: the root containing tools/)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--report",
        nargs="?",
        const=DEFAULT_REPORT_PATH,
        default=None,
        metavar="PATH",
        help=(
            "report mode: run the verification-command subprocesses and "
            "write the JSON gate report (default path: "
            f"{DEFAULT_REPORT_PATH})"
        ),
    )
    mode.add_argument(
        "--check-only",
        action="store_true",
        help="check-only mode: write nothing, launch no subprocesses (G06 "
        "records DEFERRED)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: repository root is not a directory: {root}", file=sys.stderr)
        return 2
    check_only = args.check_only
    report_mode = not check_only
    report_rel = args.report if isinstance(args.report, str) else (
        DEFAULT_REPORT_PATH if report_mode else None
    )
    if report_rel is None:
        report_path = None
    else:
        candidate = Path(report_rel)
        report_path = (
            candidate if candidate.is_absolute() else root / candidate
        )

    resolver = GitResolver(root)
    repo_head = resolver.head()
    if not repo_head:
        print(
            f"error: no Git HEAD resolvable under {root} — the gate requires "
            "a Git repository",
            file=sys.stderr,
        )
        return 2

    commands = (
        run_verification_commands(root) if report_mode else None
    )
    state = load_state(
        root,
        commands=commands,
        report_mode=report_mode,
        report_path=report_path,
    )
    results, overall = run_gate(state, resolver)

    if report_mode and report_path is not None:
        report = build_report(repo_head, results, commands, overall)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    print_summary(results, overall, repo_head, report_path, check_only)

    # Exit-code contract: report mode — 0 iff every check passed (no FAIL
    # and no DEFERRED can occur there); check-only mode — 0 iff no check
    # FAILed (G06 DEFERRED is tolerated by design §3).
    if any(r.status == STATUS_FAIL for r in results):
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
