# SOS Research Basis

**Research date:** 2026-09-05
**Purpose:** Record the evidence base used to freeze SOS architecture v1.0. This is a design-basis record, not an authority over the architecture.

## Evidence and implications

### Goal-oriented requirements engineering

Horkoff et al. report a systematic mapping study of 246 highly cited goal-oriented requirements-engineering papers. Goals are used to elicit, model and analyze requirements, including alternatives and conflicts; the literature shows growing attention to adaptation, variability and evolution.

Source: Horkoff et al., *Goal-oriented requirements engineering: an extended systematic mapping study*, Requirements Engineering, 2019.
https://link.springer.com/article/10.1007/s00766-017-0280-z

**SOS implication:** Mission and goals should be first-class models above architecture; conflicts and alternatives must be explicit.

### Self-adaptive systems

Cheng et al.'s research roadmap identifies modelling, requirements, engineering and assurance as essential views of self-adaptation and highlights uncertainty and assurance as central challenges.

Source: Cheng et al., *Software engineering for self-adaptive systems: A research roadmap*, 2009.
https://research.monash.edu/en/publications/software-engineering-for-self-adaptive-systems-a-research-roadmap/

**SOS implication:** SOS should have explicit models, requirements/mission, adaptation mechanisms and assurance rather than a single autonomous agent.

### Models@run.time

Bencomo, Götz and Song's 2019 state-of-the-art review identified 275 papers on models@run.time and organized the field around models kept actionable during execution, with uncertainty, assurance and runtime evolution as major challenges.

Source: *Models@run.time: a Guided Tour of the State-of-the-Art and Research Challenges*, Software and Systems Modeling, 2019.
https://publications.aston.ac.uk/id/eprint/37117/

**SOS implication:** maintain machine-readable live System State and Architecture models connected to runtime reality.

### Architecture-based adaptation

The Rainbow architecture is a direct precedent for explicit runtime architecture models, adaptation strategies and utility preferences guiding adaptation.

Source: Rainbow/architecture-based self-adaptation literature summarized in *Incorporating architecture-based self-adaptation into an adaptive industrial software system*.
https://www.sciencedirect.com/science/article/abs/pii/S0164121215002113

**SOS implication:** architecture should be an explicit mutable object with adaptation strategies and utility/preferences, but SOS raises the target from runtime quality attributes to mission outcomes.

### Runtime assurance

The Black-Box Simplex Architecture demonstrates a pattern in which runtime assurance can switch from an advanced potentially unsafe controller to a safer baseline and can provide formal safety arguments around runtime checks.

Source: Mehmood et al., *The Black-Box Simplex Architecture for Runtime Assurance of Autonomous CPS*, NFM 2022.
https://arxiv.org/abs/2102.12981

**SOS implication:** untrusted proposal/generation mechanisms must sit behind a trusted assurance boundary with recovery/rollback authority.

### Many-objective software optimization

A survey of many-objective search-based software engineering reports that software-engineering decisions frequently involve many criteria and conflicting objectives, motivating Pareto-oriented optimization and highlighting challenges in formulation, algorithm selection, experiment design and industry applicability.

Source: *A survey of many-objective optimisation in search-based software engineering*, Journal of Systems and Software, 2019.
https://www.sciencedirect.com/science/article/pii/S0164121218302759

**SOS implication:** do not make “architecture quality” one scalar. Support constraints, trade-offs and Pareto candidate sets/context-conditioned policies.

### Runtime experimentation and canarying

Google's Canary Analysis Service describes canarying as a partial, time-limited deployment followed by evaluation, with roll-forward, rollback or human escalation; the service evaluates very large numbers of production changes.

Source: Beyer and Davidovic, *Canary Analysis Service*, ACM Queue, 2018.
https://research.google/pubs/canary-analysis-service/

**SOS implication:** candidate architecture promotion should be evidence-gated and experimental, not an automatic consequence of generation or tests.

### Meta-adaptation

A self-learning self-adaptive-systems approach extends MAPE-K with structured knowledge and a meta-adaptation layer that evaluates previous adaptations, learns improved adaptation rules and verifies adaptation logic at runtime. It separates system, environment, goal and adaptation knowledge.

Source: *Comprehensible and dependable self-learning self-adaptive systems*, Journal of Systems Architecture, 2018.
https://www.sciencedirect.com/science/article/pii/S1383762117304472

**SOS implication:** SOS should evolve its own adaptation mechanisms as a separate meta-level while protecting its governance boundary.

### GenAI for self-adaptation

Li et al.'s 2025 state-of-the-art and roadmap paper surveys GenAI for self-adaptive systems, covering monitoring, analysis, planning, execution, human-on-the-loop interaction and self-evolution while emphasizing hallucination, evaluation, trust and human verification challenges.

Source: Li et al., *Generative AI for Self-Adaptive Systems: State of the Art and Research Roadmap*, 2025.
https://arxiv.org/abs/2512.04680

**SOS implication:** LLMs should be proposal/reasoning mechanisms inside a stronger evidence and assurance architecture, not authorities.

### Observability

OpenTelemetry standardizes traces, metrics, logs and semantic conventions and provides the common telemetry substrate needed to connect runtime evidence to system state.

Source: OpenTelemetry Specification 1.60.0.
https://opentelemetry.io/docs/specs/otel/

**SOS implication:** build telemetry adapters around an evidence graph rather than treating the observability backend itself as the semantic authority.

## Synthesis

The research supports each major mechanism independently. The proposed SOS contribution is architectural synthesis: a single mission-governed control plane in which mission/value/context models constrain an evolving System State; architecture is treated as a hypothesis; evidence and interventions update causal knowledge; search produces bounded candidate state transitions; assurance and experimentation govern promotion; humans retain authority where autonomy is insufficient; contextual personalization is subordinated to the global mission; and SOS applies the same loop to itself.

The literature does **not** establish that this complete synthesis is solved. Open research challenges remain in mission formalization, architecture-to-outcome causality, efficient architecture search, assurance of generated changes, calibrated autonomy, long-horizon learning, and safe self-evolution.
