"""LOCAL GitHub source adapter: canned fixture metadata (PUB-01).

Deterministic repository/branch/commit metadata for the brownfield
onboarding flow — clearly labeled ``fixture: true`` on every record so it can
never masquerade as live GitHub data. The fixture commit SHAs are stable
40-hex values; the fixture repository tree (for architecture recovery) lives
at ``providers/github/fixtures/demo-repo``.
"""
from __future__ import annotations

import hashlib

from .seam import BranchInfo, CommitInfo, RepositoryInfo, SeamHealth

FIXTURE_REPO_URL = "https://github.com/sos-demo/example-api"

# Deterministic fixture commits (stable 40-hex; content-derived).
_FIXTURE_COMMITS: tuple[tuple[str, str, str, str], ...] = (
    (
        hashlib.sha256(b"sos-fixture-commit-1").hexdigest(),
        "Initial service skeleton: API layer, SQLite store, background worker",
        "2026-01-12T09:15:00Z",
        "fixture-author@sos.demo",
    ),
    (
        hashlib.sha256(b"sos-fixture-commit-2").hexdigest(),
        "Add caching layer in front of the query path",
        "2026-02-03T14:40:00Z",
        "fixture-author@sos.demo",
    ),
    (
        hashlib.sha256(b"sos-fixture-commit-3").hexdigest(),
        "Harden worker retry policy and pin dependency versions",
        "2026-03-21T11:05:00Z",
        "fixture-author@sos.demo",
    ),
)


class UnknownRepositoryError(Exception):
    """The repository URL is not present in the LOCAL fixture set."""


class UnknownCommitError(Exception):
    """The ref/SHA is not present in the LOCAL fixture set."""


class LocalFixtureGitHubSource:
    """The LOCAL (canned fixture) implementation of the GitHub source seam."""

    mode = "local"
    implementation = "fixture"

    def __init__(self, *, known_urls: tuple[str, ...] = (FIXTURE_REPO_URL,)):
        self._known_urls = known_urls

    def health_check(self) -> SeamHealth:
        return SeamHealth(
            status="SUCCESS",
            detail="local fixture GitHub source ok "
            f"({len(self._known_urls)} canned repositories)",
        )

    def resolve_repository(self, url: str) -> RepositoryInfo:
        if url not in self._known_urls:
            raise UnknownRepositoryError(
                f"repository '{url}' is not available in the LOCAL fixture "
                "set (known: " + ", ".join(self._known_urls) + ")"
            )
        return RepositoryInfo(
            url=url,
            name="example-api",
            owner="sos-demo",
            default_branch="main",
            fixture=True,
        )

    def list_branches(self, url: str) -> tuple[BranchInfo, ...]:
        self.resolve_repository(url)
        return (
            BranchInfo(
                name="main",
                head_sha=_FIXTURE_COMMITS[-1][0],
            ),
            BranchInfo(
                name="staging",
                head_sha=_FIXTURE_COMMITS[1][0],
            ),
        )

    def list_commits(self, url: str, *, ref: str,
                     limit: int) -> tuple[CommitInfo, ...]:
        self.resolve_repository(url)
        if ref == "main":
            order = (2, 1, 0)
        elif ref == "staging":
            order = (1, 0)
        elif ref in {sha for sha, *_ in _FIXTURE_COMMITS}:
            idx = next(
                i for i, (sha, *_rest) in enumerate(_FIXTURE_COMMITS)
                if sha == ref
            )
            order = (idx,)
        else:
            raise UnknownCommitError(
                f"ref '{ref}' is not present in the LOCAL fixture repository"
            )
        commits = tuple(
            CommitInfo(
                sha=_FIXTURE_COMMITS[i][0],
                message=_FIXTURE_COMMITS[i][1],
                authored_at=_FIXTURE_COMMITS[i][2],
                author=_FIXTURE_COMMITS[i][3],
                fixture=True,
            )
            for i in order
        )
        return commits[:limit]

    def get_commit(self, url: str, sha: str) -> CommitInfo:
        commits = self.list_commits(url, ref=sha, limit=1)
        if not commits:
            raise UnknownCommitError(f"commit '{sha}' not in fixture set")
        return commits[0]

    @staticmethod
    def fixture_commits() -> tuple[CommitInfo, ...]:
        return tuple(
            CommitInfo(
                sha=sha, message=message, authored_at=authored_at,
                author=author, fixture=True,
            )
            for sha, message, authored_at, author in _FIXTURE_COMMITS
        )
