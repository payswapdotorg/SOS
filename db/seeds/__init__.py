"""Deterministic demo seed data (PUB-01).

``demo_seed.seed_demo(persistence)`` loads the demo dataset: a demo workspace
with mission (2 revisions), brownfield system recovered through the REAL
``sos.recovery`` pipeline over the LOCAL GitHub fixture repository, evidence
of every wire kind and every truth state, hypotheses, candidates with
multi-objective evaluations, an assurance run produced by the REAL
``sos.assurance.assure_candidate``, decisions produced by the REAL
``sos.autonomy.evaluate_autonomy`` (one ACT, one ASK), authorizations, a
completed experiment, a DemoProvider execution receipt produced through the
REAL ``sos.execution.ExecutionSubstrate`` (W11 authority gates), learning
records, memory entries, jobs, and the activity (audit) trail.

Everything is deterministic: fixed ids, fixed timestamps, content-addressed
domain ids. The seed is idempotent (skips when the demo workspace exists).
"""
