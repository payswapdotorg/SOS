"""Real GitHub adapter — FAIL-CLOSED placeholder (PUB-04+ pending).

The live GitHub adapter (read-scope PAT, REST/GraphQL) arrives after PUB-04.
Selecting cloud GitHub source before it lands aborts with a precise message —
never a silent fallback to fixture metadata (fail-closed config).
"""
from __future__ import annotations


class GitHubCloudAdapterUnavailable(Exception):
    """Raised when the cloud GitHub adapter is selected before it exists."""


def build_github_cloud_source(pat: str):  # pragma: no cover - PUB-04+
    del pat
    raise GitHubCloudAdapterUnavailable(
        "The live GitHub source adapter (SOS_GITHUB_SOURCE_PAT) is delivered "
        "after PUB-04 (not yet merged). Refusing to boot: no silent fallback "
        "to the LOCAL fixture adapter is permitted."
    )
