"""W4 — evidence / observability boundary for SOS.

Establishes the evidence/observability boundary so observations can be attached
to the recovered System State / Architecture Graph with exact provenance and
truthful truth states, **without pretending telemetry establishes causality or
authorization** (frozen W4 Work Order; architecture §3.7, §13.6).

Design invariants:

- evidence records carry deterministic, content-addressed identity (no uuid4,
  no wall-clock) so repeated ingestion of identical evidence is stable;
- truthful states remain distinct: ``SUCCESS`` / ``FAILED`` / ``UNKNOWN`` /
  ``UNAVAILABLE`` / ``EMPTY`` are never conflated (reuses W1 ``TruthState`` /
  ``TruthfulValue`` — no competing truth authority);
- evidence references recovered W2/W3 subjects by id string without mutating
  the recovered graph (no semantic authority change);
- static/repository evidence does **not** fabricate runtime reality: missing
  runtime observations are recorded as ``UNKNOWN`` / ``UNAVAILABLE`` with an
  explanatory detail;
- an OpenTelemetry-shaped ingestion boundary accepts directly-supplied
  spans/metrics/logs but does **not** require a live collector and does not
  invent runtime facts when OTel fields are missing;
- W4 introduces evidence/observation only — no causal inference (W5), candidate
  search (W6), assurance (W7), experimentation/promotion/rollback (W8), or
  autonomy/ASK execution (W9).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue


# ---------------------------------------------------------------------------
# Frozen evidence vocabulary (architecture §3.7 / sos-meta-model Evidence kind)
# ---------------------------------------------------------------------------


class EvidenceKind(str, Enum):
    """Frozen evidence kinds (per spec/sos-meta-model.md)."""

    OBSERVATION = "observation"
    TEST = "test"
    STATIC_ANALYSIS = "static-analysis"
    SIMULATION = "simulation"
    REPLAY = "replay"
    SHADOW = "shadow"
    CANARY = "canary"
    EXPERIMENT = "experiment"
    DEPLOYMENT = "deployment"
    USER_OUTCOME = "user-outcome"
    BUSINESS_OUTCOME = "business-outcome"
    INCIDENT = "incident"
    ROLLBACK = "rollback"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceProvenance:
    """Exact provenance for an evidence record.

    ``implementation_revision`` is the exact repository revision the evidence
    pertains to, when applicable (None when not supplied — truthful, not
    fabricated). ``timestamp`` is the ISO-8601 observation time when actually
    supplied; None when not supplied.
    """

    source: str
    observed_subject: str
    timestamp: str | None
    environment: str | None
    implementation_revision: str | None

    def validate(self) -> None:
        if not self.source.strip():
            raise ModelValidationError("EvidenceProvenance.source is required")
        if not self.observed_subject.strip():
            raise ModelValidationError("EvidenceProvenance.observed_subject is required")
        if self.timestamp is not None and not self.timestamp.strip():
            raise ModelValidationError("EvidenceProvenance.timestamp must be non-empty when supplied")


# ---------------------------------------------------------------------------
# Evidence record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """A single evidence record linking an observation to a recovered subject.

    ``subject_ref`` is the id of a recovered System State / Architecture Graph
    entity. Evidence holds the reference; it never mutates the recovered graph.
    """

    id: str
    kind: EvidenceKind
    source_ref: str
    subject_ref: str
    timestamp: str | None
    environment: str | None
    result: TruthfulValue[Any]
    provenance: EvidenceProvenance
    confidence: float | None
    availability: TruthState
    traceability: Traceability

    def __post_init__(self) -> None:
        # Construction-time validation so malformed evidence is rejected at the
        # boundary (W4 criterion 7), not only on explicit .validate() calls.
        self.validate()

    def validate(self, *, known_subject_ids: set[str] | None = None) -> None:
        if not self.id or not self.id.strip():
            raise ModelValidationError("Evidence.id is required")
        if not isinstance(self.kind, EvidenceKind):
            raise ModelValidationError("Evidence.kind must be an EvidenceKind")
        if not self.source_ref or not self.source_ref.strip():
            raise ModelValidationError("Evidence.source_ref is required")
        if not self.subject_ref or not self.subject_ref.strip():
            raise ModelValidationError("Evidence.subject_ref is required")
        self.result.validate()  # truthful-state separation enforced by W1
        self.provenance.validate()
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ModelValidationError("Evidence.confidence must be within [0, 1] when supplied")
        if not isinstance(self.availability, TruthState):
            raise ModelValidationError("Evidence.availability must be a TruthState")
        # Availability is the evidence's own capture state; a SUCCESS availability
        # with a non-SUCCESS result is lawful (e.g. a successful capture of a
        # FAILED observation). But an UNAVAILABLE availability must not carry a
        # SUCCESS result — that would conflate capture-state with observed-state.
        if self.availability == TruthState.UNAVAILABLE and self.result.state == TruthState.SUCCESS:
            raise ModelValidationError(
                "UNAVAILABLE evidence must not carry a SUCCESS result (capture-state/observed-state conflation)"
            )
        self.traceability.validate(require_value=True, require_context=True)
        if known_subject_ids is not None and self.subject_ref not in known_subject_ids:
            raise ModelValidationError(
                f"Evidence.subject_ref '{self.subject_ref}' is not a known recovered subject"
            )


# ---------------------------------------------------------------------------
# Deterministic identity
# ---------------------------------------------------------------------------


def _evidence_id(
    kind: EvidenceKind,
    source_ref: str,
    subject_ref: str,
    result: TruthfulValue[Any],
    provenance: EvidenceProvenance,
) -> str:
    """Content-addressed identity: identical evidence ⇒ identical id (criterion 6)."""
    material = "|".join(
        [
            kind.value,
            source_ref,
            subject_ref,
            result.state.value,
            str(result.value),
            str(result.detail),
            provenance.source,
            provenance.observed_subject,
            provenance.timestamp or "",
            provenance.implementation_revision or "",
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"evidence-{digest}"


def _build_evidence(
    *,
    kind: EvidenceKind,
    source_ref: str,
    subject_ref: str,
    result: TruthfulValue[Any],
    provenance: EvidenceProvenance,
    traceability: Traceability,
    timestamp: str | None = None,
    environment: str | None = None,
    confidence: float | None = None,
    availability: TruthState = TruthState.SUCCESS,
) -> Evidence:
    """Assemble an Evidence record with a content-addressed id, constructing once."""
    provenance.validate()
    return Evidence(
        id=_evidence_id(kind, source_ref, subject_ref, result, provenance),
        kind=kind,
        source_ref=source_ref,
        subject_ref=subject_ref,
        timestamp=timestamp,
        environment=environment,
        result=result,
        provenance=provenance,
        confidence=confidence,
        availability=availability,
        traceability=traceability,
    )


# ---------------------------------------------------------------------------
# Evidence graph (deterministic ordering + dedup + subject index)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceGraph:
    """A deterministically-ordered collection of evidence records.

    Ingestion deduplicates by deterministic id and keeps records sorted by id,
    so identical inputs always produce identical graph identity/order.
    """

    id: str
    version: int
    records: tuple[Evidence, ...]
    traceability: Traceability

    def validate(self, *, known_subject_ids: set[str] | None = None) -> None:
        if not self.id or not self.id.strip():
            raise ModelValidationError("EvidenceGraph.id is required")
        if self.version < 1:
            raise ModelValidationError("EvidenceGraph.version must be >= 1")
        self.traceability.validate(require_value=True, require_context=True)
        seen: set[str] = set()
        for r in self.records:
            r.validate(known_subject_ids=known_subject_ids)
            if r.id in seen:
                raise ModelValidationError(f"EvidenceGraph contains duplicate evidence id {r.id}")
            seen.add(r.id)
        ids = [r.id for r in self.records]
        if ids != sorted(ids):
            raise ModelValidationError("EvidenceGraph.records must be sorted by id")

    def ingest(self, evidence: Evidence) -> "EvidenceGraph":
        """Return a new graph with ``evidence`` added; dedup by id; keep sorted."""
        evidence.validate()
        records = list(self.records)
        if any(r.id == evidence.id for r in records):
            # Deterministic duplicate ingestion: identical evidence does not duplicate.
            return self
        records.append(evidence)
        records.sort(key=lambda r: r.id)
        return EvidenceGraph(
            id=self.id,
            version=self.version,
            records=tuple(records),
            traceability=self.traceability,
        )

    def by_subject(self, subject_ref: str) -> tuple[Evidence, ...]:
        return tuple(r for r in self.records if r.subject_ref == subject_ref)


# ---------------------------------------------------------------------------
# Static evidence adapter — does not invent runtime facts
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Static evidence adapter — does not invent runtime facts
# ---------------------------------------------------------------------------


class StaticEvidenceAdapter:
    """Ingests static/test evidence. Does NOT fabricate runtime observations."""

    @staticmethod
    def from_test_result(
        *,
        subject_ref: str,
        test_name: str,
        result: TruthfulValue[Any],
        traceability: Traceability,
        provenance: EvidenceProvenance,
        timestamp: str | None = None,
        environment: str | None = None,
        confidence: float | None = None,
    ) -> Evidence:
        if not test_name.strip():
            raise ModelValidationError("test_name is required")
        return _build_evidence(
            kind=EvidenceKind.TEST,
            source_ref=test_name,
            subject_ref=subject_ref,
            result=result,
            provenance=provenance,
            traceability=traceability,
            timestamp=timestamp,
            environment=environment,
            confidence=confidence,
            availability=TruthState.SUCCESS,
        )

    @staticmethod
    def from_static_observation(
        *,
        subject_ref: str,
        observation: str,
        result: TruthfulValue[Any],
        traceability: Traceability,
        provenance: EvidenceProvenance,
        timestamp: str | None = None,
        environment: str | None = None,
        confidence: float | None = None,
    ) -> Evidence:
        if not observation.strip():
            raise ModelValidationError("observation is required")
        return _build_evidence(
            kind=EvidenceKind.OBSERVATION,
            source_ref=observation,
            subject_ref=subject_ref,
            result=result,
            provenance=provenance,
            traceability=traceability,
            timestamp=timestamp,
            environment=environment,
            confidence=confidence,
            availability=TruthState.SUCCESS,
        )

    @staticmethod
    def unavailable_runtime_observation(
        *,
        subject_ref: str,
        dimension: str,
        reason: str,
        traceability: Traceability,
        provenance: EvidenceProvenance,
        timestamp: str | None = None,
        environment: str | None = None,
    ) -> Evidence:
        """Record an unavailable runtime observation explicitly — never synthesized."""
        if not dimension.strip():
            raise ModelValidationError("dimension is required")
        if not reason.strip():
            raise ModelValidationError("reason is required")
        result = TruthfulValue(TruthState.UNAVAILABLE, None, reason)
        return _build_evidence(
            kind=EvidenceKind.OBSERVATION,
            source_ref=f"unavailable:{dimension}",
            subject_ref=subject_ref,
            result=result,
            provenance=provenance,
            traceability=traceability,
            timestamp=timestamp,
            environment=environment,
            confidence=None,
            availability=TruthState.UNAVAILABLE,
        )


# ---------------------------------------------------------------------------
# OpenTelemetry-shaped ingestion boundary (no live collector; no fabrication)
# ---------------------------------------------------------------------------


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s if s.strip() else None


class OpenTelemetryShapedAdapter:
    """Accepts OTel-shaped spans/metrics/logs supplied as mappings.

    No live collector is required. Missing runtime fields stay UNKNOWN /
    UNAVAILABLE rather than being fabricated as successful values.
    """

    @staticmethod
    def from_otel_span(
        *,
        span: Mapping[str, Any],
        subject_ref: str,
        traceability: Traceability,
        provenance: EvidenceProvenance,
    ) -> Evidence:
        span_id = _as_str(span.get("span_id")) or "unknown-span"
        status = span.get("status")
        has_end = span.get("end_time_unix_nano") is not None
        if status is None or not has_end:
            # Incomplete runtime observation — record UNKNOWN, not a fabricated SUCCESS.
            detail = "otel span missing status or end_time; runtime observation incomplete"
            result: TruthfulValue[Any] = TruthfulValue(TruthState.UNKNOWN, None, detail)
            availability = TruthState.UNKNOWN
        else:
            code = _as_str(status.get("code")) if isinstance(status, Mapping) else None
            if code == "ERROR":
                msg = _as_str(status.get("message")) if isinstance(status, Mapping) else None
                result = TruthfulValue(TruthState.FAILED, None, msg or "otel span reported ERROR")
                availability = TruthState.SUCCESS  # capture succeeded; observation failed
            else:
                result = TruthfulValue(TruthState.SUCCESS, code or "OK", None)
                availability = TruthState.SUCCESS
        return _build_evidence(
            kind=EvidenceKind.OBSERVATION,
            source_ref=span_id,
            subject_ref=subject_ref,
            result=result,
            provenance=provenance,
            traceability=traceability,
            timestamp=_as_str(span.get("start_time_unix_nano")),
            environment=provenance.environment,
            confidence=None,
            availability=availability,
        )

    @staticmethod
    def from_otel_metric(
        *,
        metric: Mapping[str, Any],
        subject_ref: str,
        traceability: Traceability,
        provenance: EvidenceProvenance,
    ) -> Evidence:
        name = _as_str(metric.get("name")) or "unknown-metric"
        value = metric.get("value")
        if value is None:
            result: TruthfulValue[Any] = TruthfulValue(
                TruthState.UNKNOWN, None, "otel metric carried no value"
            )
            availability = TruthState.UNKNOWN
        else:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                result = TruthfulValue(
                    TruthState.FAILED, None, f"otel metric value not numeric: {value!r}"
                )
                availability = TruthState.SUCCESS
            else:
                result = TruthfulValue(TruthState.SUCCESS, numeric, None)
                availability = TruthState.SUCCESS
        return _build_evidence(
            kind=EvidenceKind.OBSERVATION,
            source_ref=name,
            subject_ref=subject_ref,
            result=result,
            provenance=provenance,
            traceability=traceability,
            timestamp=_as_str(metric.get("time_unix_nano")),
            environment=provenance.environment,
            confidence=None,
            availability=availability,
        )

    @staticmethod
    def from_otel_log(
        *,
        log: Mapping[str, Any],
        subject_ref: str,
        traceability: Traceability,
        provenance: EvidenceProvenance,
    ) -> Evidence:
        severity = _as_str(log.get("severity_text")) or "INFO"
        body = _as_str(log.get("body"))
        if body is None:
            result: TruthfulValue[Any] = TruthfulValue(TruthState.UNKNOWN, None, "otel log carried no body")
            availability = TruthState.UNKNOWN
        else:
            result = TruthfulValue(TruthState.SUCCESS, body, None)
            availability = TruthState.SUCCESS
        return _build_evidence(
            kind=EvidenceKind.OBSERVATION,
            source_ref=severity,
            subject_ref=subject_ref,
            result=result,
            provenance=provenance,
            traceability=traceability,
            timestamp=_as_str(log.get("time_unix_nano")),
            environment=provenance.environment,
            confidence=None,
            availability=availability,
        )
