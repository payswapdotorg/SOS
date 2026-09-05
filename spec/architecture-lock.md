# SOS Architecture Lock

**Status:** FROZEN — v1.0
**Purpose:** Guard the architectural boundaries of SOS during ordinary implementation.

## Non-negotiable invariants

### Intent
- The Constitution, Mission, and approved Value Model are higher authority than architecture, implementation, or LLM recommendations.
- Mission revisions are explicit, versioned and human-authorized; telemetry may trigger a revision proposal but may not silently rewrite mission intent.
- Business-model objectives may constrain or prioritize implementation only through explicit Value Model semantics.

### System model
- System State is the canonical conceptual object; architecture is a versioned projection/hypothesis of that state.
- Every candidate change must identify the affected subgraph and its boundary invariants when the change is local.
- Unknown, failed and unavailable states must not be converted into successful empty or inferred values.
- Evidence must preserve exact source revision, deployment revision and temporal context.

### Optimization
- SOS must support conflicting objectives and constraints; implementation must not hard-code a single scalar “architecture quality” as the sole optimization authority.
- Candidate selection must consider expected benefit, uncertainty, risk, reversibility, blast radius and granted authority.
- Contextual/personalized optimization must remain subordinate to global mission and hard constraints.

### Assurance
- Candidate generation and reasoning are untrusted relative to the assurance boundary.
- LLM outputs cannot by themselves establish truth, authorization, safety, completion or causal efficacy.
- Production promotion requires the configured evidence gates.
- Live candidates require a rollback or equivalent governed recovery path unless a documented risk policy explicitly declares rollback impossible and supplies a higher-order containment mechanism.

### Self-evolution
- SOS must evaluate its own adaptation mechanisms using the same evidence-backed loop.
- SOS may not silently rewrite its Constitution, mission authority, evidence authority, assurance authority or autonomy limits.
- Meta-adaptation cannot disable the mechanism that judges meta-adaptation.

### Platform neutrality
- Web, mobile, desktop, TV, cross-platform and other surfaces are adapters/contexts, not separate SOS semantics.
- No platform-specific fork may redefine Mission, Value Model, System State, Evidence, Candidate, Experiment or Promotion semantics.

### Implementation governance
- One bounded Work Order slice per implementation branch/PR.
- No unmerged sibling branch is a dependency.
- Exact base and head SHAs are mandatory for implementation and review evidence.
- A review-ready worker enters durable `WAITING_FOR_ARCHITECT` state; review corrections stay on the same PR.
- Merge is the completion event; post-merge reconciliation records facts and does not approve work.

## Forbidden shortcuts

An ordinary implementation task must stop rather than:

- redefine the mission or constitution;
- introduce a second architecture/evidence/experiment authority;
- let confidence alone authorize high-risk changes;
- treat generated text as evidence;
- skip the configured assurance/experiment gates;
- silently change a user's autonomy threshold;
- optimize away safety, privacy, legal, fairness or business constraints;
- make the platform dictate product semantics;
- use conversation history as required implementation state.

Architecture changes require an explicit Architecture Change Request reviewed under the Architect gate and incorporated into the frozen architecture before dependent implementation proceeds.
