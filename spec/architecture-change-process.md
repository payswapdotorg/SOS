# SOS Architecture Change Process

**Status:** FROZEN GOVERNANCE PROCESS v1.0

Ordinary implementation cannot change frozen SOS architecture. A proposed architectural change follows this sequence:

`PROPOSED → IMPACT_ANALYZED → ARCHITECT_REVIEW → APPROVED → ARCHITECTURE_UPDATED → DEPENDENT_WORK_AUTHORIZED`

## Required change record

An Architecture Change Request must state:

- exact frozen invariant(s) affected;
- reason the invariant no longer suffices;
- evidence motivating the change;
- alternative designs considered;
- mission/value/context implications;
- assurance and risk implications;
- migration/rollback plan;
- compatibility impact;
- implementation Work Orders unlocked by the change;
- exact architecture version transition.

## Hard rule

No Work Order may implement a frozen-architecture change merely because the change appears inside a PR. The Architect must approve the governed architecture change first, and dependent implementation must start from the updated authoritative architecture.

Architecture-change reconciliation never fabricates completion; actual Git merge remains implementation completion authority.
