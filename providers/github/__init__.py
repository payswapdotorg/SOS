"""GitHub source-control seam (provider-neutral) — PUB-01.

Used for brownfield onboarding: repository discovery, branch/commit lookup,
exact revision pinning (directive §10). The LOCAL implementation serves
canned fixture metadata (clearly labeled) so brownfield flows are testable
without network or credentials; the real GitHub adapter (read-scope PAT)
arrives with PUB-04+. Immutable source references are ALWAYS exact commit
SHAs — "latest main" is never persisted as an immutable ref (SECURITY S11).
"""
from .local import FIXTURE_REPO_URL, LocalFixtureGitHubSource
from .seam import BranchInfo, CommitInfo, GitHubSourcePort, RepositoryInfo, SeamHealth

__all__ = [
    "FIXTURE_REPO_URL",
    "BranchInfo",
    "CommitInfo",
    "GitHubSourcePort",
    "LocalFixtureGitHubSource",
    "RepositoryInfo",
    "SeamHealth",
]
