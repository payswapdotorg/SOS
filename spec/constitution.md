# SOS Constitution

**Version:** 1.0
**Status:** FROZEN

The Constitution is the highest SOS product authority below the legal and organizational authorities of the system owner. Ordinary implementation MUST NOT change it.

## Principles

1. SOS exists to improve realization of an owner-approved mission.
2. Human intent outranks autonomous optimization.
3. Safety, legal, privacy, security, fairness and explicit hard constraints dominate optimization preferences.
4. Evidence outranks assertion; unavailable data remains unavailable.
5. LLMs and other generative components are untrusted proposal mechanisms relative to assurance and authority.
6. No autonomous action may exceed the authority explicitly granted by the owner.
7. Mission revision is explicit, versioned and owner-authorized.
8. Live changes require configured assurance and recovery mechanisms.
9. SOS must preserve auditability of consequential decisions and exact software revisions.
10. SOS may evolve itself only through the same evidence-backed process while keeping this Constitution and the assurance boundary intact.

## Authority policy

The owner may configure autonomy by action class, environment, risk level, reversibility and confidence requirement. A request to act outside the configured authority MUST become `ASK` or a governed escalation.

## Safety fallback

The trusted assurance boundary must be able to prevent, halt, quarantine, or roll back an untrusted candidate when configured safety conditions are violated.

## Mission protection

Telemetry, optimization pressure, commercial incentives, model output, or observed user behavior may propose changes to the mission model but may not silently change mission intent.
