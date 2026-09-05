# SOS Architecture Specification

**Version:** 1.0
**Status:** FROZEN
**Authority:** This document defines the normative SOS architecture. Changes require a governed architecture change.

## 1. Architectural thesis

SOS is a mission-governed control system for evolving software systems. A software system is a changing system state that attempts to realize a mission in a changing environment. Its architecture is an explicit, versioned hypothesis about how that realization should work.

SOS does not optimize code in isolation. It optimizes candidate system states against mission outcomes, stakeholder/value-model objectives, context, environmental conditions, hard constraints, preferences, and risk policies.

## 2. Core invariant

Every consequential evolution decision MUST be traceable through:

`Constitution → Mission → Value Model → Context → System State → Evidence → Hypothesis → Candidate State → Assurance → Experiment → Promotion/Rollback → Learning`

No lower-level artifact may silently redefine a higher-level authority.

## 3. First-class models

### 3.1 Constitution

The constitution defines non-negotiable authority and safety boundaries: who may change what, forbidden actions, required evidence, autonomy limits, emergency behavior, and preservation of mission ownership.

### 3.2 Mission Model

The mission is the enduring purpose SOS is optimizing. It contains goals, desired outcomes, stakeholder definitions, measurable indicators, assumptions, ambiguities, and version history. Initial formalization is collaborative with the user and may evolve over time. Mission revision is a high-authority action and is never silently inferred from telemetry.

### 3.3 Value Model

The Value Model describes how the organization creates and sustains value. It can contribute objectives, economic constraints, incentives, trade-offs, budgets, and opportunity signals. Business-model-derived constraints are explicit and may be hard, soft, risk, or preference constraints.

### 3.4 Context Model

Context represents user, cohort, device/platform, environment, time, workload, network, regulatory region, organization, and other conditions relevant to choosing a realization. SOS may produce different experience and execution policies for different contexts while preserving the global mission and hard constraints.

### 3.5 System State Model

A versioned System State contains the current architecture graph, implementation, configuration, deployment topology, policies, active experiments, runtime environment relationships, and known dependencies. Architecture is a projection of System State, not the whole state.

### 3.6 Architecture Graph

The architecture is a typed, versioned graph with nodes and edges for components, capabilities, services, data stores, interfaces, deployments, trust boundaries, policies, ownership, runtime interactions, requirement realization, observability, and causal relationships. Subgraph evolution is expressed as a boundary-preserving replacement:

`A' = A - S + S'`

The candidate MUST specify the changed subgraph, boundary invariants, expected effects, risks, and required evidence.

### 3.7 Evidence Graph

Evidence links observations, tests, traces, metrics, logs, source revisions, deployments, incidents, experiments and user/business outcomes to the system state and to claims about cause or effect. Failed, unavailable, unknown and empty states are distinct.

OpenTelemetry is a supported telemetry substrate; SOS's evidence model is strictly broader than telemetry and must connect runtime evidence to system structure and mission outcomes. [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/)

### 3.8 Causal Knowledge

SOS maintains hypotheses about how architecture/state interventions affect runtime behavior and mission outcomes. Observational correlation is not treated as intervention evidence. Production experiments update causal confidence.

### 3.9 Architecture Memory

Every meaningful intervention becomes durable experience: context, candidate, predicted effects, actual effects, uncertainty, experiment design, verdict, failures, rollback information, and transferable lessons. Memory is used as a prior, not as proof.

## 4. Control plane

The control plane has these logically distinct capabilities:

1. Observe — ingest runtime, repository, environment, user and business signals.
2. Model — reconcile mission, value, context, system and evidence models.
3. Diagnose — detect mission shortfalls, constraint pressure, regressions and opportunities.
4. Forecast — estimate candidate outcomes and uncertainty.
5. Search — generate and rank candidate system states and subgraph replacements.
6. Assure — test, verify, simulate, analyze impact and establish safety evidence.
7. Experiment — use replay, sandbox, shadow, canary, controlled rollout and other bounded interventions.
8. Decide — choose `ACT`, `EXPERIMENT`, `GATHER_EVIDENCE`, or `ASK`, subject to authority policy.
9. Promote/Rollback — safely advance or revert a candidate using explicit promotion gates.
10. Learn — update causal knowledge, priors, adaptation strategies and architecture memory.

These are capabilities, not independent authorities. The repository must not accidentally create competing sources of semantic, evidence, execution or authorization truth.

## 5. Decision policy

SOS action is governed by a structured autonomy decision, not a raw confidence threshold.

`decision = f(confidence, calibration, expected impact, risk, reversibility, blast radius, evidence, authority)`

User configuration may set confidence and risk thresholds per environment or class of action. Low confidence does not always imply inaction: low-impact reversible changes may be experimented on; high-impact changes may require human approval even at high confidence.

When autonomous authority is insufficient, `ASK` is mandatory. Questions should present alternatives, expected outcomes, trade-offs, evidence quality, and the exact decision needed.

## 6. Optimization model

SOS optimizes expected mission improvement under constraints rather than a single global scalar objective.

Conceptually:

`maximize E[mission_utility(M, V, context, environment, candidate)]`

subject to hard constraints, risk bounds, authority limits, budget limits, policy constraints and required safety properties.

The output is generally a Pareto set or context-conditioned policy rather than a unique architecture. Search may optimize both structural architecture and runtime/policy parameters.

Search-based software engineering research supports multi-objective formulations for software decisions with many conflicting criteria. [Many-objective SBSE survey](https://www.sciencedirect.com/science/article/pii/S0164121218302759)

## 7. Personalization and contextual realization

SOS may optimize different user experiences and execution paths for different users or contexts, analogous in principle to contextual recommendation systems. Personalization is subordinate to the global mission, constitutional constraints, legal/policy constraints, fairness requirements, and system safety.

Prefer, in order:

1. policy/configuration adaptation;
2. shared components with contextual behavior;
3. parameterized architecture;
4. structural divergence only when evidence justifies its complexity.

The system must continuously evaluate population-level externalities, overspecialization, exploration, fairness and mission consistency.

## 8. Platform neutrality

SOS is platform-neutral. Web, mobile, desktop, TV, cross-platform, wearable, API, edge, cloud and other execution surfaces are contexts/adapters, not separate SOS products.

The system must distinguish:

- capability portability;
- architectural portability;
- experience/interaction portability.

It MUST NOT optimize for one cross-platform codebase merely because code sharing is convenient.

## 9. Safe evolution

A candidate moves through a gated lifecycle:

`PROPOSED → ANALYZED → ASSURED → TESTED → SIMULATED/REPLAYED → SHADOW → CANARY → EXPERIMENTAL → PROMOTED`

At any live stage:

`→ ROLLBACK`

A trusted safety boundary and rollback path must dominate untrusted candidate behavior. The Simplex pattern is a relevant assurance precedent. [Black-Box Simplex](https://arxiv.org/abs/2102.12981)

Canary analysis is a relevant production-evolution precedent: partial, time-limited deployment followed by evaluation and possible roll-forward, rollback or escalation. [Google Canary Analysis Service](https://research.google/pubs/canary-analysis-service/)

## 10. Greenfield and brownfield symmetry

Greenfield entry starts with a mission and collaboratively builds the initial Mission, Value, Context and System State hypotheses.

Brownfield entry starts with mission plus existing repository/deployment/runtime evidence and performs architecture recovery before optimization.

Both converge on the same System State and evolution control loop.

## 11. SOS self-evolution

SOS applies the same architecture and governance loop to itself. It may optimize its implementation, models, search strategies, experiment strategies and internal architecture according to its mission and evidence.

A separate meta-adaptation layer evaluates whether SOS's own adaptation mechanisms are effective, learns improvements, and verifies the new adaptation logic. It may not rewrite the Constitution or bypass the assurance/authority boundary without an explicit governed change.

This follows the research direction of meta-adaptive self-learning systems, which separate system/environment/goal/adaptation knowledge and evaluate adaptation-rule accuracy over time. [Comprehensible and dependable self-learning self-adaptive systems](https://www.sciencedirect.com/science/article/pii/S1383762117304472)

## 12. Trust boundaries

The architecture contains four authority classes:

- Intent authority: Constitution, Mission and approved Value Model commitments.
- Knowledge authority: reconciled System, Evidence, Causal and Memory models.
- Execution authority: deployment/runtime mechanisms that physically change or run software.
- Assurance authority: trusted policy/checking/rollback mechanisms that can block or reverse unsafe changes.

LLMs live inside the reasoning/proposal layer. They cannot become a fifth authority class.

## 13. Fundamental invariants

1. Mission outranks architecture.
2. Constitution outranks autonomous optimization.
3. Hard constraints outrank preferences.
4. Evidence outranks assertion.
5. Intervention evidence outranks observational correlation for causal claims.
6. Failed/unknown/unavailable reads remain distinguishable.
7. Candidate architecture cannot become production solely because it was generated.
8. No candidate may exceed granted authority.
9. Every promoted change is reproducible from exact revisions and evidence.
10. Every automated production change has a bounded rollback path unless a governed exception explicitly prohibits rollback.
11. Mission revision is explicit and versioned.
12. SOS may evolve itself, but not by escaping its own Constitution and assurance boundary.

## 14. Research lineage

The architecture synthesizes established research directions rather than claiming to invent their individual mechanisms: goal-oriented requirements engineering, self-adaptive systems, models@run.time, architecture-based adaptation, runtime assurance, search-based software engineering, runtime experimentation/canarying, observability, and recent GenAI-for-self-adaptation research. The intended novelty is their unification under mission-directed, evidence-backed system-state evolution.
