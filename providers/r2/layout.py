"""The deterministic directive §12 artifact key layout (PUB-07).

Single layout authority shared by BOTH artifact-store implementations
(LOCAL content-addressed filesystem store and the R2 S3-compatible
adapter) — the same inputs MUST produce the same key on either adapter
(determinism is what makes LOCAL↔PUBLIC parity and `evidence_artifacts`
metadata rows portable across backends):

``tenants/{tenantId}/systems/{systemId}/revisions/{revisionId}`` |
``.../recovery/{jobId}`` | ``.../evidence/{evidenceId}`` |
``.../experiments/{experimentId}`` |
``.../executions/{executionId}/{logs|reports|receipts|bundles}``

Object names are content-addressed by PUB-07's write paths
(:func:`build_key` mints exactly ``{sha256}`` or ``{sha256}-{filename}``).
Directive §12 says "use content hashes WHENEVER POSSIBLE": the READ paths
(parse/validate) therefore accept any SAFE object name under the governed
tree — the pre-PUB-07 demo seed already records short-hash receipt
references (``{16-hex}.json``), and the honest treatment of those keys is
a lawful tree key whose bytes are simply absent, not an unlawful key.
Content-address VERIFICATION (:func:`key_content_hash`) is the write-path
law: it demands the exact 64-hex prefix.

Segment rules (enforced on BUILD and on PARSE — the parse side is the
path-traversal defense for the LOCAL filesystem store): a segment may not
be empty, ``.`` or ``..``, may not contain ``/``, ``\\`` or NUL, and is
length-bounded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Directive §12 layout categories (binding — restated by infra/r2/README.md).
CATEGORIES = frozenset({
    "revisions", "recovery", "evidence", "experiments", "executions",
})
EXECUTION_SUBCATEGORIES = frozenset({"logs", "reports", "receipts", "bundles"})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_SEGMENT = 256


class InvalidArtifactKey(ValueError):
    """A key/segment violates the §12 layout (unusable, never stored)."""


def validate_segment(value: str, name: str) -> str:
    """One layout path segment: non-empty, no separators, no traversal."""
    if not isinstance(value, str) or not value:
        raise InvalidArtifactKey(f"artifact key segment {name!r} is empty")
    if len(value) > _MAX_SEGMENT:
        raise InvalidArtifactKey(
            f"artifact key segment {name!r} exceeds {_MAX_SEGMENT} chars"
        )
    if value in (".", ".."):
        raise InvalidArtifactKey(
            f"artifact key segment {name!r} is a traversal segment"
        )
    if "/" in value or "\\" in value or "\x00" in value:
        raise InvalidArtifactKey(
            f"artifact key segment {name!r} contains a path separator"
        )
    return value


def validate_content_hash(content_hash: str) -> str:
    """The content hash for build_key: exactly 64 lowercase hex."""
    if not isinstance(content_hash, str) or not _HEX64.match(content_hash):
        raise InvalidArtifactKey(
            "content hash must be exactly 64 lowercase hex characters "
            "(sha256) for the content-addressed §12 key"
        )
    return content_hash


def build_key(
    tenant_id: str,
    system_id: str,
    *,
    category: str,
    context_id: str,
    subcategory: str,
    content_hash: str,
    filename: str,
) -> str:
    """Build the deterministic §12 key for one artifact (the WRITE path).

    ``content_hash`` is the sha256 of the artifact bytes (content
    addressing); ``filename`` is an OPTIONAL safe suffix appended after
    the hash as ``-{filename}`` (human-meaningful only — the hash is the
    address).
    """
    validate_segment(tenant_id, "tenantId")
    validate_segment(system_id, "systemId")
    validate_segment(context_id, "contextId")
    validate_content_hash(content_hash)
    if category not in CATEGORIES:
        raise InvalidArtifactKey(f"unknown artifact category '{category}'")
    if filename:
        validate_segment(filename, "filename")
    parts = [f"tenants/{tenant_id}", f"systems/{system_id}"]
    if category == "executions":
        if subcategory not in EXECUTION_SUBCATEGORIES:
            raise InvalidArtifactKey(
                f"unknown execution artifact subcategory '{subcategory}'"
            )
        parts.append(f"{category}/{context_id}/{subcategory}")
    else:
        if subcategory:
            raise InvalidArtifactKey(
                f"subcategory is only lawful for executions, got "
                f"'{subcategory}'"
            )
        parts.append(f"{category}/{context_id}")
    name = content_hash if not filename else f"{content_hash}-{filename}"
    return "/".join(parts) + "/" + name


@dataclass(frozen=True)
class KeyParts:
    """The parsed components of one §12 tree key.

    ``content_hash`` is the 64-hex content address WHEN the object name
    carries one (the PUB-07 write-path law); ``""`` for legacy safe names
    (e.g. the demo seed's short-hash receipt references). ``filename`` is
    the human-meaningful suffix after ``-{...}`` when present.
    """

    key: str
    tenant_id: str
    system_id: str
    category: str
    context_id: str
    subcategory: str  # "" for non-execution categories
    name: str  # the object-name segment, verbatim
    content_hash: str  # 64-hex prefix when content-addressed, else ""
    filename: str  # suffix after the hash when addressed, else ""


def parse_key(key: str) -> KeyParts:
    """Parse + fully validate one §12 TREE key (the traversal defense).

    Raises :class:`InvalidArtifactKey` for anything outside the governed
    layout — separator tricks, unknown categories, wrong depth. The
    object NAME must be a safe segment; whether it is content-addressed
    is a write-path question (:func:`key_content_hash`).
    """
    if not isinstance(key, str) or not key:
        raise InvalidArtifactKey("artifact key is empty")
    if "\\" in key or "\x00" in key:
        raise InvalidArtifactKey("artifact key contains an illegal character")
    segments = key.split("/")
    if len(segments) not in (7, 8):
        raise InvalidArtifactKey(
            f"artifact key must have the §12 layout depth, got {len(segments)}"
        )
    if segments[0] != "tenants" or segments[2] != "systems":
        raise InvalidArtifactKey(
            "artifact key must start tenants/{tenantId}/systems/{systemId}"
        )
    tenant_id = validate_segment(segments[1], "tenantId")
    system_id = validate_segment(segments[3], "systemId")
    category = segments[4]
    if category not in CATEGORIES:
        raise InvalidArtifactKey(f"unknown artifact category '{category}'")
    name = validate_segment(segments[-1], "objectName")
    content_hash = name[:64] if _HEX64.match(name[:64]) else ""
    filename = ""
    if content_hash and name[64:]:
        filename = name[64:]
        if filename.startswith("-"):
            filename = filename[1:]
        validate_segment(filename, "filename")
    if category == "executions":
        if len(segments) != 8:
            raise InvalidArtifactKey(
                "execution artifact keys carry the {subcategory} segment"
            )
        context_id = validate_segment(segments[5], "contextId")
        subcategory = segments[6]
        if subcategory not in EXECUTION_SUBCATEGORIES:
            raise InvalidArtifactKey(
                f"unknown execution artifact subcategory '{subcategory}'"
            )
    else:
        if len(segments) != 7:
            raise InvalidArtifactKey(
                "non-execution artifact keys carry no subcategory segment"
            )
        context_id = validate_segment(segments[5], "contextId")
        subcategory = ""
    return KeyParts(
        key=key, tenant_id=tenant_id, system_id=system_id, category=category,
        context_id=context_id, subcategory=subcategory, name=name,
        content_hash=content_hash, filename=filename,
    )


def key_content_hash(key: str) -> str:
    """The content address of one §12 key — the WRITE-path law.

    Raises :class:`InvalidArtifactKey` when the object name is not the
    64-hex content address (legacy names cannot be written through the
    content-addressed redemption path).
    """
    parts = parse_key(key)
    if not parts.content_hash:
        raise InvalidArtifactKey(
            "artifact object name is not content-addressed (64-hex sha256 "
            "prefix required for writes); this key is read-only legacy "
            "surface"
        )
    return parts.content_hash
