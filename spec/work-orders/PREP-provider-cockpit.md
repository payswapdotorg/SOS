# PREP-provider-cockpit — OpenMuse + Code-OSS Integration Preparation

**Status:** DISPATCHED PREPARATION SPIKE — NOT A ROADMAP COMPLETION
**Owner:** Worker C
**Purpose:** Produce the durable provider/client integration design for the next realization stage.

## Traceability

- Architecture: §§4, 8, 10, 12, 13 of `spec/architecture.md`
- Requirements: R6, R7, R8, R9, R13, R14, R15, R18, R22, R23, R24
- Related implementation boundary: future W11 execution + future client/cockpit integration
- No unmerged sibling branch is a dependency.

## OpenMuse lane

Research and specify how OpenMuse can implement the future `ExecutionProvider` contract for:

- browser sessions;
- terminal/workspace execution;
- persistent tasks;
- computer/desktop control;
- action receipts and task lifecycle.

The integration must preserve SOS authority outside OpenMuse.

The provider must receive already-authorized bounded requests and return execution results/evidence; it must not decide whether an action is mission-authorized.

## Code-OSS lane

Research and specify a Code-OSS-based engineering cockpit that exposes SOS through a thin client/extension boundary.

Candidate cockpit surfaces:

- Mission;
- System State;
- Architecture Graph;
- Evidence;
- Candidate comparison;
- Assurance;
- Experiment/promotion state;
- ASK requests;
- worker/task sessions;
- diffs and exact revision provenance.

The cockpit is a client, not a second authority.

## Required outputs

1. OpenMuse adapter boundary and mapping table.
2. Code-OSS extension/cockpit boundary and command surface.
3. Authority/data-flow diagram.
4. Provider swap strategy.
5. Authentication/authorization separation notes.
6. Session/resume/reconnect behavior.
7. Evidence/receipt propagation mapping.
8. Security and trust-boundary analysis.
9. Smallest first implementation slice for W11.
10. Explicit list of semantics that must remain in SOS core.

## Acceptance criteria

- OpenMuse is treated as replaceable execution infrastructure, not SOS core.
- Code-OSS is treated as a replaceable client surface, not SOS core.
- No UI/provider artifact can become mission, evidence, assurance, experiment, or autonomy authority.
- The design supports more than one future execution provider.
- The design identifies a concrete first implementation path with minimal coupling.

## Explicit exclusions

- No fork/import of OpenMuse into SOS.
- No fork/import of Code-OSS into SOS.
- No live provider integration.
- No deployment.
- No roadmap status mutation.
- No changes to frozen architecture semantics.
