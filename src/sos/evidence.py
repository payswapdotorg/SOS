"""W4 evidence/observability boundary for SOS.

Evidence is durable claim-supporting material, not an authority. W4 does not
infer causality, generate candidates, or execute experiments.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .model import JsonModelStore, ModelValidationError, Traceability, TruthState, TruthfulValue
from .recovery import RecoveryReport


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    TEST = "test"
    STATIC_ANALYSIS = "static-analysis"
    SIMULATION = "simulation"
    REPLAY = "replay"
    SHADOW = "shadow"
    CANARY = "canary"
    EXPERIMENT = "experiment"
    DEPLOYMENT = "deployment"
    USER_OUTCOME = "user outcome"
    BUSINESS_OUTCOME = "business outcome"
    INCIDENT = "incident"
    ROLLBACK = "rollback"


class EvidenceMode(str, Enum):
    OBSERVATIONAL = "OBSERVATIONAL"
    INTERVENTION = "INTERVENTION"


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    kind: EvidenceKind
    mode: EvidenceMode
    source_ref: str
    subject_ref: str
    timestamp: str
    environment: str
    result: TruthfulValue[Any]
    provenance: Mapping[str, str]
    confidence: float | None
    availability: TruthState
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.source_ref or not self.subject_ref or not self.timestamp:
            raise ModelValidationError("Evidence requires id, source_ref, subject_ref and timestamp")
        if not self.environment:
            raise ModelValidationError("Evidence requires an environment identifier")
        self.result.validate()
        required_provenance = {"source_revision", "observed_at"}
        if not required_provenance.issubset(self.provenance):
            raise ModelValidationError("Evidence provenance requires source_revision and observed_at")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ModelValidationError("Evidence confidence must be within [0, 1]")
        if self.result.state != self.availability and self.availability in {
            TruthState.FAILED, TruthState.UNKNOWN, TruthState.UNSUPPORTED, TruthState.UNAVAILABLE
        }:
            raise ModelValidationError("Unavailable evidence cannot claim a successful availability state")
        self.traceability.validate()
        if self.mode == EvidenceMode.OBSERVATIONAL and self.kind in {
            EvidenceKind.EXPERIMENT, EvidenceKind.CANARY, EvidenceKind.SHADOW, EvidenceKind.REPLAY, EvidenceKind.SIMULATION
        }:
            raise ModelValidationError("Intervention/experimental evidence kinds require INTERVENTION mode")


@dataclass(frozen=True)
class TelemetryEventEnvelope:
    """Collector-neutral OpenTelemetry-compatible event envelope."""

    event_id: str
    source: str
    resource: Mapping[str, str]
    timestamp: str
    attributes: Mapping[str, Any]

    def validate(self) -> None:
        if not self.event_id or not self.source or not self.timestamp:
            raise ModelValidationError("Telemetry envelope requires event_id, source and timestamp")


class EvidenceStore:
    """Append-only in-memory evidence boundary with deterministic export."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []

    def append(self, record: EvidenceRecord) -> None:
        record.validate()
        if any(existing.id == record.id for existing in self._records):
            raise ModelValidationError(f"Evidence id already exists: {record.id}")
        self._records.append(record)

    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records)

    def export_json(self, path: str | Path) -> None:
        payload = [
            {
                "id": record.id,
                "kind": record.kind.value,
                "mode": record.mode.value,
                "source_ref": record.source_ref,
                "subject_ref": record.subject_ref,
                "timestamp": record.timestamp,
                "environment": record.environment,
                "result": {"state": record.result.state.value, "value": record.result.value, "detail": record.result.detail},
                "provenance": dict(sorted(record.provenance.items())),
                "confidence": record.confidence,
                "availability": record.availability.value,
            }
            for record in sorted(self._records, key=lambda r: (r.timestamp, r.id))
        ]
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_from_recovery(report: RecoveryReport, *, observed_at: str, environment: str = "repository") -> tuple[EvidenceRecord, ...]:
    """Convert W3 recovery facts into static-analysis evidence without causal claims."""
    records: list[EvidenceRecord] = []
    for node in report.architecture.nodes:
        source_path = str(node.attributes["source_path"])
        records.append(
            EvidenceRecord(
                id=f"recovery:{report.repository_revision}:{node.id}",
                kind=EvidenceKind.STATIC_ANALYSIS,
                mode=EvidenceMode.OBSERVATIONAL,
                source_ref=f"repository:{source_path}",
                subject_ref=node.id,
                timestamp=observed_at,
                environment=environment,
                result=TruthfulValue(TruthState.SUCCESS, value={"node_type": node.type.value}),
                provenance={"source_revision": report.repository_revision, "observed_at": observed_at, "source_path": source_path},
                confidence=node.uncertainty.confidence,
                availability=TruthState.SUCCESS,
                traceability=report.architecture.traceability,
            )
        )
    for finding in report.findings:
        records.append(
            EvidenceRecord(
                id=f"recovery-finding:{report.repository_revision}:{finding.code}",
                kind=EvidenceKind.OBSERVATION,
                mode=EvidenceMode.OBSERVATIONAL,
                source_ref=f"repository:{report.repository_revision}",
                subject_ref=finding.subject,
                timestamp=observed_at,
                environment=environment,
                result=TruthfulValue(finding.state, detail=finding.detail),
                provenance={"source_revision": report.repository_revision, "observed_at": observed_at, "recovery_finding": finding.code},
                confidence=None,
                availability=finding.state,
                traceability=report.architecture.traceability,
            )
        )
    return tuple(sorted(records, key=lambda record: record.id))


def persist_records(records: Sequence[EvidenceRecord], path: str | Path) -> None:
    store = EvidenceStore()
    for record in records:
        store.append(record)
    store.export_json(path)
