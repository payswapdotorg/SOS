# W4 Evidence / Observability Design

**Status:** IMPLEMENTED — REVIEW REQUIRED
**Work Order:** `spec/work-orders/W4-evidence-observability.md`
**Dependencies:** W2 merged on `main` as `587201d3e12a10ba9fac6da751d663a40c33dfb9`; W3 merged as `6541441bb706ef1f27b2c38b9eb930433641b14b`

W4 establishes the SOS evidence/observability boundary so observations can be
attached to the recovered System State / Architecture Graph with exact provenance
and truthful truth states, **without pretending telemetry establishes causality
or authorization** (architecture §3.7, §13.6).

## Governing principle

Evidence is broader than telemetry. An observation is a real fact about a
subject; it is **not** a causal claim, an authorization, or proof of runtime
reality beyond what was directly observed. W4 represents each evidence fact at
exactly the confidence its source warrants, reusing W1's `TruthState` /
`TruthfulValue` so the five truthful states (`SUCCESS`, `FAILED`, `UNKNOWN`,
`UNAVAILABLE`, `EMPTY`) are never conflated.

## Evidence record

`Evidence` (dataclass, frozen, construction-validated) carries the frozen
meta-model fields: `id, kind, source_ref, subject_ref, timestamp, environment,
result, provenance, confidence, availability, traceability`.

- `kind` — the frozen 13-kind vocabulary (observation, test, static-analysis,
  simulation, replay, shadow, canary, experiment, deployment, user-outcome,
  business-outcome, incident, rollback).
- `subject_ref` — the id of a recovered W2/W3 System State / Architecture Graph
  entity. Evidence holds the reference as a string; it **never mutates** the
  recovered graph (criterion 2 — no semantic authority change).
- `result` — a `TruthfulValue[Any]`; the observed value on SUCCESS, or an
  explanatory detail on FAILED/UNKNOWN/UNAVAILABLE/EMPTY.
- `provenance` — `EvidenceProvenance{source, observed_subject, timestamp,
  environment, implementation_revision}` with exact source-path + repository
  revision where applicable (None when not supplied — truthful, not fabricated).
- `availability` — the evidence's own capture state (distinct from the observed
  `result.state`): a SUCCESS availability with a FAILED result is lawful
  (successful capture of a failure); an UNAVAILABLE availability with a SUCCESS
  result is rejected (capture-state/observed-state conflation).
- `confidence` — optional calibrated probability in `[0,1]`; None when not
  supplied. (Full causal-confidence machinery is W5, not W4.)

## Deterministic identity

`_evidence_id` is a content-addressed SHA-256 over `(kind, source_ref,
subject_ref, result.state, result.value, result.detail, provenance.*)`.
Identical evidence ⇒ identical id (criterion 6). No `uuid4`, no wall-clock.

## Evidence graph

`EvidenceGraph` is a deterministically-ordered, deduplicating collection:

- `ingest(evidence)` returns a new graph; identical evidence deduplicates by id
  (no duplicate explosion); records remain sorted by id (criterion 6).
- `by_subject(subject_ref)` indexes evidence for a recovered subject.
- `validate(known_subject_ids=...)` rejects records whose `subject_ref` is not a
  known recovered subject (criterion 7) and enforces deterministic ordering +
  no duplicate ids.

## Static evidence adapter — does not invent runtime facts

`StaticEvidenceAdapter` ingests static/test evidence:

- `from_test_result` — kind=TEST, source_ref=test name, result=the test outcome.
- `from_static_observation` — kind=OBSERVATION, source_ref=observation text.
- `unavailable_runtime_observation` — records an unavailable runtime observation
  explicitly with `result.state=UNAVAILABLE` and a reason detail (criterion 4:
  runtime gaps are never synthesized as successful values).

Static evidence carries `implementation_revision` (the repo fact) but does not
fabricate runtime environment observations.

## OpenTelemetry-shaped ingestion boundary (no live collector)

`OpenTelemetryShapedAdapter` accepts directly-supplied OTel-shaped spans,
metrics, and logs as mappings. No live collector is required. Missing runtime
fields stay `UNKNOWN` / `UNAVAILABLE` rather than being fabricated:

- `from_otel_span` — a span missing `status` or `end_time` → `UNKNOWN` result
  (incomplete runtime observation); an ERROR status → `FAILED` result with a
  SUCCESS availability (capture succeeded; observation failed).
- `from_otel_metric` — a metric carrying no value → `UNKNOWN`; a non-numeric
  value → `FAILED`; a numeric value → `SUCCESS`.
- `from_otel_log` — a log with no body → `UNKNOWN`; otherwise `SUCCESS` with the
  body as the observed value.

## Serialization

Evidence graphs round-trip through the existing W1 `JsonModelStore` (deterministic
`json.dumps(..., indent=2, sort_keys=True)`). No new serialization authority is
introduced — W4 reuses the W1 persistence boundary exactly.

## Truthfulness contract summary

| Situation | `result.state` | `availability` |
|---|---|---|
| Test passed | SUCCESS("pass") | SUCCESS |
| Test raised | FAILED(None, "AssertionError") | SUCCESS (capture succeeded) |
| Metric source returned nothing | UNKNOWN(None, "no value") | UNKNOWN |
| Collector unreachable | UNAVAILABLE(None, "reason") | UNAVAILABLE |
| Empty scrape (no samples) | EMPTY(None) | SUCCESS |
| UNAVAILABLE availability + SUCCESS result | **rejected** (conflation) | — |

## Verification scope

Tests cover: deterministic identity + exact provenance; identical-input
identity stability; subject linkage without graph mutation; the five truthful
states distinct; SUCCESS-requires-value / non-SUCCESS-rejects-value; static
evidence does not claim runtime reality; unavailable runtime observation
explicit; W1 traceability preserved + missing-context rejected; deterministic
duplicate ingestion (dedup by id); deterministic ordering; invalid subject
references rejected; malformed evidence (empty id / empty subject) rejected at
construction; out-of-range confidence rejected; the evidence-only boundary
(no causal/candidate/assurance/experiment symbols exported); OTel span
ingestion; OTel missing-fields → UNKNOWN/UNAVAILABLE (no fabrication); JSON
round-trip; by-subject indexing.

## Explicit exclusions (unchanged from Work Order)

No causal inference or causal confidence (W5); no architecture memory/priors
(W5); no candidate generation/search or mutation (W6); no assurance verdicts or
safety gates (W7); no experimentation/promotion/rollback (W8); no autonomy/
action/ASK execution (W9); no redefinition of W2/W3 semantics; no treatment of
telemetry as a complete evidence model; no fabrication of runtime/deployment/
environment observations from static artifacts.
