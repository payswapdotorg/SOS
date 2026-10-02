"""The provider-neutral GitHub source seam (directive §10: repository
discovery, branch/commit lookup, exact revision pinning, source metadata)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SeamHealth:
    status: str  # a sos.model.TruthState value, reported verbatim
    detail: str


@dataclass(frozen=True)
class RepositoryInfo:
    url: str
    name: str
    owner: str
    default_branch: str
    fixture: bool  # True = canned LOCAL fixture metadata (clearly labeled)


@dataclass(frozen=True)
class BranchInfo:
    name: str
    head_sha: str


@dataclass(frozen=True)
class CommitInfo:
    sha: str  # exact 40-hex commit — the ONLY lawful immutable revision pin
    message: str
    authored_at: str
    author: str
    fixture: bool


class GitHubSourcePort(Protocol):
    mode: str
    implementation: str

    def health_check(self) -> SeamHealth: ...

    def resolve_repository(self, url: str) -> RepositoryInfo: ...

    def list_branches(self, url: str) -> tuple[BranchInfo, ...]: ...

    def list_commits(self, url: str, *, ref: str,
                     limit: int) -> tuple[CommitInfo, ...]: ...

    def get_commit(self, url: str, sha: str) -> CommitInfo: ...
