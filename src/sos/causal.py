"""W5 causal knowledge and architecture memory boundary."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Mapping, Sequence

from .evidence import EvidenceMode, EvidenceRecord
from .model import JsonModelStore, ModelValidationError, Traceability


class HypothesisStatus(str, Enum):
    PROPOSED = "PROPOSED"
    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CausalHypothesis:
    id: str
    cause: str
    mechanism: str
    effect: str
    context: str
    expected_direction: str
    expected_magnitude: str
    confidence: float
    evidence_refs: tuple[str, ...]
    status: HypothesisStatus
    traceability: Traceability

    def validate(self) -> None:
        if not all((self.id, self.cause, self.mechanism, self.effect, self.context, self.expected_direction, self.expected_magnitude)):
            raise ModelValidationError("CausalHypothesis requires cause, mechanism, effect, context and expected effect details")
        if not 0 <= self.confidence <= 1:
            raise ModelValidationError("Causal hypothesis confidence must be within [0, 1]")
        if not self.evidence_refs:
            raise ModelValidationError("CausalHypothesis requires evidence references")
        self.traceability.validate()

    def eligible_for_high_impact(self, evidence: Mapping[str, EvidenceRecord]) -> bool:
        """High-impact use requires at least one intervention-based supporting record."""
        self.validate()
        supporting = [evidence[ref] for ref in self.evidence_refs if ref in evidence]
        return any(record.mode == EvidenceMode.INTERVENTION for record in supporting)


@dataclass(frozen=True)
class ArchitectureMemory:
    id: str
    context_signature: str
    candidate_pattern: str
    predictions: tuple[str, ...]
    observations: tuple[str, ...]
    outcome: str
    learned_rule: str
    provenance: Mapping[str, str]
    confidence: float
    traceability: Traceability

    def validate(self) -> None:
        if not self.id or not self.context_signature or not self.candidate_pattern or not self.outcome or not self.learned_rule:
            raise ModelValidationError("ArchitectureMemory requires context, candidate pattern, outcome and learned rule")
        if not 0 <= self.confidence <= 1:
            raise ModelValidationError("Architecture memory confidence must be within [0, 1]")
        if "source_revision" not in self.provenance or "recorded_at" not in self.provenance:
            raise ModelValidationError("ArchitectureMemory provenance requires source_revision and recorded_at")
        self.traceability.validate()


class ArchitectureMemoryStore:
    """Append-only memory store; memory is prior experience, not proof."""

    def __init__(self) -> None:
        self._items: list[ArchitectureMemory] = []

    def append(self, item: ArchitectureMemory) -> None:
        item.validate()
        if any(existing.id == item.id for existing in self._items):
            raise ModelValidationError(f"ArchitectureMemory id already exists: {item.id}")
        self._items.append(item)

    def records(self) -> tuple[ArchitectureMemory, ...]:
        return tuple(self._items)

    def export_json(self, path: str | Path) -> None:
        payload = [
            {
                "id": item.id,
                "context_signature": item.context_signature,
                "candidate_pattern": item.candidate_pattern,
                "predictions": list(item.predictions),
                "observations": list(item.observations),
                "outcome": item.outcome,
                "learned_rule": item.learned_rule,
                "provenance": dict(sorted(item.provenance.items())),
                "confidence": item.confidence,
            }
            for item in sorted(self._items, key=lambda x: x.id)
        ]
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def record_memory(
    *,
    identifier: str,
    context_signature: str,
    candidate_pattern: str,
    predictions: Sequence[str],
    observations: Sequence[str],
    outcome: str,
    learned_rule: str,
    source_revision: str,
    recorded_at: str,
    confidence: float,
    traceability: Traceability,
) -> ArchitectureMemory:
    item = ArchitectureMemory(
        id=identifier,
        context_signature=context_signature,
        candidate_pattern=candidate_pattern,
        predictions=tuple(predictions),
        observations=tuple(observations),
        outcome=outcome,
        learned_rule=learned_rule,
        provenance={"source_revision": source_revision, "recorded_at": recorded_at},
        confidence=confidence,
        traceability=traceability,
    )
    item.validate()
    return item
