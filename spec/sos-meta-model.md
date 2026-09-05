# SOS Meta-Model v1.0

**Status:** FROZEN

This is the canonical conceptual data model for SOS implementation. Concrete storage/serialization may vary only while preserving these semantics.

## Entities

### Constitution
`id, version, owner, immutable_rules, autonomy_limits, assurance_rules`

### Mission
`id, version, authority, statement, goals, desired_outcomes, stakeholders, measures, assumptions, ambiguities, status, parent_version`

### ValueModel
`id, version, business_model, economic_objectives, budgets, incentives, opportunities, constraints`

### Context
`id, user_or_cohort, platform, device, environment, workload, geography, time, regulatory_context, attributes`

### SystemState
`id, version, architecture_ref, implementation_ref, configuration_ref, deployment_ref, policy_ref, environment_ref, active_experiments`

### ArchitectureGraph
`id, version, nodes, edges, boundary_contracts, uncertainty`

Node types include capability, service, component, data store, interface, deployment, trust boundary, policy, model, adapter and external dependency.

Edge types include call, data-flow, dependency, trust, deployment, runtime-interaction, realizes, observes, influences, owns and constrains.

### Evidence
`id, kind, source_ref, subject_ref, timestamp, environment, result, provenance, confidence, availability`

Evidence kinds include observation, test, static-analysis, simulation, replay, shadow, canary, experiment, deployment, user outcome, business outcome, incident and rollback.

### CausalHypothesis
`id, cause, mechanism, effect, context, expected_direction, expected_magnitude, confidence, evidence_refs, status`

### CandidateState
`id, base_system_state, changed_subgraph, replacement_subgraph, invariants, predicted_effects, risks, authority_required, reversibility, blast_radius, confidence`

### Experiment
`id, candidate_ref, hypothesis_ref, design, population/context, allocation, success_metrics, guardrails, rollback_triggers, start/end, result, verdict`

### Decision
`id, candidate_ref, action, rationale, authority_ref, confidence, calibration, risk, evidence_refs, user_input_ref`

Action is one of: `ACT, EXPERIMENT, GATHER_EVIDENCE, ASK, REJECT, ROLLBACK`.

### ArchitectureMemory
`id, context_signature, candidate_pattern, predictions, observations, outcome, learned_rule, provenance, confidence`

## Mandatory relationships

```text
Constitution
  ├── governs → Mission
  ├── governs → ValueModel
  └── bounds → Decision

Mission
  ├── motivates → SystemState
  ├── defines → desired outcomes
  └── constrains → ValueModel interpretation

ValueModel + Context
  └── shape → candidate evaluation

SystemState
  ├── contains/provides → ArchitectureGraph
  └── produces → Evidence

CandidateState
  ├── proposes transition from → SystemState
  ├── predicts → mission/value outcomes
  └── requires → Assurance/Experiment

Experiment
  └── produces → Evidence

Evidence
  └── updates → CausalHypothesis + ArchitectureMemory

ArchitectureMemory
  └── informs → future CandidateState generation
```

## State-transition invariants

A CandidateState cannot become active production SystemState without a valid promotion Decision whose authority and evidence satisfy the current Constitution/Policy.

A Mission change cannot be caused by CandidateState or telemetry alone; it requires an explicit mission-authority decision.

A causal claim used for a high-impact decision must identify whether evidence is observational or intervention-based.

A Decision with insufficient authority MUST be `ASK` or a safer bounded alternative.

A personalized/context-specific CandidateState MUST preserve global mission and hard constraints.

## Context-conditioned architecture

SOS may represent a realization as:

`Policy(context) → System behavior / architecture selection`

The same semantic System State may have multiple context-conditioned execution/experience paths. Platform adapters are implementation mechanisms and cannot redefine the mission semantics.

## Subgraph mutation contract

For local evolution, a CandidateState declares:

`base_graph, target_subgraph, replacement_subgraph, boundary_interfaces, invariants`

and must establish:

`boundary_compatible(target_subgraph, replacement_subgraph) = true`

before the candidate can enter deployment experimentation.

## Uncertainty semantics

Confidence is a calibrated probability estimate where technically justified; otherwise it is a qualitative uncertainty class. The system must preserve raw evidence and calibration results rather than treating an LLM's self-reported confidence as ground truth.
