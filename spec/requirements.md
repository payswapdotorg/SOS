# SOS Product Requirements

**Status:** FROZEN BASELINE REQUIREMENTS v1.0

## Mission

SOS helps a software owner continuously improve the realization of a mission. A user may begin with only a mission or may provide an existing software system.

## Product requirements

### R1 — Mission-first
SOS MUST treat Mission as the highest product-level intent beneath its Constitution and above architecture/implementation.

### R2 — Collaborative progressive formalization
SOS MUST help users progressively formalize an initially natural-language mission into goals, outcomes, stakeholders, measures, assumptions, ambiguities, constraints and preferences. The user remains the authority over mission meaning.

### R3 — Mission evolution
SOS MUST version mission models and support explicit revision over time. Production evidence may trigger revision proposals but may not silently alter the mission.

### R4 — Value/business model
SOS MUST represent the business/value model separately from the mission and derive explicit objectives, hard constraints, soft constraints, incentives and opportunities from it.

### R5 — Contextual realization
SOS MUST represent user, cohort, device/platform, environment, time, workload and other context that can change the best realization of the mission.

### R6 — Greenfield and brownfield
SOS MUST support both mission-only greenfield initialization and existing-system onboarding through architecture/state recovery.

### R7 — System State
SOS MUST maintain a versioned System State that includes architecture, implementation, configuration, deployment topology, policies, active experiments and relevant environment relationships.

### R8 — Architecture as hypothesis
SOS MUST treat architecture as a versioned hypothesis. It MUST support bounded subgraph candidate replacement with explicit interface/boundary invariants.

### R9 — Evidence graph
SOS MUST connect code revisions, architecture versions, runtime telemetry, environment state, experiments and mission outcomes into durable evidence.

### R10 — Causal reasoning
SOS MUST distinguish observation/correlation from intervention evidence and maintain explicit causal hypotheses with uncertainty.

### R11 — Candidate generation
SOS MUST generate multiple candidate system states where practical and compare them across mission outcomes, constraints, risk, cost and other objectives.

### R12 — Multi-objective optimization
SOS MUST support Pareto/non-dominated candidate sets or context-conditioned policies rather than requiring a single scalar architecture score.

### R13 — Safe evolution
SOS MUST validate candidates through configured assurance gates before production promotion, using appropriate combinations of static checks, tests, simulation/replay, shadowing, canarying and controlled experiments.

### R14 — Rollback
SOS MUST maintain a bounded rollback/recovery strategy for live changes unless explicitly governed otherwise.

### R15 — Autonomy policy
SOS MUST support configurable autonomy policies that account for calibrated confidence, impact, risk, reversibility, blast radius, evidence quality and authority.

### R16 — Ask
SOS MUST have `ASK` as a first-class decision outcome and MUST ask the user when autonomous authority is insufficient. Questions MUST present the decision, alternatives, evidence, uncertainty and trade-offs.

### R17 — Personalization
SOS MUST be able to optimize user experiences and execution policies by context while preserving global mission, safety, legal, fairness and business constraints.

### R18 — Platform neutrality
SOS MUST work across web, mobile, desktop, TV, cross-platform and other supported surfaces without making platform-specific implementation choices into semantic authorities.

### R19 — Learning
SOS MUST record intervention outcomes as durable architecture memory and use them as priors for future candidate generation and evaluation.

### R20 — Self-evolution
SOS MUST apply its own mission-directed evolution principles to its own architecture, implementation and adaptation mechanisms, subject to its Constitution and assurance boundary.

### R21 — Truthful failure states
SOS MUST preserve distinctions among success, failure, unknown, unsupported and unavailable states.

### R22 — Human authority
SOS MUST expose an explicit authority model showing what users have authorized SOS to decide and act upon.

### R23 — Explainability by evidence
For consequential proposals, SOS MUST be able to explain the affected subgraph, hypothesis, predicted outcomes, evidence quality, risks, required validation and promotion decision.

### R24 — Repository-governed implementation
The SOS project itself MUST use repository-resident architecture, roadmap, Work Orders, evidence and review state so a fresh agent can recover without conversation history.
