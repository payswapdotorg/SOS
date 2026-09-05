from pathlib import Path

import pytest

from sos import (
    EvidenceKind,
    EvidenceMode,
    EvidenceRecord,
    EvidenceStore,
    ModelValidationError,
    TelemetryEventEnvelope,
    Traceability,
    TruthState,
    TruthfulValue,
    evidence_from_recovery,
    recover_repository,
)


def trace():
    return Traceability("constitution:1", "mission:1", "value:1", "context:1")


def test_evidence_record_requires_provenance_and_truthful_result():
    record = EvidenceRecord(
        id="e1", kind=EvidenceKind.OBSERVATION, mode=EvidenceMode.OBSERVATIONAL,
        source_ref="sensor:1", subject_ref="system-state:1", timestamp="2026-09-05T15:00:00Z",
        environment="prod", result=TruthfulValue(TruthState.SUCCESS, value={"latency_ms": 12}),
        provenance={"source_revision": "rev-1", "observed_at": "2026-09-05T15:00:00Z"},
        confidence=0.8, availability=TruthState.SUCCESS, traceability=trace(),
    )
    record.validate()
    with pytest.raises(ModelValidationError):
        EvidenceRecord(
            **{**record.__dict__, "provenance": {"source_revision": "rev-1"}}
        ).validate()


def test_failed_unknown_and_unavailable_are_not_success():
    for state in (TruthState.FAILED, TruthState.UNKNOWN, TruthState.UNAVAILABLE):
        record = EvidenceRecord(
            id=f"e-{state.value}", kind=EvidenceKind.OBSERVATION, mode=EvidenceMode.OBSERVATIONAL,
            source_ref="sensor:1", subject_ref="system-state:1", timestamp="2026-09-05T15:00:00Z",
            environment="prod", result=TruthfulValue(state, detail="not observable"),
            provenance={"source_revision": "rev-1", "observed_at": "2026-09-05T15:00:00Z"},
            confidence=None, availability=state, traceability=trace(),
        )
        record.validate()


def test_experimental_kind_must_be_marked_intervention():
    record = EvidenceRecord(
        id="e1", kind=EvidenceKind.EXPERIMENT, mode=EvidenceMode.OBSERVATIONAL,
        source_ref="exp:1", subject_ref="system-state:1", timestamp="2026-09-05T15:00:00Z",
        environment="prod", result=TruthfulValue(TruthState.SUCCESS, value=True),
        provenance={"source_revision": "rev-1", "observed_at": "2026-09-05T15:00:00Z"},
        confidence=0.9, availability=TruthState.SUCCESS, traceability=trace(),
    )
    with pytest.raises(ModelValidationError):
        record.validate()


def test_store_is_append_only_and_export_is_deterministic(tmp_path: Path):
    def record(identifier: str) -> EvidenceRecord:
        return EvidenceRecord(
            id=identifier, kind=EvidenceKind.TEST, mode=EvidenceMode.OBSERVATIONAL,
            source_ref="ci", subject_ref="system-state:1", timestamp="2026-09-05T15:00:00Z",
            environment="ci", result=TruthfulValue(TruthState.SUCCESS, value=True),
            provenance={"source_revision": "rev-1", "observed_at": "2026-09-05T15:00:00Z"},
            confidence=1.0, availability=TruthState.SUCCESS, traceability=trace(),
        )
    store = EvidenceStore()
    store.append(record("e2"))
    store.append(record("e1"))
    with pytest.raises(ModelValidationError):
        store.append(record("e1"))
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    store.export_json(first)
    store.export_json(second)
    assert first.read_text() == second.read_text()


def test_telemetry_envelope_preserves_source_resource_time_and_attributes():
    event = TelemetryEventEnvelope("event-1", "otel", {"service.name": "sos"}, "2026-09-05T15:00:00Z", {"latency_ms": 4})
    event.validate()


def test_recovery_adapter_emits_static_evidence_without_causal_claims(tmp_path: Path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    report = recover_repository(tmp_path, repository_revision="rev-1", traceability=trace())
    records = evidence_from_recovery(report, observed_at="2026-09-05T15:00:00Z")
    assert any(record.kind == EvidenceKind.STATIC_ANALYSIS for record in records)
    assert all(record.mode == EvidenceMode.OBSERVATIONAL for record in records)
