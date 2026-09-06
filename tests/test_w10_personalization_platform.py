"""W10 — contextual personalization + platform adapters invariant tests.

Failing-first per SOS-IMPLEMENTATION-PROCESS §5. Covers the W10 Work Order
acceptance criteria C1–C12 and the required regression coverage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sos import (
    AutonomyDecision,
    AutonomyDecisionState,
    AutonomyRequest,
    ContextDimension,
    ContextValue,
    DecisionAction,
    JsonModelStore,
    ModelValidationError,
    PolicyCeiling,
    Traceability,
    TruthState,
    TruthfulValue,
)
from sos.personalization import (
    ContextualPolicy,
    ContextualSelector,
    PersonalizationDecision,
    evaluate_personalization,
)
from sos.platform import (
    AdapterCapability,
    AdapterPlan,
    PlatformAdapter,
    PlatformSurface,
    validate_adapter,
)


REVISION = "deadbeefcafebabe1234567890abcdef12345678"


def tr() -> Traceability:
    return Traceability(
        constitution_ref="constitution:1", mission_ref="mission:1",
        value_model_ref="value:1", context_ref="context:1",
    )


def base_policy() -> AutonomyRequest:
    return AutonomyRequest(
        id="policy-1", version=1,
        allowed_actions=(DecisionAction.ACT, DecisionAction.EXPERIMENT, DecisionAction.GATHER_EVIDENCE),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False,
        ),
        traceability=tr(),
    )


# --- C1: explicit contextual model ---


def test_contextual_selector_has_typed_dimensions_and_truth_states():
    cs = ContextualSelector(
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ContextValue(dimension=ContextDimension.ENVIRONMENT, key="tier", value=TruthfulValue(TruthState.SUCCESS, "production", None)),
        ),
    )
    cs.validate()
    assert len(cs.dimensions) == 2


def test_unknown_context_value_remains_distinct():
    cs = ContextualSelector(
        dimensions=(
            ContextValue(dimension=ContextDimension.CUSTOM, key="feature", value=TruthfulValue(TruthState.UNKNOWN, None, "not determined")),
        ),
    )
    cs.validate()
    assert cs.dimensions[0].value.state == TruthState.UNKNOWN


# --- C2: bounded personalization ---


def test_contextual_policy_selects_based_on_context():
    cp = ContextualPolicy(
        id="ctx-policy-1", version=1,
        source_policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
        ),
        narrowed_allowed_actions=(DecisionAction.ACT,),  # subset of source
        narrowed_ceilings=PolicyCeiling(
            max_risk=0.2, max_blast_radius="limited", require_reversible=True,
            min_confidence=0.9, require_human_approval_for_act=True,  # stricter
        ),
        traceability=tr(),
    )
    cp.validate()
    assert DecisionAction.ACT in cp.narrowed_allowed_actions
    assert DecisionAction.EXPERIMENT not in cp.narrowed_allowed_actions  # narrowed


# --- C3: W9 authority inheritance ---


def test_contextual_policy_cannot_expand_allowed_actions():
    with pytest.raises(ModelValidationError, match="cannot expand"):
        ContextualPolicy(
            id="bad", version=1,
            source_policy=base_policy(),  # no ROLLBACK
            selector=ContextualSelector(dimensions=()),
            narrowed_allowed_actions=(DecisionAction.ACT, DecisionAction.ROLLBACK),  # ROLLBACK not in source
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )


def test_contextual_policy_cannot_relax_ceilings():
    with pytest.raises(ModelValidationError, match=r"cannot.*(relax|exceed|widen)"):
        ContextualPolicy(
            id="bad", version=1,
            source_policy=base_policy(),  # max_risk=0.3
            selector=ContextualSelector(dimensions=()),
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(
                max_risk=0.5,  # relaxed (0.5 > 0.3)
                max_blast_radius="system",  # relaxed (system > service)
                require_reversible=False,  # relaxed
                min_confidence=0.5,  # relaxed (0.5 < 0.8)
                require_human_approval_for_act=False,
            ),
            traceability=tr(),
        )


# --- C4: human authority / ASK ---


def test_missing_context_routes_to_ask():
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.USER, key="id", value=TruthfulValue(TruthState.UNKNOWN, None, "no user context")),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,  # W9 says ACT, but context is unknown -> ASK
    )
    assert decision.state == "ASK"


def test_unavailable_context_routes_to_ask():
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.ENVIRONMENT, key="tier", value=TruthfulValue(TruthState.UNAVAILABLE, None, "environment data offline")),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,  # W9 says ACT, but context unavailable -> ASK
    )
    assert decision.state == "ASK"


# --- C5: platform-neutral adapter interface ---


def test_platform_adapter_exposes_capabilities():
    adapter = PlatformAdapter(
        id="adapter-web-1", version=1,
        surface=PlatformSurface.WEB,
        capabilities=(
            AdapterCapability(name="http-api", supported=True),
            AdapterCapability(name="websocket", supported=True),
            AdapterCapability(name="native-push", supported=False),
        ),
        traceability=tr(),
    )
    adapter.validate()
    assert adapter.surface == PlatformSurface.WEB
    assert len(adapter.capabilities) == 3


def test_invalid_adapter_data_rejected():
    with pytest.raises(ModelValidationError):
        PlatformAdapter(
            id="", version=1,  # empty id
            surface=PlatformSurface.WEB,
            capabilities=(),
            traceability=tr(),
        )


# --- C6: no execution ---


def test_adapter_plan_is_side_effect_free():
    adapter = PlatformAdapter(
        id="adapter-web-1", version=1,
        surface=PlatformSurface.WEB,
        capabilities=(AdapterCapability(name="http-api", supported=True),),
        traceability=tr(),
    )
    plan = validate_adapter(adapter, required_capabilities=("http-api",))
    assert isinstance(plan, AdapterPlan)
    assert plan.compatible is True
    assert not hasattr(plan, "executed")
    assert not hasattr(plan, "deployed")


def test_incompatible_adapter_rejected():
    adapter = PlatformAdapter(
        id="adapter-web-1", version=1,
        surface=PlatformSurface.WEB,
        capabilities=(AdapterCapability(name="http-api", supported=True),),
        traceability=tr(),
    )
    plan = validate_adapter(adapter, required_capabilities=("native-push",))  # not supported
    assert plan.compatible is False


# --- C7: constraint preservation ---


def test_platform_constraints_narrow_not_widen():
    cp = ContextualPolicy(
        id="ctx-1", version=1,
        source_policy=base_policy(),  # max_risk=0.3, max_blast=service
        selector=ContextualSelector(dimensions=()),
        narrowed_allowed_actions=(DecisionAction.ACT,),
        narrowed_ceilings=PolicyCeiling(
            max_risk=0.1,  # narrower
            max_blast_radius="limited",  # narrower
            require_reversible=True,
            min_confidence=0.95,  # stricter
            require_human_approval_for_act=True,  # stricter
        ),
        traceability=tr(),
    )
    cp.validate()  # should pass — all narrower


# --- C8: explainability and evidence ---


def test_personalization_decision_records_context_and_policy_refs():
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
    )
    assert decision.policy_id == "policy-1"
    assert len(decision.context_refs) > 0
    assert decision.traceability.context_ref == "context:1"


# --- C9: deterministic evaluation ---


def test_personalization_is_deterministic():
    selector = ContextualSelector(
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
        ),
    )
    d1 = evaluate_personalization(policy=base_policy(), selector=selector, traceability=tr(), w9_decision_state=AutonomyDecisionState.ACT)
    d2 = evaluate_personalization(policy=base_policy(), selector=selector, traceability=tr(), w9_decision_state=AutonomyDecisionState.ACT)
    assert d1.state == d2.state
    assert d1.id == d2.id


# --- C10: persistence ---


def test_decision_round_trips_through_json(tmp_path):
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
    )
    p = tmp_path / "personalization.json"
    JsonModelStore(p).save(decision)
    data = JsonModelStore(p).load()
    assert data["state"] == decision.state
    assert data["policy_id"] == "policy-1"
    assert data["traceability"]["context_ref"] == "context:1"


# --- C11: bounded authority surface ---


def test_w10_introduces_no_w11_plus_symbols():
    import sos.personalization as pmod
    import sos.platform as pmod2
    forbidden = {
        "Greenfield", "Brownfield", "SelfEvolution", "MetaAdaptation",
        "Deployer", "Deploy", "ExperimentRunner", "ProductionRunner",
    }
    for mod in (pmod, pmod2):
        exported = {n for n in dir(mod) if not n.startswith("_")}
        assert not (forbidden & exported), f"forbidden W11+ symbols in {mod.__name__}: {forbidden & exported}"


def test_w10_does_not_redefine_autonomy_authority():
    import sos.personalization as pmod
    import sos.platform as pmod2
    forbidden = {"AutonomyRequest", "AutonomyDecision", "evaluate_autonomy", "PolicyCeiling"}
    for mod in (pmod, pmod2):
        exported = {n for n in dir(mod) if not n.startswith("_")}
        assert not (forbidden & exported), f"W10 must not re-export W9 authority: {forbidden & exported}"


# --- C12: extension contract ---


def test_new_adapter_can_implement_contract():
    custom_adapter = PlatformAdapter(
        id="adapter-custom-1", version=1,
        surface=PlatformSurface.OTHER,
        capabilities=(AdapterCapability(name="custom-api", supported=True),),
        traceability=tr(),
    )
    custom_adapter.validate()
    plan = validate_adapter(custom_adapter, required_capabilities=("custom-api",))
    assert plan.compatible is True


# --- PlatformSurface vocabulary ---


def test_platform_surface_covers_frozen_vocabulary():
    surfaces = {s.value for s in PlatformSurface}
    assert "web" in surfaces
    assert "mobile" in surfaces
    assert "desktop" in surfaces
    assert "tv" in surfaces
    assert "cross-platform" in surfaces
    assert "other" in surfaces

# --- SOS-W10-F01 regression: W9 decision state inheritance ---


def test_w9_ask_cannot_become_act():
    """SOS-W10-F01: a W9 ASK decision cannot become ACT even with resolved context."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ASK,
    )
    assert decision.state == "ASK"


def test_w9_reject_cannot_become_act():
    """SOS-W10-F01: a W9 REJECT decision cannot become ACT even with resolved context."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.REJECT,
    )
    assert decision.state == "REJECT"


def test_w9_act_with_resolved_context_preserves_act():
    """SOS-W10-F01: a W9 ACT decision with resolved context preserves ACT."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
    )
    assert decision.state == "ACT"


def test_w9_act_with_unknown_context_narrows_to_ask():
    """SOS-W10-F01: a W9 ACT decision with unknown context narrows to ASK."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            dimensions=(
                ContextValue(dimension=ContextDimension.USER, key="id", value=TruthfulValue(TruthState.UNKNOWN, None, "no user")),
            ),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
    )
    assert decision.state == "ASK"
