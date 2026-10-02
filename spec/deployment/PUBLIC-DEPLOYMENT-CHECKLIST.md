# SOS Public Deployment — Completion Checklist

**Status:** ACTIVE — completion ledger (Public Deployment Overlay)
**Machine state:** `spec/development-state/public-deployment-state.json`
**Definition of completion:** operator directive §23 (verbatim in
`spec/deployment/PUBLIC-DEPLOYMENT-DIRECTIVE.md`).

## Ledger

| Item | Title | Owner | Dependencies | Status |
|------|-------|-------|--------------|--------|
| PUB-00 | Repository deployment contract | TL | — | IN_PROGRESS (this delivery) |
| PUB-01 | FastAPI control-plane adapter | Worker A | PUB-00 | PENDING |
| PUB-02 | Next.js public cockpit | Worker B | PUB-00 | PENDING |
| PUB-03 | Free-tier infrastructure | Worker C | PUB-00 | PENDING |
| PUB-04 | GitHub authentication + tenancy | Worker B | PUB-01, PUB-02 | PENDING |
| PUB-05 | Neon persistence | Worker A | PUB-01 | PENDING |
| PUB-06 | Upstash job/coordination layer | Worker A | PUB-01, PUB-05 | PENDING |
| PUB-07 | R2 evidence/artifact layer | Worker C | PUB-01 | PENDING |
| PUB-08 | Apify bounded execution provider | Worker C | PUB-06, PUB-07 | PENDING |
| PUB-09 | Integrated user journeys | TL (A+B+C) | PUB-04…PUB-08 | PENDING |
| PUB-10 | Security/adversarial verification | Worker C + review | PUB-09 | PENDING |
| PUB-11 | Public demo deployment (Stage B) | TL + operator inputs | PUB-10 | PENDING |
| PUB-12 | Authenticated beta deployment (Stage C) | TL + operator inputs | PUB-11 | PENDING |
| PUB-13 | Final deployment Architect gate | TL + independent review | PUB-12 | PENDING |

Status values: `PENDING → DISPATCHED → WAITING_FOR_ARCHITECT → APPROVED →
MERGED → COMPLETE` (+ `BLOCKED_ON_OPERATOR_INPUT` / `WAITING_FOR_CAPACITY`
where truthful). An item is COMPLETE only after merge + canonical
reconciliation (contract §H).

## Journey acceptance (directive §18; directive numbering had two "Journey 6" —
renumbered here as 6/7, cited as-received in the directive record)

1. **Anonymous demo:** Landing → demo workspace → existing system →
   architecture → evidence → candidate comparison → decision explanation.
2. **New user:** Landing → GitHub login → create workspace → create mission →
   approve mission → create system.
3. **Brownfield:** GitHub repository → exact revision → architecture recovery →
   uncertainty → evidence → candidate set.
4. **Governed optimization:** Candidate → assurance → experiment →
   authorization → execution provider → receipt → evidence → promotion/rollback.
5. **ASK:** Insufficient authority → ASK → user sees exact decision →
   approves/rejects/provides evidence → lifecycle continues.
6. **Failure:** Provider fails → FAILED evidence → no false SUCCESS →
   rollback/recovery path → learning record.
7. **Provider isolation:** Apify cannot authorize itself; Render cannot redefine
   SOS policy; Vercel cannot create authoritative decisions; Redis cannot become
   evidence authority; R2 cannot become semantic state.

## Security gate

All 21 directive §19 lines verified per `PUBLIC-DEPLOYMENT-SECURITY.md` (S1–S21)
— each passing with executable evidence or honestly recorded as
operator-input-blocked.

## Final state (directive §23)

```text
SOS-v1 semantic roadmap  🟢 W0 → … → 🟢 W15 (frozen, gate green)
        + PUBLIC DEPLOYMENT PUB-00 → … → 🟢 PUB-13
        = Vercel + Render + Neon + Upstash + R2 + Apify
        = REAL PUBLIC SOS PRODUCT
```

PUB-13 sign-off record: `spec/development-state/PUB-13-final-sign-off.md`
(TL-authored at approval, independent-context review verdict recorded).
