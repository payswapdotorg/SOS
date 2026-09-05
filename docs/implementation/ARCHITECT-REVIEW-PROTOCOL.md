# SOS Architect Review Protocol

**Status:** FROZEN OPERATING PROTOCOL v1.0

## Review sequence

1. Verify live `main` and PR base SHA.
2. Verify exact PR head SHA actually under review.
3. Inspect the real diff.
4. Verify declared Work Order scope and dependencies from repository/Git history.
5. Map changed concepts to owning SOS authority: Constitution, Mission, Value Model, Context, System State, Evidence, Assurance, Execution, Experiment or Governance.
6. Reject duplicated authorities or protocol-visible semantic forks.
7. Check mission/value/constraint traceability.
8. Check truthfulness of unknown/failed/unavailable states.
9. Check confidence calibration, risk, reversibility, blast radius and authority before autonomous action.
10. Check personalized/contextual behavior against global mission and hard constraints.
11. Check platform neutrality of the semantic core.
12. Check assurance, experiment and rollback gates.
13. Check exact-head deterministic verification and required real-system/evaluation evidence.
14. Approve or issue stable `REQUEST_CHANGES` findings.
15. Merge only after every blocking finding and gate is satisfied.
16. Reconcile canonical state from actual Git merge evidence.
17. Recompute the implementation frontier.

## Hard stops

Stop/request changes when:

- submitted and verified heads differ;
- dependency is an unmerged sibling;
- frozen architecture or Constitution is changed without governed ACR;
- LLM output is treated as authoritative evidence or authorization;
- mission is silently rewritten;
- business incentives silently outrank mission/constraints;
- unavailable data is rendered as successful data;
- contextual personalization bypasses global constraints;
- candidate promotion bypasses assurance/experiment gates;
- rollback/recovery is absent where required;
- tests/evidence are stale-head or incomplete;
- completion is claimed without actual Architect-authorized merge.

## Review packet

A `REQUEST_CHANGES` review must name the exact reviewed head and each finding with stable ID, severity, path, criterion, evidence and required action. Corrections remain on the same PR.
