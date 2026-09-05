# SOS Work Orders

Work Orders are the task-level authorization and acceptance authority referenced by the frozen implementation roadmap.

## Required fields

Each Work Order must define:

- identifier and title;
- mission/requirement traceability;
- dependencies with authoritative merge identities once complete;
- exact scope;
- explicit exclusions;
- owning architecture authorities;
- allowed/forbidden implementation surfaces;
- acceptance criteria;
- deterministic verification;
- real-system/evaluation evidence;
- risk/rollback requirements;
- completion/reconciliation conditions.

One Work Order maps to one bounded implementation branch/PR unless the roadmap explicitly defines an integration Work Order.
