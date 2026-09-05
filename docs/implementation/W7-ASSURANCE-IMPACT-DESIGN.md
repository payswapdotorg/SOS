# W7 Assurance / Impact Design

W7 is the trusted checking boundary after candidate search and before experimentation.

A candidate is evaluated against required assurance checks, evidence truth states, impact, risk, and configured policy thresholds. PASS is never inferred merely because a check object exists: successful checks require successful evidence references.

Required checks that are missing, failed, inconclusive, not run, or supported only by non-success evidence cause a `BLOCK` verdict. Risk, residual risk, and blast radius are independently bounded.

The assurance result is descriptive evidence about whether the configured gates were satisfied. W7 does not deploy, experiment, promote, rollback, or mutate the candidate/system state.
