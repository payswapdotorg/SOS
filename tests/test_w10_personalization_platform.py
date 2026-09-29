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
    AlternativeDimensionEvaluation,
    AlternativeEvaluation,
    ContextualPolicy,
    ContextualSelector,
    PersonalizationDecision,
    PolicyAlternative,
    PolicySelection,
    StateNarrowingStep,
    evaluate_personalization,
    narrow_decision_state,
    select_policy,
)
from sos.platform import (
    AdapterCapability,
    AdapterPlan,
    PlatformAdapter,
    PlatformPolicyConstraint,
    PlatformSurface,
    constrain_policy,
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
    """SOS-W10-F04/A1: select_policy evaluates each alternative's declared
    dimensions against the SUPPLIED context. Both alternatives declare a
    surface constraint that matches the supplied 'web' context, so both are
    context-compatible and the lower-priority-number one wins."""
    selector = ContextualSelector(
        id="ctx-sel", version=1,
        dimensions=(
            ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),
        ),
        traceability=tr(),
    )
    # Both alternatives declare constraints that match the supplied context
    alt1_sel = ContextualSelector(
        id="alt1-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),),
        traceability=tr(),
    )
    alt2_sel = ContextualSelector(
        id="alt2-sel", version=1,
        dimensions=(ContextValue(dimension=ContextDimension.PLATFORM, key="surface", value=TruthfulValue(TruthState.SUCCESS, "web", None)),),
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


# =============================================================================
# SOS-W10 Architect review iteration 4 — findings A1–A5 regression coverage
# =============================================================================


def cv(dim: ContextDimension, key: str, state: TruthState, value=None, detail=None) -> ContextValue:
    return ContextValue(dimension=dim, key=key, value=TruthfulValue(state, value, detail))


def sel(sid: str, *dims: ContextValue, version: int = 1) -> ContextualSelector:
    return ContextualSelector(id=sid, version=version, dimensions=dims, traceability=tr())


def alt(aid: str, *declared: ContextValue, priority: int = 1) -> PolicyAlternative:
    return PolicyAlternative(
        id=aid, policy=base_policy(),
        selector=sel(f"{aid}-sel", *declared), priority=priority,
    )


def approval_policy() -> AutonomyRequest:
    """Source policy that requires human approval for ACT (for A5 waiver tests)."""
    return AutonomyRequest(
        id="policy-approval", version=1,
        allowed_actions=(DecisionAction.ACT, DecisionAction.EXPERIMENT, DecisionAction.GATHER_EVIDENCE),
        ceilings=PolicyCeiling(
            max_risk=0.3, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=True,
        ),
        traceability=tr(),
    )


def web_adapter() -> PlatformAdapter:
    return PlatformAdapter(
        id="adapter-web-1", version=1,
        surface=PlatformSurface.WEB,
        capabilities=(
            AdapterCapability(name="http-api", supported=True),
            AdapterCapability(name="websocket", supported=False),
        ),
        traceability=tr(),
    )


# --- A1: alternative selection is a true predicate over the supplied context ---


def test_a1_supplied_context_value_mismatch_excludes_alternative():
    """A1: an alternative whose declared dimension value-mismatches the SUPPLIED
    context is NOT context-compatible, even at higher priority."""
    supplied = sel("ctx-sup", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    mismatched = alt("alt-mismatch", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=1)
    matching = alt("alt-match", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"), priority=2)
    result = select_policy(
        alternatives=(mismatched, matching),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.selected_id == "alt-match"  # mismatched alternative excluded despite priority 1
    assert result.state == "ACT"
    evaluations = {e.alternative_id: e for e in result.alternative_evaluations}
    assert evaluations["alt-mismatch"].compatible is False
    assert evaluations["alt-mismatch"].dimension_evaluations[0].outcome == "mismatched"
    assert evaluations["alt-match"].compatible is True
    assert evaluations["alt-match"].dimension_evaluations[0].outcome == "matched"


def test_a1_success_on_own_declaration_alone_never_implies_compatibility():
    """A1: a SUCCESS flag on the alternative's OWN declaration must never imply
    compatibility when the supplied context does not match the constraint."""
    supplied = sel("ctx-sup", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    declares_mobile = alt("alt-mobile", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=1)
    result = select_policy(
        alternatives=(declares_mobile,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.alternative_evaluations[0].compatible is False
    assert result.state == "ASK"  # no compatible alternative -> ACT narrows to ASK


def test_a1_dimension_absent_in_supplied_context_not_compatible():
    """A1: a declared dimension absent from the supplied selector is unresolved
    (ABSENT) — the alternative is not compatible and the decision routes per C4."""
    supplied = sel("ctx-sup", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    declares_tier = alt("alt-tier", cv(ContextDimension.ENVIRONMENT, "tier", TruthState.SUCCESS, "production"), priority=1)
    result = select_policy(
        alternatives=(declares_tier,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    evaluation = result.alternative_evaluations[0]
    assert evaluation.compatible is False
    assert evaluation.dimension_evaluations[0].outcome == "unresolved"
    assert evaluation.dimension_evaluations[0].supplied_state == "ABSENT"
    assert result.state == "ASK"  # routes per C4: no context-compatible alternative


def test_a1_dimension_unresolved_in_supplied_context_not_compatible():
    """A1: a declared dimension that is present but unresolved (non-SUCCESS) in
    the supplied selector makes the alternative not context-compatible."""
    supplied = sel(
        "ctx-sup",
        cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"),
        cv(ContextDimension.ENVIRONMENT, "tier", TruthState.UNKNOWN, None, "tier not determined"),
    )
    declares_tier = alt("alt-tier", cv(ContextDimension.ENVIRONMENT, "tier", TruthState.SUCCESS, "production"), priority=1)
    result = select_policy(
        alternatives=(declares_tier,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    evaluation = result.alternative_evaluations[0]
    assert evaluation.compatible is False
    dim = evaluation.dimension_evaluations[0]
    assert dim.outcome == "unresolved"
    assert dim.supplied_state == "UNKNOWN"
    assert result.state == "ASK"  # routes per C4


def test_a1_matching_predicate_selects_and_preserves_inherited_state():
    """A1 positive case: a fully matched alternative is compatible and the
    inherited W9 state is preserved (narrowing only, never widening)."""
    supplied = sel(
        "ctx-sup",
        cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"),
        cv(ContextDimension.COHORT, "segment", TruthState.SUCCESS, "beta"),
    )
    declares_both = alt(
        "alt-both",
        cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"),
        cv(ContextDimension.COHORT, "segment", TruthState.SUCCESS, "beta"),
        priority=1,
    )
    result = select_policy(
        alternatives=(declares_both,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.REJECT,
        traceability=tr(),
    )
    assert result.alternative_evaluations[0].compatible is True
    assert all(
        e.outcome == "matched" for e in result.alternative_evaluations[0].dimension_evaluations
    )
    assert result.state == "REJECT"  # compatible selection still cannot widen inherited REJECT


# --- A2: every non-SUCCESS supplied truth state narrows (FAILED included) ---


def test_a2_failed_supplied_context_never_silently_preserves_act():
    """A2: a FAILED supplied context must narrow the decision — never silently
    preserve ACT (the old guard only checked UNKNOWN/UNAVAILABLE/UNSUPPORTED)."""
    supplied = sel("ctx-failed", cv(ContextDimension.USER, "id", TruthState.FAILED, None, "user lookup failed"))
    declares_user = alt("alt-user", cv(ContextDimension.USER, "id", TruthState.SUCCESS, "user-1"), priority=1)
    result = select_policy(
        alternatives=(declares_user,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.state != "ACT"
    assert result.state == "ASK"
    # evaluate_personalization applies the same distinctness
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=supplied,
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-failed",
    )
    assert decision.state == "ASK"


_NON_SUCCESS_STATES = [
    TruthState.FAILED,
    TruthState.EMPTY,
    TruthState.UNKNOWN,
    TruthState.UNSUPPORTED,
    TruthState.UNAVAILABLE,
]


@pytest.mark.parametrize("state", _NON_SUCCESS_STATES, ids=lambda s: s.value)
def test_a2_every_non_success_supplied_state_narrows_act(state):
    """A2: EVERY truth state the W1 model defines other than SUCCESS narrows
    the decision — no non-SUCCESS state is collapsed into success."""
    detail = None if state == TruthState.EMPTY else f"{state.value.lower()} context"
    supplied = sel(f"ctx-{state.value}", cv(ContextDimension.USER, "id", state, None, detail))
    declares_user = alt("alt-user", cv(ContextDimension.USER, "id", TruthState.SUCCESS, "user-1"), priority=1)
    result = select_policy(
        alternatives=(declares_user,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.state == "ASK"
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=supplied,
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.ACT,
        w9_decision_id="w9-a2",
    )
    assert decision.state == "ASK"


# --- A3: monotonic narrowing in the W9 decision-state lattice ---


def test_a3_inherited_reject_survives_no_compatible_path():
    """A3: the no-compatible-alternative path may not upgrade inherited REJECT
    to ASK — narrowing is monotonic, never widening."""
    supplied = sel("ctx-sup", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    declares_mobile = alt("alt-mobile", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=1)
    result = select_policy(
        alternatives=(declares_mobile,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.REJECT,
        traceability=tr(),
    )
    assert result.state == "REJECT"
    assert result.inherited_state == "REJECT"
    assert result.narrowing_chain == ()  # REJECT is never widened


def test_a3_inherited_rollback_survives_no_compatible_path():
    """A3: inherited ROLLBACK stays ROLLBACK on the no-compatible path."""
    supplied = sel("ctx-sup", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    declares_mobile = alt("alt-mobile", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=1)
    result = select_policy(
        alternatives=(declares_mobile,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ROLLBACK,
        traceability=tr(),
    )
    assert result.state == "ROLLBACK"
    assert result.narrowing_chain == ()


def test_a3_act_narrows_to_ask_on_no_compatible_path():
    """A3: ACT may narrow to ASK when no alternative is context-compatible."""
    supplied = sel("ctx-sup", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    declares_mobile = alt("alt-mobile", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=1)
    result = select_policy(
        alternatives=(declares_mobile,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.state == "ASK"
    assert result.narrowing_chain[0].from_state == "ACT"
    assert result.narrowing_chain[0].to_state == "ASK"


def test_a3_inherited_reject_survives_unresolved_supplied_context():
    """A3: the unresolved-context guard must not overwrite an inherited REJECT
    with ASK (the old code did); REJECT is more restrictive and survives."""
    supplied = sel("ctx-unresolved", cv(ContextDimension.USER, "id", TruthState.UNKNOWN, None, "no user"))
    result = select_policy(
        alternatives=(alt("alt-user", cv(ContextDimension.USER, "id", TruthState.SUCCESS, "user-1")),),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.REJECT,
        traceability=tr(),
    )
    assert result.state == "REJECT"
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=supplied,
        traceability=tr(),
        w9_decision_state=AutonomyDecisionState.REJECT,
        w9_decision_id="w9-reject",
    )
    assert decision.state == "REJECT"


_MONOTONIC_CASES = [
    (AutonomyDecisionState.ACT, "ASK"),
    (AutonomyDecisionState.EXPERIMENT, "ASK"),
    (AutonomyDecisionState.GATHER_EVIDENCE, "ASK"),
    (AutonomyDecisionState.ASK, "ASK"),
    (AutonomyDecisionState.REJECT, "REJECT"),
    (AutonomyDecisionState.ROLLBACK, "ROLLBACK"),
]


@pytest.mark.parametrize("inherited,expected", _MONOTONIC_CASES, ids=lambda v: v.value if isinstance(v, AutonomyDecisionState) else v)
def test_a3_monotonic_narrowing_across_all_state_adjusting_paths(inherited, expected):
    """A3: every state-adjusting path (no-compatible + unresolved-context
    guards, in both select_policy and evaluate_personalization) narrows
    monotonically — never to a less restrictive state than inherited."""
    supplied = sel("ctx-unresolved", cv(ContextDimension.USER, "id", TruthState.UNKNOWN, None, "no user"))
    incompatible = alt("alt-absent", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    result = select_policy(
        alternatives=(incompatible,),
        selector=supplied,
        w9_decision_state=inherited,
        traceability=tr(),
    )
    assert result.state == expected
    assert result.inherited_state == inherited.value
    decision = evaluate_personalization(
        policy=base_policy(),
        selector=supplied,
        traceability=tr(),
        w9_decision_state=inherited,
        w9_decision_id="w9-a3",
    )
    assert decision.state == expected


def test_a3_narrow_decision_state_primitive_never_widens():
    """A3: the narrowing primitive itself refuses widening and non-state input."""
    assert narrow_decision_state(AutonomyDecisionState.ACT, AutonomyDecisionState.ASK) is AutonomyDecisionState.ASK
    assert narrow_decision_state(AutonomyDecisionState.REJECT, AutonomyDecisionState.ASK) is AutonomyDecisionState.REJECT
    assert narrow_decision_state(AutonomyDecisionState.ROLLBACK, AutonomyDecisionState.ASK) is AutonomyDecisionState.ROLLBACK
    assert narrow_decision_state(AutonomyDecisionState.ASK, AutonomyDecisionState.ACT) is AutonomyDecisionState.ASK  # widening refused
    assert narrow_decision_state(AutonomyDecisionState.REJECT, AutonomyDecisionState.ACT) is AutonomyDecisionState.REJECT
    assert narrow_decision_state(AutonomyDecisionState.ASK, AutonomyDecisionState.ASK) is AutonomyDecisionState.ASK
    with pytest.raises(ModelValidationError):
        narrow_decision_state("ASK", AutonomyDecisionState.ASK)  # type: ignore[arg-type]
    with pytest.raises(ModelValidationError):
        narrow_decision_state(AutonomyDecisionState.ASK, "ACT")  # type: ignore[arg-type]


# --- A4: per-alternative evaluation record + narrowing chain + round-trip ---


def test_a4_selection_records_per_alternative_evaluation_evidence():
    """A4: the selection records, per alternative: id, context-compatibility,
    and per-declared-dimension supplied-context outcomes (matched / mismatched /
    unresolved-with-truth-state), plus the inherited W9 state."""
    supplied = sel(
        "ctx-sup",
        cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"),
        cv(ContextDimension.USER, "id", TruthState.UNKNOWN, None, "no user"),
    )
    matched = alt("alt-matched", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"), priority=1)
    mismatched = alt("alt-mismatched", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=2)
    absent = alt("alt-absent", cv(ContextDimension.ENVIRONMENT, "tier", TruthState.SUCCESS, "production"), priority=3)
    result = select_policy(
        alternatives=(matched, mismatched, absent),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.inherited_state == "ACT"
    evaluations = {e.alternative_id: e for e in result.alternative_evaluations}
    assert set(evaluations) == {"alt-matched", "alt-mismatched", "alt-absent"}
    assert evaluations["alt-matched"].compatible is True
    assert evaluations["alt-matched"].dimension_evaluations[0].outcome == "matched"
    assert evaluations["alt-mismatched"].compatible is False
    assert evaluations["alt-mismatched"].dimension_evaluations[0].outcome == "mismatched"
    assert evaluations["alt-absent"].compatible is False
    absent_dim = evaluations["alt-absent"].dimension_evaluations[0]
    assert absent_dim.outcome == "unresolved"
    assert absent_dim.supplied_state == "ABSENT"
    unresolved_user = evaluations["alt-matched"].dimension_evaluations[-1] if len(evaluations["alt-matched"].dimension_evaluations) > 1 else None
    # alt-matched declares only PLATFORM:surface; the unresolved USER dimension
    # is captured on the supplied-context guard path (rationale + narrowing chain)
    assert result.state == "ASK"
    assert unresolved_user is None
    chain_reasons = " ".join(step.reason for step in result.narrowing_chain)
    assert "USER:id is UNKNOWN" in chain_reasons


def test_a4_selection_records_narrowing_chain_from_inherited_to_final():
    """A4: the narrowing chain records inherited -> final with reasons."""
    supplied = sel("ctx-unresolved", cv(ContextDimension.USER, "id", TruthState.UNKNOWN, None, "no user"))
    incompatible = alt("alt-absent", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"))
    result = select_policy(
        alternatives=(incompatible,),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    assert result.inherited_state == "ACT"
    assert result.state == "ASK"
    assert len(result.narrowing_chain) == 1  # ACT -> ASK once; second guard is a no-op
    step = result.narrowing_chain[0]
    assert step.from_state == "ACT"
    assert step.to_state == "ASK"
    assert "no context-compatible alternative" in step.reason


def test_a4_selection_json_round_trip_preserved(tmp_path):
    """A4/C10: the selection record (including the new evaluation evidence and
    narrowing chain) round-trips through the W1 JsonModelStore deterministically."""
    supplied = sel(
        "ctx-sup",
        cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"),
        cv(ContextDimension.USER, "id", TruthState.FAILED, None, "user lookup failed"),
    )
    matched = alt("alt-matched", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"), priority=1)
    mismatched = alt("alt-mismatched", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=2)
    result = select_policy(
        alternatives=(matched, mismatched),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    )
    p1 = tmp_path / "selection-1.json"
    p2 = tmp_path / "selection-2.json"
    JsonModelStore(p1).save(result)
    JsonModelStore(p2).save(select_policy(
        alternatives=(matched, mismatched),
        selector=supplied,
        w9_decision_state=AutonomyDecisionState.ACT,
        traceability=tr(),
    ))
    assert p1.read_text(encoding="utf-8") == p2.read_text(encoding="utf-8")  # deterministic serialization
    data = JsonModelStore(p1).load()
    assert data["selected_id"] == result.selected_id
    assert data["state"] == result.state
    assert data["inherited_state"] == "ACT"
    evaluations = {e["alternative_id"]: e for e in data["alternative_evaluations"]}
    assert evaluations["alt-matched"]["compatible"] is True
    assert evaluations["alt-mismatched"]["compatible"] is False
    assert evaluations["alt-mismatched"]["dimension_evaluations"][0]["outcome"] == "mismatched"
    assert evaluations["alt-mismatched"]["dimension_evaluations"][0]["supplied_value"] == "web"
    assert evaluations["alt-mismatched"]["dimension_evaluations"][0]["declared_value"] == "mobile"
    assert data["narrowing_chain"][0]["from_state"] == "ACT"
    assert data["narrowing_chain"][0]["to_state"] == "ASK"
    assert "supplied context unresolved" in data["narrowing_chain"][0]["reason"]


def test_a4_policy_selection_additive_fields_have_safe_defaults(tmp_path):
    """A4: new PolicySelection fields are strictly additive with safe defaults
    so previously persisted records (and old call sites) still load/work."""
    legacy = PolicySelection(
        selected_id="alt-1", state="ASK", selector_id="ctx-legacy",
        selector_version=1, alternatives_evaluated=1,
        rationale="legacy record without iteration-4 fields",
        traceability=tr(),
    )
    assert legacy.alternative_evaluations == ()
    assert legacy.inherited_state == ""
    assert legacy.narrowing_chain == ()
    # a persisted pre-iteration-4 record (no new keys) still loads via the W1 store
    legacy_payload = {
        "selected_id": "alt-1", "state": "ASK", "selector_id": "ctx-legacy",
        "selector_version": 1, "alternatives_evaluated": 1,
        "rationale": "legacy persisted record",
        "traceability": {"constitution_ref": "constitution:1", "mission_ref": "mission:1",
                         "value_model_ref": "value:1", "context_ref": "context:1"},
    }
    p = tmp_path / "legacy.json"
    JsonModelStore(p).save(legacy_payload)
    loaded = JsonModelStore(p).load()
    assert loaded["selected_id"] == "alt-1"
    assert "alternative_evaluations" not in loaded  # old record loads unchanged


def test_a4_policy_selection_rejects_invalid_record_data():
    """A4/C12: malformed evaluation-record data is rejected deterministically."""
    with pytest.raises(ModelValidationError, match="inherited_state"):
        PolicySelection(
            selected_id="alt-1", state="ASK", selector_id="ctx", selector_version=1,
            alternatives_evaluated=1, rationale="bad inherited state",
            traceability=tr(), inherited_state="NOT_A_STATE",
        )
    with pytest.raises(ModelValidationError, match="outcome"):
        AlternativeDimensionEvaluation(
            dimension="PLATFORM", key="surface", outcome="bogus",
            declared_state="SUCCESS", supplied_state="SUCCESS",
        )
    with pytest.raises(ModelValidationError, match="supplied_state"):
        AlternativeDimensionEvaluation(
            dimension="PLATFORM", key="surface", outcome="unresolved",
            declared_state="SUCCESS", supplied_state="NOPE",
        )
    with pytest.raises(ModelValidationError, match="from_state"):
        StateNarrowingStep(from_state="NOT_A_STATE", to_state="ASK", reason="bad step")
    with pytest.raises(ModelValidationError, match="alternative_id"):
        AlternativeEvaluation(alternative_id="   ", compatible=True)


def test_a4_selection_is_deterministic():
    """A4/C9: identical authoritative inputs produce identical selections."""
    supplied = sel(
        "ctx-sup",
        cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"),
        cv(ContextDimension.USER, "id", TruthState.FAILED, None, "user lookup failed"),
    )
    alternatives = (
        alt("alt-a", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "web"), priority=1),
        alt("alt-b", cv(ContextDimension.PLATFORM, "surface", TruthState.SUCCESS, "mobile"), priority=2),
    )
    r1 = select_policy(alternatives=alternatives, selector=supplied, w9_decision_state=AutonomyDecisionState.ACT, traceability=tr())
    r2 = select_policy(alternatives=alternatives, selector=supplied, w9_decision_state=AutonomyDecisionState.ACT, traceability=tr())
    assert r1 == r2


# --- A5: platform constraints are typed narrowing constraints ---


def test_a5_platform_constraint_narrows_authorized_policy():
    """A5/C7: a platform constraint may further restrict an authorized policy
    (subset of allowed actions, stricter-or-equal ceilings) — never widen."""
    constraint = PlatformPolicyConstraint(
        id="pc-web-1", version=1, adapter_id="adapter-web-1",
        source_policy=base_policy(),
        narrowed_allowed_actions=(DecisionAction.ACT,),  # strict subset
        narrowed_ceilings=PolicyCeiling(
            max_risk=0.1,  # stricter (source 0.3)
            max_blast_radius="limited",  # stricter (source service)
            require_reversible=True,  # not relaxed
            min_confidence=0.9,  # stricter (source 0.8)
            require_human_approval_for_act=True,  # stricter (source False)
        ),
        traceability=tr(),
    )
    constraint.validate()
    assert constraint.adapter_id == "adapter-web-1"
    assert set(constraint.narrowed_allowed_actions) <= set(base_policy().allowed_actions)


def test_a5_platform_constraint_cannot_expand_allowed_actions():
    with pytest.raises(ModelValidationError, match="cannot expand"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),  # no ROLLBACK
            narrowed_allowed_actions=(DecisionAction.ACT, DecisionAction.ROLLBACK),
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )


def test_a5_platform_constraint_cannot_relax_risk_ceiling():
    with pytest.raises(ModelValidationError, match="cannot relax max_risk"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),  # max_risk 0.3
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(
                max_risk=0.5, max_blast_radius="service", require_reversible=True,
                min_confidence=0.8, require_human_approval_for_act=False,
            ),
            traceability=tr(),
        )


def test_a5_platform_constraint_cannot_widen_blast_radius():
    with pytest.raises(ModelValidationError, match="cannot widen max_blast_radius"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),  # blast service
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(
                max_risk=0.3, max_blast_radius="system", require_reversible=True,
                min_confidence=0.8, require_human_approval_for_act=False,
            ),
            traceability=tr(),
        )


def test_a5_platform_constraint_cannot_lower_confidence_floor():
    with pytest.raises(ModelValidationError, match="cannot lower min_confidence"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),  # min_confidence 0.8
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(
                max_risk=0.3, max_blast_radius="service", require_reversible=True,
                min_confidence=0.5, require_human_approval_for_act=False,
            ),
            traceability=tr(),
        )


def test_a5_platform_constraint_cannot_relax_reversibility():
    with pytest.raises(ModelValidationError, match="cannot relax require_reversible"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),  # require_reversible True
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(
                max_risk=0.3, max_blast_radius="service", require_reversible=False,
                min_confidence=0.8, require_human_approval_for_act=False,
            ),
            traceability=tr(),
        )


def test_a5_platform_constraint_cannot_waive_human_approval():
    with pytest.raises(ModelValidationError, match="cannot waive human approval"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=approval_policy(),  # requires human approval for ACT
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=PolicyCeiling(
                max_risk=0.3, max_blast_radius="service", require_reversible=True,
                min_confidence=0.8, require_human_approval_for_act=False,  # waived
            ),
            traceability=tr(),
        )


def test_a5_platform_constraint_rejects_invalid_data():
    """A5/C12: invalid adapter constraint data is rejected deterministically."""
    with pytest.raises(ModelValidationError, match="non-DecisionAction"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),
            narrowed_allowed_actions=("ACT",),  # a plain string is not a DecisionAction
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )
    with pytest.raises(ModelValidationError, match="narrowed_allowed_actions is required"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="adapter-web-1",
            source_policy=base_policy(),
            narrowed_allowed_actions=(),
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )
    with pytest.raises(ModelValidationError, match="adapter_id is required"):
        PlatformPolicyConstraint(
            id="pc-bad", version=1, adapter_id="   ",
            source_policy=base_policy(),
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )
    with pytest.raises(ModelValidationError, match="version must be >= 1"):
        PlatformPolicyConstraint(
            id="pc-bad", version=0, adapter_id="adapter-web-1",
            source_policy=base_policy(),
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=base_policy().ceilings,
            traceability=tr(),
        )
    # invalid ceiling data is rejected deterministically at construction (C12)
    with pytest.raises(ModelValidationError, match="max_risk"):
        PolicyCeiling(
            max_risk=1.5, max_blast_radius="service", require_reversible=True,
            min_confidence=0.8, require_human_approval_for_act=False,
        )


def test_a5_constrain_policy_builder_is_pure_and_deterministic():
    """A5: constrain_policy validates the adapter and returns the construction-
    validated narrowing constraint; identical inputs give identical results."""
    adapter = web_adapter()
    narrowed = PolicyCeiling(
        max_risk=0.1, max_blast_radius="limited", require_reversible=True,
        min_confidence=0.9, require_human_approval_for_act=True,
    )
    c1 = constrain_policy(
        adapter, source_policy=base_policy(),
        narrowed_allowed_actions=(DecisionAction.GATHER_EVIDENCE,),
        narrowed_ceilings=narrowed, constraint_id="pc-build-1",
    )
    c2 = constrain_policy(
        adapter, source_policy=base_policy(),
        narrowed_allowed_actions=(DecisionAction.GATHER_EVIDENCE,),
        narrowed_ceilings=narrowed, constraint_id="pc-build-1",
    )
    assert c1 == c2
    assert c1.adapter_id == "adapter-web-1"
    assert c1.id == "pc-build-1"
    assert c1.traceability == adapter.traceability
    # invalid adapter data is rejected deterministically (C12)
    with pytest.raises(ModelValidationError):
        constrain_policy(
            PlatformAdapter(id="", version=1, surface=PlatformSurface.WEB,
                            capabilities=(AdapterCapability(name="http-api", supported=True),),
                            traceability=tr()),
            source_policy=base_policy(),
            narrowed_allowed_actions=(DecisionAction.ACT,),
            narrowed_ceilings=base_policy().ceilings,
            constraint_id="pc-bad",
        )
    # widening is rejected through the builder as well
    with pytest.raises(ModelValidationError, match="cannot expand"):
        constrain_policy(
            adapter, source_policy=base_policy(),
            narrowed_allowed_actions=(DecisionAction.ROLLBACK,),  # not in source policy
            narrowed_ceilings=narrowed, constraint_id="pc-bad",
        )


def test_a5_platform_constraint_integrates_with_adapter_validation():
    """A5/C6: the constraint narrows the policy while validate_adapter stays a
    pure capability check — both compose side-effect-free."""
    adapter = web_adapter()
    plan = validate_adapter(adapter, required_capabilities=("http-api",))
    assert plan.compatible is True
    constraint = constrain_policy(
        adapter, source_policy=base_policy(),
        narrowed_allowed_actions=(DecisionAction.ACT,),
        narrowed_ceilings=PolicyCeiling(
            max_risk=0.1, max_blast_radius="limited", require_reversible=True,
            min_confidence=0.9, require_human_approval_for_act=True,
        ),
        constraint_id="pc-int-1",
    )
    # platform constraints narrow: subset actions, stricter ceilings
    assert set(constraint.narrowed_allowed_actions) < set(base_policy().allowed_actions)
    assert constraint.narrowed_ceilings.max_risk <= base_policy().ceilings.max_risk


# --- W10 review iteration 4: bounded authority surface ---


def test_w10_review4_symbols_are_exported_within_scope():
    """The iteration-4 additions are exported from the W10 boundary only."""
    import sos
    for name in (
        "AlternativeDimensionEvaluation", "AlternativeEvaluation", "StateNarrowingStep",
        "narrow_decision_state", "PlatformPolicyConstraint", "constrain_policy",
    ):
        assert hasattr(sos, name)
    import sos.personalization as pmod
    import sos.platform as pmod2
    # W10 still does not re-export frozen W9 authority symbols
    forbidden = {"AutonomyRequest", "AutonomyDecision", "evaluate_autonomy", "PolicyCeiling"}
    for mod in (pmod, pmod2):
        exported = {n for n in dir(mod) if not n.startswith("_")}
        assert not (forbidden & exported), f"W10 must not re-export W9 authority: {forbidden & exported}"
