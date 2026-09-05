# W4 Evidence / Observability Design

W4 establishes the evidence boundary beneath the frozen SOS architecture.

Evidence is a durable record supporting a claim about a governed subject. It is not itself an authority and it does not infer causality.

Each record carries:

`kind + mode + source + subject + timestamp + environment + truthful result + provenance + confidence + availability + traceability`

Observational records and intervention records are explicitly distinguished. W4 rejects experimental/intervention evidence mislabeled as observational.

The collection boundary is append-only. Export sorts records by timestamp and stable ID so identical fixed inputs produce deterministic JSON.

`TelemetryEventEnvelope` is collector-neutral and preserves source/resource/time/attributes without making a live telemetry collector part of the W4 semantic authority.

W3 recovery output can be converted into static-analysis evidence. Runtime deployment/environment gaps remain explicit `UNAVAILABLE` evidence and are never coerced to empty success.

Causal reasoning, candidate generation, assurance, and experiment execution are downstream work orders.
