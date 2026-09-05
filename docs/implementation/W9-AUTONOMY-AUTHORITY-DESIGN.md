# W9 Autonomy / Authority Design

W9 separates **authority** from **policy**. `AuthorityGrant` records what the owner has explicitly permitted for an action class and environment. The existing W1 `AutonomyPolicy` remains the earlier decision-policy primitive; W9 does not create a competing semantic authority.

`DecisionRequest` carries confidence, calibration, evidence quality, impact, risk, reversibility and blast radius. `evaluate()` first checks the explicit grant boundary. Missing authority, human-approval requirements, excessive risk/impact, irreversibility, or insufficient evidence/confidence cannot silently become action.

Where a grant explicitly allows evidence gathering, low-confidence/low-evidence requests can produce `GATHER_EVIDENCE`. Otherwise the result is `ASK` with the exact decision, alternatives, evidence quality, uncertainty and trade-offs.

The authority ledger is append-only and decisions are deterministic records. This module produces decisions only; it does not execute them.
