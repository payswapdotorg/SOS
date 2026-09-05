"""W5 — causal knowledge + architecture memory boundary for SOS.

Represents causal knowledge and architecture memory over the W2 System State /
Architecture Graph using W4 evidence, while keeping causal claims explicitly
uncertain, provenance-backed, versioned, and **non-authorizing** (frozen W5
Work Order; architecture §§3.8–3.9, §13.4–3.5).

Design invariants:

- causal hypotheses carry deterministic, content-addressed identity spanning
  the full claim semantics + supporting evidence ids (no uuid4, no wall-clock);
- every non-empty causal claim references one or more existing W4 evidence ids;
  unsupported claims survive only as explicit hypotheses with non-SUCCESS
  uncertainty (no implied truth);
- observation vs intervention is an explicit distinction: an observation-only
  evidence id cannot be encoded as intervention support, and intervention
  support requires explicit ``InterventionMetadata`` + provenance actually
  supplied by the source;
- truthful uncertainty: UNKNOWN/FAILED/UNAVAILABLE evidence cannot be silently
  converted into positive causal support; contradictory hypotheses coexist
  rather than one being silently deleted;
- architecture memory is a versioned projection that references the recovered
  W2/W3 graph by id; it never mutates the canonical graph and never silently
  replaces architecture truth;
- W5 is non-authorizing and introduces no W6+ (candidate/search, assurance,
  experimentation/promotion/rollback, autonomy/ASK, personalization) semantics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .model import ModelValidationError, Traceability, TruthState, TruthfulValue


# ---------------------------------------------------------------------------
# Frozen causal vocabulary
# ---------------------------------------------------------------------------


class CausalRelationType(str, Enum):
    """Causal relation vocabulary (architecture §3.8 / meta-model CausalHypothesis)."""

    INFLUENCES = "influences"
    CONSTRAINS = "constrains"
    REALIZES = "realizes"
    OBSERVES = "observes"
    OWNS = "owns"


class SupportKind(str, Enum):
    """How a piece of W4 evidence supports a causal claim.

    Observation-only support cannot establish intervention efficacy; intervention
    support requires explicit ``InterventionMetadata``.
    """

    OBSERVATIONAL = "observational"
    INTERVENTION = "intervention"


@dataclass(frozen=True)
class InterventionMetadata:
    """Explicit metadata required for intervention-grade support (architecture §13.4)."""

    intervention_id: str
    intervention_kind: str
    applied_at: str
    revision: str
    environment: str

    def validate(self) -> None:
        for name, value in (
            ("intervention_id", self.intervention_id),
            ("intervention_kind", self.intervention_kind),
            ("applied_at", self.applied_at),
            ("revision", self.revision),
            ("environment", self.environment),
        ):
            if not value or not value.strip():
                raise ModelValidationError(f"InterventionMetadata.{name} is required")


# ---------------------------------------------------------------------------
# Evidence support reference (links a causal claim to W4 evidence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceSupport:
    """A reference from a causal claim to a W4 evidence record + how it supports."""

    evidence_id: str
    support_kind: SupportKind
    intervention: InterventionMetadata | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.evidence_id or not self.evidence_id.strip():
            raise ModelValidationError("EvidenceSupport.evidence_id is required")
        if not isinstance(self.support_kind, SupportKind):
            raise ModelValidationError("EvidenceSupport.support_kind must be a SupportKind")
        if self.support_kind == SupportKind.INTERVENTION:
            if self.intervention is None:
                raise ModelValidationError(
                    "INTERVENTION support requires explicit InterventionMetadata"
                )
            self.intervention.validate()
        elif self.intervention is not None:
            raise ModelValidationError(
                "OBSERVATIONAL support must not carry InterventionMetadata"
            )


# ---------------------------------------------------------------------------
# Causal hypothesis
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CausalHypothesis:
    """A causal claim linking named subjects/architecture entities.

    ``uncertainty`` is a W1 ``TruthfulValue`` — the hypothesis is never silently
    certain. ``status`` is the hypothesis lifecycle (proposed → supported →
    confirmed), and promotion to ``confirmed`` requires intervention-grade
    support (architecture §13.4: intervention evidence outranks observational
    correlation for causal claims).
    """

    cause_subject: str
    effect_subject: str
    relation_type: CausalRelationType
    direction: str
    rationale: str
    status: str
    uncertainty: TruthfulValue[Any]
    supporting_evidence: tuple[EvidenceSupport, ...]
    traceability: Traceability
    provenance_revision: str
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", _hypothesis_id(self))
        self.validate()

    def validate(
        self,
        *,
        known_evidence_ids: set[str] | None = None,
        known_evidence_results: dict[str, TruthState] | None = None,
    ) -> None:
        if not self.cause_subject.strip() or not self.effect_subject.strip():
            raise ModelValidationError("CausalHypothesis requires cause_subject and effect_subject")
        if not isinstance(self.relation_type, CausalRelationType):
            raise ModelValidationError("CausalHypothesis.relation_type must be a CausalRelationType")
        if not self.direction.strip():
            raise ModelValidationError("CausalHypothesis.direction is required")
        if not self.rationale.strip():
            raise ModelValidationError("CausalHypothesis.rationale is required")
        if not self.provenance_revision.strip():
            raise ModelValidationError("CausalHypothesis.provenance_revision is required")
        if self.status not in ("proposed", "supported", "confirmed", "rejected"):
            raise ModelValidationError(f"CausalHypothesis.status '{self.status}' is not a known lifecycle state")
        self.uncertainty.validate()
        self.traceability.validate(require_value=True, require_context=True)
        # An unsupported claim must carry non-SUCCESS uncertainty (no implied truth).
        if len(self.supporting_evidence) == 0 and self.uncertainty.state == TruthState.SUCCESS:
            raise ModelValidationError(
                "an unsupported causal claim must not claim SUCCESS uncertainty (no implied truth)"
            )
        for support in self.supporting_evidence:
            support.validate()
            if known_evidence_ids is not None and support.evidence_id not in known_evidence_ids:
                raise ModelValidationError(
                    f"CausalHypothesis references unknown evidence id '{support.evidence_id}'"
                )
        # Truthful uncertainty (C4): evidence whose observed result is not SUCCESS
        # cannot be silently converted into positive (SUCCESS) causal support.
        if known_evidence_results is not None and self.uncertainty.state == TruthState.SUCCESS:
            for support in self.supporting_evidence:
                obs_state = known_evidence_results.get(support.evidence_id)
                if obs_state is not None and obs_state != TruthState.SUCCESS:
                    raise ModelValidationError(
                        f"evidence '{support.evidence_id}' has observed state {obs_state.value}; "
                        "non-SUCCESS evidence cannot support a SUCCESS (positive) causal claim"
                    )

    def with_status(
        self,
        new_status: str,
        *,
        known_evidence_ids: set[str] | None = None,
        known_evidence_results: dict[str, TruthState] | None = None,
    ) -> "CausalHypothesis":
        """Transition to a new lifecycle status with authority gating.

        - ``confirmed`` (a causal certainty state) requires at least one
          intervention-grade supporting evidence record (architecture §13.4).
        - ``supported`` is allowed for observation-backed claims but the
          uncertainty must remain non-SUCCESS unless intervention evidence exists.
        """
        if new_status == "confirmed":
            has_intervention = any(s.support_kind == SupportKind.INTERVENTION for s in self.supporting_evidence)
            if not has_intervention:
                raise ModelValidationError(
                    "status 'confirmed' requires intervention-grade supporting evidence "
                    "(observation-only support cannot establish causal certainty)"
                )
        self.validate(known_evidence_ids=known_evidence_ids, known_evidence_results=known_evidence_results)
        return CausalHypothesis(
            cause_subject=self.cause_subject, effect_subject=self.effect_subject,
            relation_type=self.relation_type, direction=self.direction,
            rationale=self.rationale, status=new_status,
            uncertainty=self.uncertainty, supporting_evidence=self.supporting_evidence,
            traceability=self.traceability, provenance_revision=self.provenance_revision,
            id=self.id,
        )


# ---------------------------------------------------------------------------
# Deterministic identity
# ---------------------------------------------------------------------------


def _hypothesis_id(h: CausalHypothesis) -> str:
    """Content-addressed identity spanning claim semantics + supporting evidence.

    Identical claims with identical provenance/supporting evidence ⇒ identical
    id (C1). Differing relation type, direction, cause/effect subjects, or
    supporting evidence ids ⇒ distinct ids.
    """
    support_material = "|".join(
        f"{s.evidence_id}:{s.support_kind.value}" for s in sorted(h.supporting_evidence, key=lambda s: s.evidence_id)
    )
    material = "|".join([
        h.cause_subject,
        h.effect_subject,
        h.relation_type.value,
        h.direction,
        h.rationale,
        h.provenance_revision,
        support_material,
    ])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"causal-{digest}"


# ---------------------------------------------------------------------------
# Causal knowledge graph (deterministic ordering + dedup)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CausalKnowledgeGraph:
    """A deterministically-ordered collection of causal hypotheses.

    Ingestion deduplicates by content-addressed id and keeps hypotheses sorted
    by id, so identical inputs always produce identical graph identity/order.
    Competing hypotheses coexist (contradiction handling, C4).
    """

    id: str
    version: int
    hypotheses: tuple[CausalHypothesis, ...]
    traceability: Traceability

    def validate(
        self,
        *,
        known_evidence_ids: set[str] | None = None,
        known_evidence_results: dict[str, TruthState] | None = None,
    ) -> None:
        if not self.id or not self.id.strip():
            raise ModelValidationError("CausalKnowledgeGraph.id is required")
        if self.version < 1:
            raise ModelValidationError("CausalKnowledgeGraph.version must be >= 1")
        self.traceability.validate(require_value=True, require_context=True)
        seen: set[str] = set()
        for h in self.hypotheses:
            h.validate(known_evidence_ids=known_evidence_ids, known_evidence_results=known_evidence_results)
            if h.id in seen:
                raise ModelValidationError(f"CausalKnowledgeGraph contains duplicate hypothesis id {h.id}")
            seen.add(h.id)
        ids = [h.id for h in self.hypotheses]
        if ids != sorted(ids):
            raise ModelValidationError("CausalKnowledgeGraph.hypotheses must be sorted by id")

    def ingest(self, hypothesis: CausalHypothesis) -> "CausalKnowledgeGraph":
        """Return a new graph with ``hypothesis`` added; dedup by id; keep sorted."""
        hypothesis.validate()
        if any(h.id == hypothesis.id for h in self.hypotheses):
            return self
        hyps = list(self.hypotheses) + [hypothesis]
        hyps.sort(key=lambda h: h.id)
        return CausalKnowledgeGraph(
            id=self.id, version=self.version,
            hypotheses=tuple(hyps), traceability=self.traceability,
        )

    def by_subject(self, subject: str) -> tuple[CausalHypothesis, ...]:
        return tuple(h for h in self.hypotheses if h.cause_subject == subject or h.effect_subject == subject)


# ---------------------------------------------------------------------------
# Architecture memory — versioned projection, never a replacement
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchitectureMemory:
    """A versioned projection of learned causal hypotheses about a recovered graph.

    ``graph_ref`` references the W2/W3 Architecture Graph by id; memory never
    mutates the canonical graph. Hypotheses are explicitly uncertain knowledge
    (priors), never silent replacements for recovered architecture facts.
    """

    id: str
    version: int
    graph_ref: str
    hypotheses: tuple[CausalHypothesis, ...]
    traceability: Traceability

    def __post_init__(self) -> None:
        self.validate()

    def validate(
        self,
        *,
        known_graph_id: str | None = None,
        known_evidence_ids: set[str] | None = None,
        known_evidence_results: dict[str, TruthState] | None = None,
    ) -> None:
        if not self.id or not self.id.strip():
            raise ModelValidationError("ArchitectureMemory.id is required")
        if self.version < 1:
            raise ModelValidationError("ArchitectureMemory.version must be >= 1")
        if not self.graph_ref or not self.graph_ref.strip():
            raise ModelValidationError("ArchitectureMemory.graph_ref is required")
        if known_graph_id is not None and self.graph_ref != known_graph_id:
            raise ModelValidationError(
                f"ArchitectureMemory.graph_ref '{self.graph_ref}' does not match known graph '{known_graph_id}'"
            )
        self.traceability.validate(require_value=True, require_context=True)
        for h in self.hypotheses:
            h.validate(known_evidence_ids=known_evidence_ids, known_evidence_results=known_evidence_results)
        ids = [h.id for h in self.hypotheses]
        if len(set(ids)) != len(ids):
            raise ModelValidationError("ArchitectureMemory.hypotheses must have unique ids")
