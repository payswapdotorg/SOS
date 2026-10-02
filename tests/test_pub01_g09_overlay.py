"""PUB-01 — G09 overlay-prefix reconciliation tests (contract §D PUB-01.1):
overlay-prefixed deployment-shaped paths are exempt; a pattern-matching path
OUTSIDE the overlay prefixes still fails G09. Includes the real-repository
in-process check with ``db/migrations/*.sql`` present on the branch."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

import final_gate_check as fgc  # noqa: E402

# The exact contract-mandated allowlist (spec/deployment/
# PUBLIC-DEPLOYMENT-CONTRACT.md §D PUB-01).
EXPECTED_OVERLAY_PREFIXES = (
    "apps/", "services/", "providers/", "execution/", "db/", "infra/",
    "docs/deployment/", "spec/deployment/",
)


def test_overlay_prefix_constant_is_exactly_the_contract_set() -> None:
    assert fgc.POST_ROADMAP_OVERLAY_PREFIXES == EXPECTED_OVERLAY_PREFIXES


def test_g09_passes_on_real_repository_with_overlay_present() -> None:
    """The real branch carries db/migrations/*.sql (a G09 pattern) under the
    governed ``db/`` overlay root; G09 must PASS at this head through the
    real Git-backed resolver."""
    resolver = fgc.GitResolver(REPO_ROOT)
    state = fgc.load_state(
        REPO_ROOT, baseline=fgc.Baseline(), commands=None,
        report_mode=False,
    )
    results, _overall = fgc.run_gate(state, resolver)
    g09 = next(r for r in results if r.id == "G09")
    assert g09.status == fgc.STATUS_PASS, g09.details
    assert "frozen surface of the repository tree" in g09.details
    assert "spec/deployment/PUBLIC-DEPLOYMENT-CONTRACT.md" in g09.details
    # and the overlay artifacts ARE on disk under exempt prefixes
    assert (REPO_ROOT / "db" / "migrations").is_dir()
    assert list((REPO_ROOT / "db" / "migrations").glob("*.sql"))


def test_g09_fails_for_pattern_outside_overlay_prefixes(tmp_path: Path) -> None:
    """A pattern-matching path OUTSIDE the overlay prefixes still fails G09 —
    the exemption is prefix-scoped, not global."""
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from test_w15_final_gate_check import (  # noqa: E402
        DAG,
        TIP,
        FakeResolver,
        build_fixture,
    )

    root = tmp_path / "repo"
    baseline = build_fixture(root)
    intruder = root / "deploy" / "k8s" / "manifest.yaml"
    intruder.parent.mkdir(parents=True)
    intruder.write_text("apiVersion: v1\n", encoding="utf-8")
    state = fgc.load_state(
        root, baseline=baseline, commands=None, report_mode=True,
        report_path=root / fgc.DEFAULT_REPORT_PATH,
    )
    results, _overall = fgc.run_gate(state, FakeResolver(DAG, TIP))
    g09 = next(r for r in results if r.id == "G09")
    assert g09.status == fgc.STATUS_FAIL
    assert "deploy/k8s/manifest.yaml" in g09.details


def test_g09_exempts_paths_only_under_overlay_prefixes(tmp_path: Path) -> None:
    """Paths under overlay prefixes are exempt; a deceptively-named sibling
    directory (``dbx/``) is NOT."""
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from test_w15_final_gate_check import (  # noqa: E402
        DAG,
        TIP,
        FakeResolver,
        build_fixture,
    )

    root = tmp_path / "repo"
    baseline = build_fixture(root)
    for rel in (
        "db/migrations/0001_init.sql",
        "infra/apify/Dockerfile",
        "services/api/docker-compose.yml",
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("-- overlay fixture\n", encoding="utf-8")
    sneaky = root / "dbx" / "migrations" / "evil.sql"
    sneaky.parent.mkdir(parents=True)
    sneaky.write_text("-- frozen-surface intrusion\n", encoding="utf-8")
    state = fgc.load_state(
        root, baseline=baseline, commands=None, report_mode=True,
        report_path=root / fgc.DEFAULT_REPORT_PATH,
    )
    results, _overall = fgc.run_gate(state, FakeResolver(DAG, TIP))
    g09 = next(r for r in results if r.id == "G09")
    assert g09.status == fgc.STATUS_FAIL
    assert "dbx/migrations/evil.sql" in g09.details
    assert "db/migrations/0001_init.sql" not in g09.details
