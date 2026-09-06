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
    PolicyAlternative,
    PolicySelection,
    evaluate_personalization,
    select_policy,
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
        id="ctx-test", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ContextValue(dimension=ContextDimension.ENVIRONMENT, key="tier", value=TruthfulValue(TruthState.SUCCESS, "production", None)),
        ),
        traceability=tr(),
    )
    cs.validate()
    assert len(cs.dimensions) == 2


def test_unknown_context_value_remains_distinct():
    cs = ContextualSelector(
        id="ctx-1", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.CUSTOM, key="feature", value=TruthfulValue(TruthState.UNKNOWN, None, "not determined")),
        ),
        traceability=tr(),
    )
    cs.validate()
    assert cs.dimensions[0].value.state == TruthState.UNKNOWN


# --- C2: bounded personalization ---


def test_contextual_policy_selects_based_on_context():
    cp = ContextualPolicy(
        id="ctx-policy-1", version=1,
        source_policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-1", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
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
            selector=ContextualSelector(id="ctx-empty", version=1, dimensions=(), traceability=tr()),
            narrowed_allowed_actions=(DecisionAction.ACT, DecisionAction.ROLLBACK),  # ROLLBACK not in source
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )


def test_contextual_policy_cannot_relax_ceilings():
    with pytest.raises(ModelValidationError, match=r"cannot.*(relax|exceed|widen)"):
        ContextualPolicy(
            id="bad", version=1,
            source_policy=base_policy(),  # max_risk=0.3
            selector=ContextualSelector(id="ctx-empty", version=1, dimensions=(), traceability=tr()),
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
            id="ctx-auto", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.USER, key="id", value=TruthfulValue(TruthState.UNKNOWN, None, "no user context")),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-1",
    )
    assert decision.state == "ASK"


def test_unavailable_context_routes_to_ask():
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-auto", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.ENVIRONMENT, key="tier", value=TruthfulValue(TruthState.UNAVAILABLE, None, "environment data offline")),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-1",
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
        selector=ContextualSelector(id="ctx-empty", version=1, dimensions=(), traceability=tr()),
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
            id="ctx-1", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-1",
        evidence_ids=("ev-1",),
        alternatives=("alt-1",),
        constraints=("preserve-safety",),
    )
    assert decision.policy_id == "policy-1"
    assert len(decision.context_refs) > 0
    assert decision.traceability.context_ref == "context:1"
    assert decision.w9_decision_id == "w9-dec-1"
    assert "ev-1" in decision.evidence_ids
    assert "alt-1" in decision.alternatives
    assert "preserve-safety" in decision.constraints


# --- C9: deterministic evaluation ---


def test_personalization_is_deterministic():
    selector = ContextualSelector(
        id="ctx-det", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
        ),
        traceability=tr(),
    )
    d1 = evaluate_personalization(policy=base_policy(), selector=selector, traceability=tr(), w9_decision_state=AutonomyDecisionState.ACT, w9_decision_id="w9-1")
    d2 = evaluate_personalization(policy=base_policy(), selector=selector, traceability=tr(), w9_decision_state=AutonomyDecisionState.ACT, w9_decision_id="w9-1")
    assert d1.state == d2.state
    assert d1.id == d2.id


# --- C10: persistence ---


def test_decision_round_trips_through_json(tmp_path):
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-1", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-1",
        evidence_ids=("ev-1",),
        alternatives=("alt-1",),
        constraints=("preserve-safety",),
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
            id="ctx-1", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ASK,
        w9_decision_id="w9-dec-1",
    )
    assert decision.state == "ASK"


def test_w9_reject_cannot_become_act():
    """SOS-W10-F01: a W9 REJECT decision cannot become ACT even with resolved context."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-1", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.REJECT,
        w9_decision_id="w9-dec-1",
    )
    assert decision.state == "REJECT"


def test_w9_act_with_resolved_context_preserves_act():
    """SOS-W10-F01: a W9 ACT decision with resolved context preserves ACT."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-1", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-1",
        evidence_ids=("ev-1",),
        alternatives=("alt-1",),
        constraints=("preserve-safety",),
    )
    assert decision.state == "ACT"


def test_w9_act_with_unknown_context_narrows_to_ask():
    """SOS-W10-F01: a W9 ACT decision with unknown context narrows to ASK."""
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-narrow", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.USER, key="id", value=TruthfulValue(TruthState.UNKNOWN, None, "no user")),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-1",
        evidence_ids=("ev-1",),
        alternatives=("alt-1",),
        constraints=("preserve-safety",),
    )
    assert decision.state == "ASK"

# --- SOS-W10-F02 regression: full explainability/evidence traceability ---


def test_decision_preserves_w9_decision_id_and_evidence_refs():
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=ContextualSelector(
            id="ctx-f02", version=1,
            dimensions=(
                ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
            ),
            traceability=tr(),
        ),
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-dec-f02",
        evidence_ids=("ev-f02-1", "ev-f02-2"),
        alternatives=("alt-a", "alt-b"),
        constraints=("hard:safety", "soft:cost"),
    )
    assert decision.w9_decision_id == "w9-dec-f02"
    assert "ev-f02-1" in decision.evidence_ids
    assert "ev-f02-2" in decision.evidence_ids
    assert "alt-a" in decision.alternatives
    assert "hard:safety" in decision.constraints
    assert decision.uncertainty.state != TruthState.SUCCESS  # uncertainty is never SUCCESS


# --- SOS-W10-F03 regression: versioned/traceable context selector ---


def test_contextual_selector_is_versioned_and_traceable():
    cs = ContextualSelector(
        id="ctx-ver-1", version=3,
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
        ),
        traceability=tr(),
    )
    cs.validate()
    assert cs.version == 3
    assert cs.id == "ctx-ver-1"
    assert cs.traceability.context_ref == "context:1"


def test_contextual_selector_requires_version():
    with pytest.raises(ModelValidationError):
        ContextualSelector(
            id="ctx-bad", version=0,
            dimensions=(),
            traceability=tr(),
        )


# --- SOS-W10-F04 regression: alternative selection ---


def test_select_policy_chooses_among_alternatives():
    """SOS-W10-F04: select_policy evaluates each alternative's own selector
    against context. Both alternatives have resolved context; the lower-priority
    one wins."""
    selector = ContextualSelector(
        id="ctx-sel", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
        ),
        traceability=tr(),
    )
    # Both alternatives have resolved (SUCCESS) selectors
    alt1_sel = ContextualSelector(
        id="alt1-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),),
        traceability=tr(),
    )
    alt2_sel = ContextualSelector(
        id="alt2-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "mobile", None)),),
        traceability=tr(),
    )
    alt1 = PolicyAlternative(id="alt-1", policy=base_policy(), selector=alt1_sel, priority=2)
    alt2 = PolicyAlternative(id="alt-2", policy=base_policy(), selector=alt2_sel, priority=1)  # higher priority
    result = select_policy(
        alternatives=(alt1, alt2),
        selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.selected_id == "alt-2"  # both compatible; priority 1 wins
    assert result.state == "ACT"
    assert result.alternatives_evaluated == 2


def test_select_policy_with_unresolved_context_narrows_to_ask():
    selector = ContextualSelector(
        id="ctx-sel-2", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.USER, key="id", value=TruthfulValue(TruthState.UNKNOWN, None, "no user")),
        ),
        traceability=tr(),
    )
    alt1 = PolicyAlternative(id="alt-1", policy=base_policy(), selector=selector, priority=1)
    result = select_policy(
        alternatives=(alt1,),
        selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.state == "ASK"
    assert result.selected_id == "alt-1"


def test_select_policy_w9_ask_preserved():
    selector = ContextualSelector(
        id="ctx-sel-3", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
        ),
        traceability=tr(),
    )
    alt1 = PolicyAlternative(id="alt-1", policy=base_policy(), selector=selector, priority=1)
    result = select_policy(
        alternatives=(alt1,),
        selector=selector,
        w9_decision_state=AutonomyDecisionState.ASK,
        traceability=tr(),
    )
    assert result.state == "ASK"

def test_context_changes_which_alternative_wins():
    """SOS-W10-F04: context conditions determine which alternative is selected.
    When alt-1's selector is SUCCESS but alt-2's is UNKNOWN, alt-1 wins
    regardless of priority."""
    selector = ContextualSelector(
        id="ctx-top", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),),
        traceability=tr(),
    )
    # alt-1 has a RESOLVED selector (SUCCESS)
    alt1_sel = ContextualSelector(
        id="alt1-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),),
        traceability=tr(),
    )
    # alt-2 has an UNRESOLVED selector (UNKNOWN) — even though priority is lower
    alt2_sel = ContextualSelector(
        id="alt2-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.UNKNOWN, None, "not determined")),),
        traceability=tr(),
    )
    alt1 = PolicyAlternative(id="alt-1", policy=base_policy(), selector=alt1_sel, priority=2)  # lower priority
    alt2 = PolicyAlternative(id="alt-2", policy=base_policy(), selector=alt2_sel, priority=1)  # higher priority but context-incompatible
    result = select_policy(
        alternatives=(alt1, alt2),
        selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    # alt-1 wins because it's context-compatible, even though priority is lower
    assert result.selected_id == "alt-1"
    assert result.state == "ACT"


def test_no_compatible_alternative_routes_to_ask():
    """SOS-W10-F04: when no alternative's selector is context-compatible,
    select the highest-priority and narrow to ASK."""
    selector = ContextualSelector(
        id="ctx-top", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),),
        traceability=tr(),
    )
    # Both alternatives have UNKNOWN selectors
    alt1_sel = ContextualSelector(
        id="alt1-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.USER, key="id", value=TruthfulValue(TruthState.UNKNOWN, None, "no user")),),
        traceability=tr(),
    )
    alt2_sel = ContextualSelector(
        id="alt2-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.ENVIRONMENT, key="tier", value=TruthfulValue(TruthState.UNAVAILABLE, None, "offline")),),
        traceability=tr(),
    )
    alt1 = PolicyAlternative(id="alt-1", policy=base_policy(), selector=alt1_sel, priority=2)
    alt2 = PolicyAlternative(id="alt-2", policy=base_policy(), selector=alt2_sel, priority=1)
    result = select_policy(
        alternatives=(alt1, alt2),
        selector=selector,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    # No compatible alternative -> ASK
    assert result.state == "ASK"
    assert result.selected_id == "alt-2"  # highest priority among incompatible
