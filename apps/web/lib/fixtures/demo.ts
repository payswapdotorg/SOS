/**
 * DEMO FIXTURES — the deterministic demo dataset (Journey-1 seed story).
 *
 * Everything here is demo data, clearly labeled as such in the UI. It exists
 * so the cockpit is demonstrable standalone when no API is configured
 * (contract §D PUB-02: "fixture/demo mode serves Journey-1 content
 * client-side when no API is configured").
 *
 * Honesty rules honored by construction:
 * - all six truth states appear and are labeled truthfully;
 * - demo receipts carry `demo: true`;
 * - candidate evaluation is multi-objective with Pareto membership (no
 *   single "AI score");
 * - one decision is an ASK awaiting owner action;
 * - no fabricated successes: failures, unknowns and unsupported states are
 *   kept exactly as they are.
 */

import type { DemoDataset } from "@/lib/api/types";

export const DEMO_LABEL = "Demo data";
export const DEMO_WORKSPACE_SLUG = "aurora-fulfillment-demo";

export const demo: DemoDataset = {
  workspace: {
    id: "ws_aurora_demo",
    name: "Aurora Fulfillment (Demo)",
    slug: DEMO_WORKSPACE_SLUG,
    createdAt: "2026-09-14T09:12:00Z",
  },

  users: [
    {
      id: "user_owner",
      githubId: "6011201",
      login: "aurora-owner",
      displayName: "Dana Okafor (demo owner)",
      createdAt: "2026-09-14T09:10:00Z",
    },
    {
      id: "user_operator",
      githubId: "6011202",
      login: "aurora-eng",
      displayName: "Wei Chen (demo operator)",
      createdAt: "2026-09-14T09:11:00Z",
    },
  ],

  mission: {
    id: "mis_aurora_001",
    workspaceId: "ws_aurora_demo",
    title: "Reduce deployment failure rate on the fulfillment platform",
    status: "ACTIVE",
    currentRevisionId: "mrev_aurora_002",
  },

  missionRevisions: [
    {
      id: "mrev_aurora_001",
      missionId: "mis_aurora_001",
      revision: 1,
      goals: [
        {
          id: "g1",
          statement: "Reduce deployment-caused order-processing failures",
          rationale: "Two release trains last quarter caused failed orders.",
        },
      ],
      outcomes: [
        {
          id: "o1",
          statement: "Deployment failure rate below 2% per release train",
          metric: "deploy_failure_rate",
        },
      ],
      stakeholders: [
        {
          id: "s1",
          name: "Marta Reyes",
          role: "Business owner",
          interest: "Order revenue continuity during releases",
        },
      ],
      measures: [
        {
          id: "m1",
          name: "Deployment success rate",
          target: "≥ 98%",
          current: "96.8%",
          unit: "%",
        },
      ],
      constraints: [
        {
          id: "c1",
          statement: "No unrevertable production changes without an explicit owner exception",
          severity: "HARD",
        },
      ],
      preferences: [
        {
          id: "p1",
          statement: "Prefer gradual canaries over big-bang switches",
        },
      ],
      approval: {
        state: "APPROVED",
        requestedBy: "user_owner",
        decidedBy: "user_owner",
        decidedAt: "2026-09-14T10:00:00Z",
      },
    },
    {
      id: "mrev_aurora_002",
      missionId: "mis_aurora_001",
      revision: 2,
      goals: [
        {
          id: "g1",
          statement: "Reduce deployment-caused order-processing failures",
          rationale: "Two release trains last quarter caused failed orders and a 41-minute rollback gap.",
        },
        {
          id: "g2",
          statement: "Keep fulfillment latency within SLO while evolving the platform",
          rationale: "Latency SLO protects the checkout path, the highest-value journey.",
        },
        {
          id: "g3",
          statement: "Preserve auditable, reversible production changes",
          rationale: "Reversibility is a hard constraint from the compliance side.",
        },
      ],
      outcomes: [
        {
          id: "o1",
          statement: "Deployment failure rate below 2% per release train",
          metric: "deploy_failure_rate",
        },
        {
          id: "o2",
          statement: "p95 order-acceptance latency stays under 400 ms at seasonal peak",
          metric: "p95_order_acceptance_ms",
        },
        {
          id: "o3",
          statement: "Every live change has a tested rollback path",
          metric: "rollback_drill_success_rate",
        },
      ],
      stakeholders: [
        {
          id: "s1",
          name: "Marta Reyes",
          role: "Business owner",
          interest: "Order revenue continuity during releases",
        },
        {
          id: "s2",
          name: "Priya Nair",
          role: "Operations lead",
          interest: "Predictable, low-drama release trains",
        },
        {
          id: "s3",
          name: "Wei Chen",
          role: "Engineering lead",
          interest: "Maintainable services and honest observability",
        },
        {
          id: "s4",
          name: "Compliance office",
          role: "Auditor",
          interest: "Complete audit trail for every consequential change",
        },
      ],
      measures: [
        {
          id: "m1",
          name: "Deployment success rate",
          target: "≥ 98%",
          current: "96.8%",
          unit: "%",
        },
        {
          id: "m2",
          name: "p95 order-acceptance latency",
          target: "≤ 400",
          current: "412",
          unit: "ms",
        },
        {
          id: "m3",
          name: "Rollback drill success",
          target: "100%",
          current: "67%",
          unit: "% of live changes",
        },
      ],
      constraints: [
        {
          id: "c1",
          statement: "No unrevertable production changes without an explicit owner exception",
          severity: "HARD",
        },
        {
          id: "c2",
          statement: "Payment data stays inside the PCI trust boundary",
          severity: "HARD",
        },
        {
          id: "c3",
          statement: "Monthly infrastructure spend stays within the free-tier budget envelope",
          severity: "SOFT",
        },
      ],
      preferences: [
        {
          id: "p1",
          statement: "Prefer gradual canaries over big-bang switches",
        },
        {
          id: "p2",
          statement: "Prefer configuration-first changes over structural ones when evidence is weak",
        },
      ],
      approval: {
        state: "APPROVED",
        requestedBy: "user_owner",
        decidedBy: "user_owner",
        decidedAt: "2026-09-21T16:40:00Z",
      },
    },
  ],

  systems: [
    {
      id: "sys_fulfillment",
      workspaceId: "ws_aurora_demo",
      name: "fulfillment-platform",
      mode: "BROWNFIELD",
      currentRevisionId: "srev_fulfillment_004",
    },
    {
      id: "sys_notification_relay",
      workspaceId: "ws_aurora_demo",
      name: "notification-relay",
      mode: "BROWNFIELD",
      currentRevisionId: "srev_notification_001",
    },
    {
      id: "sys_legacy_reports",
      workspaceId: "ws_aurora_demo",
      name: "legacy-reports",
      mode: "BROWNFIELD",
      currentRevisionId: "srev_legacy_reports_001",
    },
    {
      id: "sys_partner_edge",
      workspaceId: "ws_aurora_demo",
      name: "partner-edge-sync",
      mode: "BROWNFIELD",
      currentRevisionId: "srev_partner_edge_001",
    },
  ],

  systemRevisions: [
    {
      id: "srev_fulfillment_004",
      systemId: "sys_fulfillment",
      revision: 4,
      stateSummary: {
        summary:
          "Recovered from exact revision: modular monolith + queue workers; order path, inventory reservation and notification dispatch are separate services over PostgreSQL and Redis.",
        health: "SUCCESS",
        drift: "MINOR",
        services: 4,
        dataStores: 2,
        integrations: 3,
      },
      uncertainty: {
        state: "UNKNOWN",
        reason:
          "Code topology recovered at high confidence; runtime behavior under seasonal peak is only partially observed (see evidence: runtime observation, telemetry).",
        confidence: 0.82,
      },
      sourceRef: {
        kind: "GITHUB_REPO",
        url: "https://github.com/aurora-demo/fulfillment-platform",
        revision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
        immutable: true,
      },
      recovery: {
        jobId: "job_rec_fulfillment_001",
        status: "SUCCESS",
        note: "Architecture recovery completed; graph validated (all edges resolve).",
      },
    },
    {
      id: "srev_notification_001",
      systemId: "sys_notification_relay",
      revision: 1,
      stateSummary: {
        summary:
          "Recovery in progress: 2 of an estimated 5 nodes recovered. The system state is NOT yet authoritative — treat topology as partial.",
        health: "UNKNOWN",
        drift: "UNKNOWN",
        services: 1,
        dataStores: 0,
        integrations: 1,
      },
      uncertainty: {
        state: "UNAVAILABLE",
        reason:
          "Recovery job still running; runtime observation currently UNAVAILABLE (agent unreachable), so neither structure nor behavior is fully known yet.",
        confidence: null,
      },
      sourceRef: {
        kind: "GITHUB_REPO",
        url: "https://github.com/aurora-demo/notification-relay",
        revision: "b2c3d4e5f60718293a4b5c6d7e8f90123456789a",
        immutable: true,
      },
      recovery: {
        jobId: "job_rec_notification_001",
        status: "UNKNOWN",
        note: "Recovery running (started 2026-10-02). Outcome unknown — no success claimed yet.",
      },
    },
    {
      id: "srev_legacy_reports_001",
      systemId: "sys_legacy_reports",
      revision: 1,
      stateSummary: {
        summary:
          "Recovery FAILED: the recovered graph was internally inconsistent (edges referencing missing nodes). No system state is published; nothing is inferred in its place.",
        health: "FAILED",
        drift: "UNKNOWN",
        services: 0,
        dataStores: 0,
        integrations: 0,
      },
      uncertainty: {
        state: "FAILED",
        reason: "Failure is explicit: the analysis produced a structurally invalid graph.",
        confidence: null,
      },
      sourceRef: {
        kind: "GITHUB_REPO",
        url: "https://github.com/aurora-demo/legacy-reports",
        revision: "c3d4e5f60718293a4b5c6d7e8f90123456789ab",
        immutable: true,
      },
      recovery: {
        jobId: "job_rec_legacy_001",
        status: "FAILED",
        note: "Recovery job FAILED — inconsistent graph (see job error state).",
      },
    },
    {
      id: "srev_partner_edge_001",
      systemId: "sys_partner_edge",
      revision: 1,
      stateSummary: {
        summary:
          "Source kind not supported by the recovery adapter (GitLab-hosted). Recovery is UNSUPPORTED for this source; no system state exists.",
        health: "UNKNOWN",
        drift: "UNKNOWN",
        services: 0,
        dataStores: 0,
        integrations: 0,
      },
      uncertainty: {
        state: "UNSUPPORTED",
        reason: "UNSUPPORTED is not FAILED: the source is reachable, the adapter does not cover it.",
        confidence: null,
      },
      sourceRef: {
        kind: "OTHER",
        url: "https://gitlab.com/aurora-demo/partner-edge-sync",
        revision: "unknown",
        immutable: false,
      },
      recovery: {
        jobId: "job_rec_partner_edge_001",
        status: "UNSUPPORTED",
        note: "Source kind OTHER (GitLab) is not supported by the GitHub source adapter.",
      },
    },
  ],

  architectureGraphs: {
    sys_fulfillment: {
      nodes: [
        { id: "gw", label: "API gateway", kind: "INTERFACE", notes: "Public entry; request routing and auth." },
        { id: "order", label: "order-service", kind: "SERVICE", notes: "Order acceptance and lifecycle." },
        { id: "inv", label: "inventory-service", kind: "SERVICE", notes: "Stock levels and reservation locks." },
        { id: "notif", label: "notification-service", kind: "SERVICE", notes: "Outbound emails + webhooks." },
        { id: "worker", label: "queue-worker", kind: "COMPONENT", notes: "Async job consumer (reservation TTL, retries)." },
        { id: "pg", label: "orders-db (PostgreSQL)", kind: "DATA_STORE", notes: "Orders, inventory rows; PCI-scoped credentials." },
        { id: "redis", label: "cache (Redis)", kind: "DATA_STORE", notes: "Read-through cache + reservation lock TTL." },
        { id: "deploy", label: "deploy-pipeline", kind: "DEPLOYMENT", notes: "Single-stage rollout today; no canary stage." },
        { id: "obs", label: "observability", kind: "CAPABILITY", notes: "Traces + metrics for order path; partial elsewhere." },
      ],
      edges: [
        { id: "e1", source: "gw", target: "order", kind: "CALLS", label: "accept order" },
        { id: "e2", source: "gw", target: "inv", kind: "CALLS", label: "reserve stock" },
        { id: "e3", source: "order", target: "pg", kind: "DATA_FLOW", label: "persist order (write)" },
        { id: "e4", source: "inv", target: "pg", kind: "DATA_FLOW", label: "stock rows (read)" },
        { id: "e5", source: "inv", target: "redis", kind: "DATA_FLOW", label: "reservation lock (write)" },
        { id: "e6", source: "worker", target: "redis", kind: "DATA_FLOW", label: "TTL expiry events (read)" },
        { id: "e7", source: "worker", target: "inv", kind: "CALLS", label: "release lock" },
        { id: "e8", source: "order", target: "notif", kind: "CALLS", label: "order events" },
        { id: "e9", source: "deploy", target: "gw", kind: "DEPLOYS", label: "revisions" },
        { id: "e10", source: "obs", target: "order", kind: "OBSERVES", label: "traces/metrics" },
        { id: "e11", source: "obs", target: "inv", kind: "OBSERVES", label: "metrics only" },
      ],
    },
    sys_notification_relay: {
      nodes: [
        { id: "relay", label: "relay-core", kind: "SERVICE", notes: "Recovered so far; fan-out of notifications." },
        { id: "sink", label: "partner-webhook", kind: "INTERFACE", notes: "Outbound webhook sink (recovered)." },
      ],
      edges: [
        { id: "ne1", source: "relay", target: "sink", kind: "CALLS", label: "webhook post" },
      ],
    },
    sys_legacy_reports: { nodes: [], edges: [] },
    sys_partner_edge: { nodes: [], edges: [] },
  },

  evidence: [
    {
      id: "ev_001",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "source_revision",
      status: "SUCCESS",
      provenance: "GitHub source adapter (recovery job job_rec_fulfillment_001)",
      timestamp: "2026-09-24T11:03:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: 0.98,
      confidenceNote: "Exact pinned revision, content-addressed artifacts.",
      artifactRef: {
        name: "recovery-manifest.json",
        signedUrl: "/demo/artifacts/ev_001-recovery-manifest.json?sig=demo-signature&expires=2026-10-31",
        mediaType: "application/json",
        sizeBytes: 38214,
      },
    },
    {
      id: "ev_002",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "runtime_observation",
      status: "SUCCESS",
      provenance: "Tracing agent (order-acceptance span, last 24h)",
      timestamp: "2026-10-03T08:00:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: 0.86,
      confidenceNote: "Sampled 10%; consistent across regions.",
    },
    {
      id: "ev_003",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_notification_relay",
      kind: "runtime_observation",
      status: "UNAVAILABLE",
      provenance: "Tracing agent on notification-relay",
      timestamp: "2026-10-03T08:00:00Z",
      sourceRevision: "b2c3d4e5f60718293a4b5c6d7e8f90123456789a",
      relatedSystemState: "srev_notification_001",
      confidence: null,
      confidenceNote: "Agent unreachable for the last 6h; no data — UNAVAILABLE, not empty.",
    },
    {
      id: "ev_004",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "test_result",
      status: "SUCCESS",
      provenance: "CI workflow (integration suite, 312 tests)",
      timestamp: "2026-10-01T22:14:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: 0.94,
      confidenceNote: "Deterministic suite; green at exact revision.",
      artifactRef: {
        name: "integration-report.xml",
        signedUrl: "/demo/artifacts/ev_004-integration-report.xml?sig=demo-signature&expires=2026-10-31",
        mediaType: "application/xml",
        sizeBytes: 210431,
      },
    },
    {
      id: "ev_005",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_legacy_reports",
      kind: "test_result",
      status: "FAILED",
      provenance: "Rollback drill harness (legacy-reports)",
      timestamp: "2026-09-30T18:40:00Z",
      sourceRevision: "c3d4e5f60718293a4b5c6d7e8f90123456789ab",
      relatedSystemState: "srev_legacy_reports_001",
      confidence: 0.9,
      confidenceNote: "Drill executed and failed — honest failure, blocks promotion of any candidate relying on that path.",
      artifactRef: {
        name: "rollback-drill.log",
        signedUrl: "/demo/artifacts/ev_005-rollback-drill.log?sig=demo-signature&expires=2026-10-31",
        mediaType: "text/plain",
        sizeBytes: 15870,
      },
    },
    {
      id: "ev_006",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "telemetry",
      status: "SUCCESS",
      provenance: "Deploy metrics (last 30 days)",
      timestamp: "2026-10-03T07:55:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: 0.91,
      confidenceNote: "31 deploys; failure rate 3.2% observed (mission shortfall signal).",
    },
    {
      id: "ev_007",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_partner_edge",
      kind: "telemetry",
      status: "UNSUPPORTED",
      provenance: "Observability substrate probe",
      timestamp: "2026-10-02T13:00:00Z",
      sourceRevision: "unknown",
      relatedSystemState: "srev_partner_edge_001",
      confidence: null,
      confidenceNote: "partner-edge-sync emits no supported telemetry substrate — UNSUPPORTED, not failed.",
    },
    {
      id: "ev_008",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "environment",
      status: "SUCCESS",
      provenance: "Environment snapshot (staging + production)",
      timestamp: "2026-10-03T07:00:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: 0.97,
      confidenceNote: "Snapshot pinned to deployed revision.",
    },
    {
      id: "ev_009",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "environment",
      status: "UNKNOWN",
      provenance: "Local development environments",
      timestamp: "2026-10-03T07:00:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: null,
      confidenceNote: "Local environments are not captured — unknown, not empty.",
    },
    {
      id: "ev_010",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "experiment",
      status: "SUCCESS",
      provenance: "Shadow replay (queue-timeout intervention, Sep 2026)",
      timestamp: "2026-09-19T09:30:00Z",
      sourceRevision: "9f8e7d6c5b4a39281706f5e4d3c2b1a098765432",
      relatedSystemState: "srev_fulfillment_003",
      confidence: 0.78,
      confidenceNote: "24h shadow; replay matched production semantics.",
    },
    {
      id: "ev_011",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "experiment",
      status: "EMPTY",
      provenance: "Canary analysis window (candidate C1)",
      timestamp: "2026-10-04T00:00:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: null,
      confidenceNote: "Canary window opened; no eligible deployments yet — observed and EMPTY (distinct from unknown).",
    },
    {
      id: "ev_012",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "business_outcome",
      status: "SUCCESS",
      provenance: "Order ledger reconciliation (release train 2026-W39)",
      timestamp: "2026-09-29T23:59:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: 0.99,
      confidenceNote: "Zero failed customer orders attributable to the release train.",
    },
    {
      id: "ev_013",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_legacy_reports",
      kind: "source_revision",
      status: "FAILED",
      provenance: "GitHub source adapter (recovery job job_rec_legacy_001)",
      timestamp: "2026-09-26T15:20:00Z",
      sourceRevision: "c3d4e5f60718293a4b5c6d7e8f90123456789ab",
      relatedSystemState: "srev_legacy_reports_001",
      confidence: 0.2,
      confidenceNote: "Revision ref resolved but the recovered graph was invalid — explicit failure recorded.",
    },
    {
      id: "ev_014",
      workspaceId: "ws_aurora_demo",
      systemId: "sys_fulfillment",
      kind: "business_outcome",
      status: "UNKNOWN",
      provenance: "Seasonal-peak revenue attribution (pending finance close)",
      timestamp: "2026-10-03T07:00:00Z",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      relatedSystemState: "srev_fulfillment_004",
      confidence: null,
      confidenceNote: "Attribution not yet computed — unknown until finance closes the period.",
    },
  ],

  hypotheses: [
    {
      id: "hyp_001",
      statement:
        "Adding a canary stage with automatic rollback to the deployment pipeline reduces deployment-caused order failures.",
      causal: {
        cause: "canary + auto-rollback gate on the deploy pipeline",
        effect: "deployment failure rate drops (bounded blast radius, auto-revert on SLO breach)",
        mechanism:
          "5% cohort absorbs regressions; rollback controller reverts before full rollout when canary SLO breaches.",
      },
      evidenceRefs: ["ev_006", "ev_010", "ev_005", "ev_011"],
      status: "PARTIALLY_SUPPORTED",
    },
    {
      id: "hyp_002",
      statement:
        "Extracting inventory reservation into a dedicated service reduces p95 order-acceptance latency under peak load.",
      causal: {
        cause: "inventory-reservation extraction (own service + datastore)",
        effect: "p95 order-acceptance latency drops under peak",
        mechanism: "reservation locking leaves the order hot path; lock contention isolated to the new service.",
      },
      evidenceRefs: ["ev_002"],
      status: "PROPOSED",
    },
  ],

  candidates: [
    {
      id: "cand_001",
      name: "Canary + auto-rollback gate for the deployment pipeline",
      subgraphReplacement: {
        boundary: "deploy-pipeline stage between build and full rollout",
        removes: ["deploy"],
        adds: [
          { id: "canary_stage", label: "canary-analysis stage", kind: "COMPONENT" },
          { id: "rollback_ctl", label: "auto-rollback controller", kind: "COMPONENT" },
        ],
        boundaryInvariants: [
          "deploy interface (input contract) unchanged",
          "release artifacts remain signed and content-addressed",
          "rollback controller has no authority beyond reverting its own rollout",
        ],
      },
      effects: [
        {
          onObjective: "deployment_failure_rate",
          description: "Est. 3.2% → ~1.4% once canary + auto-revert gate the rollout.",
          direction: "IMPROVE",
        },
        {
          onObjective: "p95_order_acceptance_ms",
          description: "No direct latency effect; canary adds no request-path work.",
          direction: "NEUTRAL",
        },
      ],
      costs: [
        { description: "Pipeline engineering", magnitude: "MEDIUM", quantifier: "~3 engineer-weeks" },
        { description: "Canary infra", magnitude: "LOW", quantifier: "~$4/month" },
      ],
      risks: [
        {
          description: "Rollback controller itself misbehaves under partial rollout",
          likelihood: "MEDIUM",
          severity: "MEDIUM",
          mitigation: "Shadow mode first; rollback controller covered by the same audit trail.",
        },
      ],
      constraints: [
        {
          constraint: "No unrevertable production changes",
          compliance: "SATISFIED",
          note: "Change is configuration-first; revert restores the prior pipeline.",
        },
        {
          constraint: "Rollback drill success 100% of live changes",
          compliance: "AT_RISK",
          note: "Current drill FAILED (ev_005) — remediation is a promotion precondition.",
        },
      ],
      evidenceRefs: ["ev_006", "ev_010", "ev_005", "ev_011"],
      reversibility: {
        level: "FULLY_REVERSIBLE",
        rollbackPath: "Revert pipeline configuration; canary stage is additive.",
        notes: "No data or schema migration involved.",
      },
      evaluation: {
        objectives: [
          { objectiveId: "obj_failure_rate", objective: "Deployment failure rate", direction: "MINIMIZE", value: "1.4% (est.)", unit: "%", assessment: "GOOD" },
          { objectiveId: "obj_p95", objective: "p95 order-acceptance latency", direction: "MINIMIZE", value: "410", unit: "ms", assessment: "NEUTRAL" },
          { objectiveId: "obj_cost", objective: "Monthly infrastructure cost delta", direction: "MINIMIZE", value: "+4", unit: "USD", assessment: "GOOD" },
          { objectiveId: "obj_rollback", objective: "Rollback exposure", direction: "MINIMIZE", value: "2", unit: "min at risk", assessment: "GOOD" },
        ],
        paretoFront: true,
      },
    },
    {
      id: "cand_002",
      name: "Extract inventory reservation into a dedicated service",
      subgraphReplacement: {
        boundary: "inventory reservation subgraph inside the order-acceptance path",
        removes: ["inv"],
        adds: [
          { id: "inv_svc", label: "inventory-reservation-service", kind: "SERVICE" },
          { id: "inv_db", label: "reservations-db", kind: "DATA_STORE" },
        ],
        boundaryInvariants: [
          "reservation API contract identical from order-service's view",
          "PCI trust boundary unchanged",
          "dual-write window bounded and reversible",
        ],
      },
      effects: [
        {
          onObjective: "p95_order_acceptance_ms",
          description: "Est. 412 → ~340 ms at peak (reservation locking leaves the hot path).",
          direction: "IMPROVE",
        },
        {
          onObjective: "deployment_failure_rate",
          description: "Small independent-effect estimate; not the primary lever.",
          direction: "NEUTRAL",
        },
      ],
      costs: [
        { description: "Service extraction + migration tooling", magnitude: "HIGH", quantifier: "~8 engineer-weeks" },
        { description: "Additional managed services", magnitude: "MEDIUM", quantifier: "~$18/month" },
      ],
      risks: [
        {
          description: "Data migration consistency between orders-db and reservations-db",
          likelihood: "MEDIUM",
          severity: "HIGH",
          mitigation: "Bounded dual-write with reconciliation job; shadow period before cutover.",
        },
        {
          description: "Latency claim rests on observational evidence only",
          likelihood: "MEDIUM",
          severity: "MEDIUM",
          mitigation: "Shadow experiment to produce intervention evidence before any cutover.",
        },
      ],
      constraints: [
        {
          constraint: "Monthly free-tier budget envelope",
          compliance: "AT_RISK",
          note: "+$18/month consumes most of the remaining envelope — owner judgment required.",
        },
        {
          constraint: "Prefer config-first changes while evidence is weak",
          compliance: "UNCERTAIN",
          note: "Structural change with weak evidence — explicitly an owner trade-off.",
        },
      ],
      evidenceRefs: ["ev_002"],
      reversibility: {
        level: "PARTIALLY_REVERSIBLE",
        rollbackPath: "Service revert is straightforward; migrated reservation data requires a back-fill rollback.",
        notes: "Rollback path exists but is data-heavy; drill needed.",
      },
      evaluation: {
        objectives: [
          { objectiveId: "obj_failure_rate", objective: "Deployment failure rate", direction: "MINIMIZE", value: "3.0% (est.)", unit: "%", assessment: "NEUTRAL" },
          { objectiveId: "obj_p95", objective: "p95 order-acceptance latency", direction: "MINIMIZE", value: "340 (est.)", unit: "ms", assessment: "GOOD" },
          { objectiveId: "obj_cost", objective: "Monthly infrastructure cost delta", direction: "MINIMIZE", value: "+18", unit: "USD", assessment: "NEUTRAL" },
          { objectiveId: "obj_rollback", objective: "Rollback exposure", direction: "MINIMIZE", value: "45", unit: "min at risk", assessment: "BAD" },
        ],
        paretoFront: true,
      },
    },
    {
      id: "cand_003",
      name: "Rewrite the order-processing core in Rust",
      subgraphReplacement: {
        boundary: "order-service runtime (language/runtime swap)",
        removes: ["order"],
        adds: [{ id: "order_rs", label: "order-service (Rust)", kind: "SERVICE" }],
        boundaryInvariants: [
          "order API contract unchanged",
          "audit-trail events identical in kind",
        ],
      },
      effects: [
        {
          onObjective: "p95_order_acceptance_ms",
          description: "Vendor-claimed ~25% latency reduction; no intervention evidence for this codebase.",
          direction: "UNCERTAIN",
        },
      ],
      costs: [
        { description: "Rewrite + team ramp", magnitude: "HIGH", quantifier: "~6 months, whole team" },
        { description: "Additional build/test infra", magnitude: "MEDIUM", quantifier: "~$120/month" },
      ],
      risks: [
        {
          description: "Behavioral drift during rewrite (ordering, retries, idempotency)",
          likelihood: "HIGH",
          severity: "HIGH",
          mitigation: "None credible within budget; equivalence checking is unpaid work.",
        },
        {
          description: "Audit-trail continuity during migration",
          likelihood: "MEDIUM",
          severity: "HIGH",
          mitigation: "Dual-run logging — doubles cost.",
        },
      ],
      constraints: [
        {
          constraint: "Monthly free-tier budget envelope",
          compliance: "VIOLATED",
          note: "Blows the soft budget envelope by an order of magnitude.",
        },
        {
          constraint: "Prefer config-first changes while evidence is weak",
          compliance: "VIOLATED",
          note: "Structural rewrite with zero codebase-specific intervention evidence.",
        },
      ],
      evidenceRefs: [],
      reversibility: {
        level: "IRREVERSIBLE",
        rollbackPath: "No practical rollback once the rewrite replaces the core.",
        notes: "Violates the reversibility preference outright.",
      },
      evaluation: {
        objectives: [
          { objectiveId: "obj_failure_rate", objective: "Deployment failure rate", direction: "MINIMIZE", value: "unknown", unit: "%", assessment: "UNKNOWN" },
          { objectiveId: "obj_p95", objective: "p95 order-acceptance latency", direction: "MINIMIZE", value: "310 (claimed)", unit: "ms", assessment: "NEUTRAL" },
          { objectiveId: "obj_cost", objective: "Monthly infrastructure cost delta", direction: "MINIMIZE", value: "+120", unit: "USD", assessment: "BAD" },
          { objectiveId: "obj_rollback", objective: "Rollback exposure", direction: "MINIMIZE", value: "n/a", unit: "min at risk", assessment: "BAD" },
        ],
        paretoFront: false,
      },
    },
  ],

  assuranceRuns: [
    {
      id: "assur_001",
      candidateId: "cand_001",
      checks: [
        {
          id: "chk_1",
          name: "Build from exact revision",
          status: "SUCCESS",
          detail: "Reproducible build from a1b2c3d…, artifacts content-addressed.",
        },
        {
          id: "chk_2",
          name: "Unit + integration suites",
          status: "SUCCESS",
          detail: "312/312 green at the exact revision (ev_004).",
        },
        {
          id: "chk_3",
          name: "Shadow replay (24h)",
          status: "SUCCESS",
          detail: "99.2% behavioral match vs production traffic.",
        },
        {
          id: "chk_4",
          name: "Rollback drill",
          status: "FAILED",
          detail: "Drill failed (ev_005): revert step timed out on legacy-reports dependency. Promotion blocked until remediated.",
        },
        {
          id: "chk_5",
          name: "Blast-radius containment",
          status: "SUCCESS",
          detail: "Canary cohort capped at 5%, single region.",
        },
        {
          id: "chk_6",
          name: "Audit-trail preservation",
          status: "SUCCESS",
          detail: "Every canary action and revert emits an audit event.",
        },
      ],
      verdict: "CONDITIONAL_PASS",
      verdictNote:
        "Conditioned on rollback-drill remediation (check 4 FAILED). The canary EXPERIMENT may proceed because its own auto-revert is bounded; PROMOTION is blocked.",
    },
  ],

  decisions: [
    {
      id: "dec_001",
      action: "EXPERIMENT",
      candidateId: "cand_001",
      candidateName: "Canary + auto-rollback gate",
      createdAt: "2026-10-02T14:05:00Z",
      status: "EXECUTED",
      rationale:
        "Evidence supports a bounded experiment: telemetry shows a 3.2% failure rate (mission shortfall), the shadow replay matched production, and the change is fully reversible. The rollback-drill FAILURE blocks promotion — not the experiment stage, whose own auto-revert is bounded and audited.",
      evidenceRefs: ["ev_006", "ev_010", "ev_005", "ev_004"],
      authoritySnapshot: {
        principal: "user_owner",
        autonomy: "EXPERIMENT allowed for bounded, reversible changes (canary cohort ≤ 5%)",
        constraints: ["no unrevertable changes", "PCI boundary", "audit trail on every action"],
      },
      expectedImpact:
        "Deployment failure rate est. 3.2% → ~1.4% on gated trains; p95 latency unaffected.",
      risk: {
        level: "LOW",
        summary: "Rollback controller misbehavior contained by shadow-first rollout and cohort cap.",
      },
      blastRadius: {
        level: "LOW",
        description: "5% of deploy traffic, one region; auto-revert within 2 minutes.",
      },
      reversibility: "Fully reversible — revert pipeline configuration; no data migration.",
      requiredApprovals: [
        { approver: "user_owner", scope: "experiment.start (canary ≤ 5%)", state: "GRANTED" },
      ],
    },
    {
      id: "dec_002",
      action: "ASK",
      candidateId: "cand_002",
      candidateName: "Inventory reservation extraction",
      createdAt: "2026-10-03T09:47:00Z",
      status: "AWAITING_OWNER",
      rationale:
        "Autonomy policy does not justify autonomous action: the intervention is partially reversible, carries a HIGH-severity migration risk, strains the budget constraint, and rests on observational evidence only. The mission owner must weigh the latency objective against the budget/reversibility trade-offs. An earlier ACT request on this candidate was DENIED (auth_002).",
      evidenceRefs: ["ev_002", "ev_011"],
      authoritySnapshot: {
        principal: "user_owner",
        autonomy: "ASK required: partial reversibility + HIGH severity risk + budget constraint judgment",
        constraints: ["budget envelope is a soft constraint owned by the mission authority"],
      },
      expectedImpact:
        "If approved and validated: p95 latency est. 412 → ~340 ms at peak; +$18/month; migration risk during cutover.",
      risk: {
        level: "MEDIUM",
        summary: "Migration consistency risk (HIGH severity, MEDIUM likelihood), mitigated by bounded dual-write.",
      },
      blastRadius: {
        level: "MEDIUM",
        description: "Order-acceptance path for all customers during the cutover window.",
      },
      reversibility: "Partially reversible — service revert is clean, data rollback requires back-fill.",
      requiredApprovals: [
        { approver: "user_owner", scope: "experiment.approve (shadow, then decide)", state: "PENDING" },
      ],
      askPayload: {
        decision:
          "Approve a shadow EXPERIMENT of the inventory-reservation extraction, defer for more evidence, or reject the candidate.",
        alternatives: [
          {
            label: "A. Approve shadow experiment",
            expectedOutcome:
              "Intervention evidence for the latency claim with zero production exposure; decision data within ~1 week.",
            tradeoffs: ["~8 engineer-weeks of build", "+$18/month shadow infra", "migration design effort now"],
          },
          {
            label: "B. Defer — gather more evidence first",
            expectedOutcome:
              "Add reservation-path tracing; re-measure contention before committing to structure.",
            tradeoffs: ["2–3 weeks delay", "no causal evidence until a later experiment", "p95 risk persists meanwhile"],
          },
          {
            label: "C. Reject the extraction",
            expectedOutcome: "Keep the current topology; rely on the canary candidate (C1) for the failure-rate goal.",
            tradeoffs: ["p95 objective stays at risk (412 ms vs 400 ms SLO)", "no structural debt added"],
          },
        ],
        evidenceQuality: {
          grade: "MODERATE",
          note: "One observational runtime study (sampled 10%); no intervention evidence for this codebase.",
        },
        uncertainty:
          "Reservation-lock contention is measured indirectly; seasonal-peak behavior unmeasured; migration failure modes unquantified.",
        tradeoffs: [
          "latency gain vs budget envelope",
          "structural change vs config-first preference",
          "intervention evidence vs 8-week build cost",
        ],
      },
    },
    {
      id: "dec_003",
      action: "GATHER_EVIDENCE",
      candidateId: "cand_001",
      candidateName: "Canary + auto-rollback gate",
      createdAt: "2026-10-01T23:10:00Z",
      status: "EXECUTED",
      rationale:
        "The rollback drill FAILED (ev_005). Before promotion is even discussable, the drill failure must be reproduced with diagnostics and a remediation re-run recorded as evidence.",
      evidenceRefs: ["ev_005"],
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "Evidence gathering allowed within the workspace read/observe budget.",
        constraints: ["no production mutations from an evidence-gathering job"],
      },
      expectedImpact: "A remediated drill result re-establishes the promotion precondition.",
      risk: { level: "LOW", summary: "Read-only diagnostics plus a sandboxed drill re-run." },
      blastRadius: { level: "LOW", description: "Sandboxed drill environment only." },
      reversibility: "No state changed — not applicable (read + sandbox).",
      requiredApprovals: [],
    },
    {
      id: "dec_004",
      action: "REJECT",
      candidateId: "cand_003",
      candidateName: "Rust rewrite of order core",
      createdAt: "2026-09-30T11:22:00Z",
      status: "EXECUTED",
      rationale:
        "Dominated on cost and reversibility, violates the budget envelope and the config-first preference, and rests on zero codebase-specific evidence. No plausible objective-weighting rescues it.",
      evidenceRefs: [],
      authoritySnapshot: {
        principal: "user_owner",
        autonomy: "REJECT within granted autonomy (no action, purely advisory candidate lifecycle)",
        constraints: ["budget envelope", "reversibility preference"],
      },
      expectedImpact: "None — the candidate is retired from the active set.",
      risk: { level: "LOW", summary: "No runtime risk; only opportunity cost of the claimed latency gain." },
      blastRadius: { level: "LOW", description: "None — no change is made." },
      reversibility: "Not applicable — rejection takes no action.",
      requiredApprovals: [],
    },
    {
      id: "dec_005",
      action: "ROLLBACK",
      candidateId: "cand_001",
      candidateName: "queue-timeout-8s-dlq (prior intervention)",
      createdAt: "2026-09-20T09:12:00Z",
      status: "EXECUTED",
      rationale:
        "The queue-consumer timeout change surfaced duplicate shipments (an unpredicted effect). The trusted rollback path dominated the untrusted candidate behavior: revert first, learn, then re-propose with an idempotency guard.",
      evidenceRefs: ["ev_010", "ev_002"],
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "ROLLBACK always within authority — the safety path outranks optimization",
        constraints: ["every live change has a tested rollback path"],
      },
      expectedImpact:
        "Duplicate-shipment exposure ended; p95 regressed by the measured 22 ms improvement gained.",
      risk: { level: "LOW", summary: "Rollback is the safety action; risk is bounded by design." },
      blastRadius: { level: "LOW", description: "queue-worker cohort only; no customer-facing interface change." },
      reversibility: "The rollback itself is the recovery path; re-applying the change requires a new governed candidate.",
      requiredApprovals: [],
    },
    {
      id: "dec_006",
      action: "ACT",
      candidateId: "cand_001",
      candidateName: "queue-consumer concurrency 4 → 6 (config-only)",
      createdAt: "2026-10-04T08:15:00Z",
      status: "EXECUTED",
      rationale:
        "Low-impact, fully reversible configuration change within the granted autonomy policy: low confidence does not always imply inaction — low-impact reversible changes may act, high-impact ones ask.",
      evidenceRefs: ["ev_002", "ev_006"],
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "ACT allowed for config-only, reversible changes with bounded blast radius",
        constraints: ["no structural change", "audit event on every mutation"],
      },
      expectedImpact: "Queue depth under peak reduced; p95 order-acceptance expected to improve marginally.",
      risk: { level: "LOW", summary: "Concurrency ceiling is config-revertible within minutes." },
      blastRadius: { level: "LOW", description: "queue-worker pool; no interface or data-store change." },
      reversibility: "Fully reversible — revert the configuration value.",
      requiredApprovals: [],
    },
  ],

  authorizations: [
    {
      id: "auth_001",
      decisionId: "dec_001",
      principal: "user_owner",
      scope: "experiment.start (canary ≤ 5%)",
      decision: "GRANTED",
      createdAt: "2026-10-02T14:00:00Z",
    },
    {
      id: "auth_002",
      principal: "user_owner",
      scope: "act.production (inventory extraction cutover)",
      decision: "DENIED",
      createdAt: "2026-09-28T10:30:00Z",
    },
  ],

  experiments: [
    {
      id: "exp_001",
      candidateId: "cand_001",
      candidateName: "Canary + auto-rollback gate",
      status: "CANARY",
      events: [
        {
          id: "exp_001_ev_1",
          at: "2026-10-02T14:10:00Z",
          kind: "PROPOSED",
          label: "Experiment proposed",
          detail: "Bounded canary experiment for cand_001; authorization granted (auth_001).",
        },
        {
          id: "exp_001_ev_2",
          at: "2026-10-02T14:20:00Z",
          kind: "ANALYZED",
          label: "Analysis complete",
          detail: "Blast-radius model: 5% cohort, one region, 2-minute auto-revert.",
        },
        {
          id: "exp_001_ev_3",
          at: "2026-10-02T15:00:00Z",
          kind: "ASSURED",
          label: "Assurance run recorded",
          detail: "assur_001 verdict CONDITIONAL_PASS (drill check FAILED — promotion blocked, experiment allowed).",
          status: "FAILED",
        },
        {
          id: "exp_001_ev_4",
          at: "2026-10-02T16:30:00Z",
          kind: "TESTED",
          label: "Suites green at exact revision",
          detail: "Integration suite 312/312 (ev_004).",
          status: "SUCCESS",
        },
        {
          id: "exp_001_ev_5",
          at: "2026-10-02T22:00:00Z",
          kind: "REPLAYED",
          label: "Shadow replay 24h",
          detail: "99.2% behavioral match (ev_010 precedent methodology).",
          status: "SUCCESS",
        },
        {
          id: "exp_001_ev_6",
          at: "2026-10-03T10:00:00Z",
          kind: "CANARY",
          label: "Canary stage entered (5% cohort)",
          detail: "Canary window opened; no eligible deployments yet — analysis window EMPTY so far (ev_011), canary health UNKNOWN until first traffic.",
          status: "UNKNOWN",
        },
      ],
    },
  ],

  executions: [
    {
      id: "exec_001",
      experimentId: "exp_001",
      provider: "DEMO",
      requestHash: "sha256:1f2a4c7b3e9d0a5f8c6b2d4e7a9f0c3b5d8e1a4f7c2b9e0d6a3f5c8b1e4d7a0",
      receipt: {
        provider: "DEMO",
        demo: true,
        runId: "run_demo_aurora_canary_001",
        completedAt: "2026-10-03T10:04:00Z",
        summary:
          "DemoProvider simulated the canary orchestration (cohort cap, health sampling schedule). No real infrastructure was touched.",
      },
      artifactRefs: [
        {
          name: "canary-run.log",
          signedUrl: "/demo/artifacts/exec_001-canary-run.log?sig=demo-signature&expires=2026-10-31",
          mediaType: "text/plain",
          sizeBytes: 6120,
        },
        {
          name: "canary-metrics.csv",
          signedUrl: "/demo/artifacts/exec_001-canary-metrics.csv?sig=demo-signature&expires=2026-10-31",
          mediaType: "text/csv",
          sizeBytes: 9421,
        },
      ],
      status: "SUCCESS",
    },
    {
      id: "exec_002",
      jobId: "job_rec_notification_001",
      provider: "APIFY",
      requestHash: "sha256:9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b",
      receipt: undefined,
      artifactRefs: [],
      status: "UNKNOWN",
    },
  ],

  jobs: [
    {
      id: "job_rec_fulfillment_001",
      tenantId: "ws_aurora_demo",
      type: "ARCHITECTURE_RECOVERY",
      requestedBy: "user_operator",
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "recovery jobs allowed (read-only source analysis)",
        constraints: ["no source mutations"],
      },
      inputHash: "sha256:0e1d2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d",
      sourceRevision: "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678",
      provider: "GITHUB",
      status: "COMPLETED",
      startedAt: "2026-09-24T10:55:00Z",
      completedAt: "2026-09-24T11:03:00Z",
      receipt: {
        provider: "GITHUB",
        demo: true,
        runId: "run_demo_recovery_fulfillment",
        completedAt: "2026-09-24T11:03:00Z",
        summary: "Demo recovery receipt: 9 nodes, 11 edges recovered and validated.",
      },
      artifactRefs: [
        {
          name: "architecture-graph.json",
          signedUrl: "/demo/artifacts/job_rec_fulfillment_001-graph.json?sig=demo-signature&expires=2026-10-31",
          mediaType: "application/json",
          sizeBytes: 17422,
        },
      ],
      errorState: null,
    },
    {
      id: "job_rec_notification_001",
      tenantId: "ws_aurora_demo",
      type: "ARCHITECTURE_RECOVERY",
      requestedBy: "user_operator",
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "recovery jobs allowed (read-only source analysis)",
        constraints: ["no source mutations"],
      },
      inputHash: "sha256:1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091",
      sourceRevision: "b2c3d4e5f60718293a4b5c6d7e8f90123456789a",
      provider: "APIFY",
      status: "RUNNING",
      startedAt: "2026-10-02T13:05:00Z",
      completedAt: null,
      receipt: undefined,
      artifactRefs: [],
      errorState: null,
    },
    {
      id: "job_rec_legacy_001",
      tenantId: "ws_aurora_demo",
      type: "ARCHITECTURE_RECOVERY",
      requestedBy: "user_operator",
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "recovery jobs allowed (read-only source analysis)",
        constraints: ["no source mutations"],
      },
      inputHash: "sha256:2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2b",
      sourceRevision: "c3d4e5f60718293a4b5c6d7e8f90123456789ab",
      provider: "GITHUB",
      status: "FAILED",
      startedAt: "2026-09-26T15:12:00Z",
      completedAt: "2026-09-26T15:20:00Z",
      receipt: undefined,
      artifactRefs: [],
      errorState: {
        code: "VALIDATION",
        message: "Recovered graph inconsistent: 2 edges reference missing nodes.",
        details: { edges: ["e_31", "e_47"], missingNodes: ["node_report_scheduler"] },
      },
    },
    {
      id: "job_rec_partner_edge_001",
      tenantId: "ws_aurora_demo",
      type: "ARCHITECTURE_RECOVERY",
      requestedBy: "user_operator",
      authoritySnapshot: {
        principal: "user_operator",
        autonomy: "recovery jobs allowed (read-only source analysis)",
        constraints: ["no source mutations"],
      },
      inputHash: "sha256:3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c",
      sourceRevision: "unknown",
      provider: "DEMO",
      status: "COMPLETED",
      startedAt: "2026-10-01T09:00:00Z",
      completedAt: "2026-10-01T09:02:00Z",
      receipt: {
        provider: "DEMO",
        demo: true,
        runId: "run_demo_partner_edge_probe",
        completedAt: "2026-10-01T09:02:00Z",
        summary: "Source probe completed: kind OTHER (GitLab) — recovery unsupported for this source.",
      },
      artifactRefs: [],
      errorState: {
        code: "PROVIDER_UNAVAILABLE",
        message: "No adapter supports source kind OTHER for architecture recovery.",
        details: { sourceKind: "OTHER", url: "https://gitlab.com/aurora-demo/partner-edge-sync" },
      },
    },
  ],

  learningRecords: [
    {
      id: "learn_001",
      context:
        "Prior intervention — queue-consumer timeout tuning (30s → 8s + DLQ), September 2026, fulfillment-platform",
      candidate: "queue-timeout-8s-dlq",
      predictedEffects: [
        "p95 order-acceptance latency improves ~40 ms",
        "failed-order retries drop by half",
      ],
      actualEffects: [
        "p95 improved 22 ms (under-predicted; contention elsewhere)",
        "retries dropped as predicted",
        "unpredicted: duplicate shipments surfaced (retry + DLQ interaction) — rolled back 2026-09-20 (dec_005)",
      ],
      uncertainty: "Single release train; seasonal load not exercised — MODERATE.",
      verdict: "PARTIALLY_CONFIRMED",
      lessons: [
        "Timeout changes have emergent duplicate-order behavior — pair with an idempotency check before shipping.",
        "Shadow replay under-predicted retry storms; include synthetic retry pressure in future replays.",
        "Latency gains moved elsewhere in the path; always re-measure the full order path, not the tuned component.",
      ],
    },
  ],

  memoryEntries: [
    {
      id: "mem_001",
      context:
        "Architecture memory — fulfillment-platform deploy path under canary candidate C1 (running)",
      candidate: "cand_001 (canary + auto-rollback gate)",
      predictedEffects: [
        "deployment failure rate 3.2% → ~1.4%",
        "auto-revert keeps failure exposure ≤ 2 minutes",
      ],
      actualEffects: [],
      uncertainty: "HIGH until the canary window produces its first eligible deployment (window currently EMPTY).",
      verdict: "PENDING",
      lessons: [
        "Prior canary-style change on this codebase: shadow match 99.2% predicted, actual match 99.2% — replay fidelity is good here.",
        "Rollback drill previously FAILED on legacy-reports dependency — do not assume revert paths; drill them.",
      ],
    },
  ],

  activity: [
    {
      id: "act_016",
      actor: "user_operator",
      action: "rollback.executed",
      target: "queue-timeout-8s-dlq",
      timestamp: "2026-09-20T09:12:00Z",
      meta: { reason: "duplicate shipments surfaced", decision: "dec_005", action: "ROLLBACK" },
    },
    {
      id: "act_001",
      actor: "user_owner",
      action: "mission.proposed",
      target: "mrev_aurora_002",
      timestamp: "2026-09-21T14:00:00Z",
      meta: { revision: "2", change: "added latency + reversibility goals" },
    },
    {
      id: "act_002",
      actor: "user_owner",
      action: "mission.approved",
      target: "mrev_aurora_002",
      timestamp: "2026-09-21T16:40:00Z",
      meta: { decidedBy: "user_owner", state: "APPROVED" },
    },
    {
      id: "act_003",
      actor: "user_operator",
      action: "system.onboarded",
      target: "sys_fulfillment",
      timestamp: "2026-09-24T10:55:00Z",
      meta: { mode: "BROWNFIELD", source: "github.com/aurora-demo/fulfillment-platform" },
    },
    {
      id: "act_004",
      actor: "job:job_rec_fulfillment_001",
      action: "recovery.completed",
      target: "sys_fulfillment",
      timestamp: "2026-09-24T11:03:00Z",
      meta: { nodes: "9", edges: "11", status: "SUCCESS" },
    },
    {
      id: "act_005",
      actor: "job:job_rec_legacy_001",
      action: "recovery.failed",
      target: "sys_legacy_reports",
      timestamp: "2026-09-26T15:20:00Z",
      meta: { error: "VALIDATION", detail: "inconsistent graph" },
    },
    {
      id: "act_015",
      actor: "system",
      action: "learning.recorded",
      target: "learn_001",
      timestamp: "2026-09-29T10:00:00Z",
      meta: { verdict: "PARTIALLY_CONFIRMED" },
    },
    {
      id: "act_007",
      actor: "user_owner",
      action: "candidate.rejected",
      target: "cand_003",
      timestamp: "2026-09-30T11:22:00Z",
      meta: { decision: "dec_004", action: "REJECT" },
    },
    {
      id: "act_006",
      actor: "system",
      action: "evidence.ingested",
      target: "ev_005",
      timestamp: "2026-09-30T18:40:00Z",
      meta: { kind: "test_result", status: "FAILED" },
    },
    {
      id: "act_008",
      actor: "system",
      action: "candidate.proposed",
      target: "cand_001",
      timestamp: "2026-10-01T09:30:00Z",
      meta: { source: "search: deploy-path optimization" },
    },
    {
      id: "act_009",
      actor: "system",
      action: "assurance.recorded",
      target: "assur_001",
      timestamp: "2026-10-02T13:50:00Z",
      meta: { verdict: "CONDITIONAL_PASS", failedChecks: "1" },
    },
    {
      id: "act_011",
      actor: "user_owner",
      action: "authorization.granted",
      target: "auth_001",
      timestamp: "2026-10-02T14:00:00Z",
      meta: { scope: "experiment.start (canary ≤ 5%)" },
    },
    {
      id: "act_010",
      actor: "system",
      action: "decision.raised",
      target: "dec_001",
      timestamp: "2026-10-02T14:05:00Z",
      meta: { action: "EXPERIMENT", candidate: "cand_001" },
    },
    {
      id: "act_014",
      actor: "system",
      action: "decision.raised",
      target: "dec_002",
      timestamp: "2026-10-03T09:47:00Z",
      meta: { action: "ASK", candidate: "cand_002", state: "AWAITING_OWNER" },
    },
    {
      id: "act_012",
      actor: "system",
      action: "experiment.stage",
      target: "exp_001",
      timestamp: "2026-10-03T10:00:00Z",
      meta: { stage: "CANARY", cohort: "5%" },
    },
    {
      id: "act_013",
      actor: "provider:DEMO",
      action: "execution.receipt",
      target: "exec_001",
      timestamp: "2026-10-03T10:04:00Z",
      meta: { demo: "true", runId: "run_demo_aurora_canary_001" },
    },
    {
      id: "act_017",
      actor: "system",
      action: "decision.raised",
      target: "dec_006",
      timestamp: "2026-10-04T08:15:00Z",
      meta: { action: "ACT", autonomy: "granted (config-only, reversible)" },
    },
    {
      id: "act_018",
      actor: "user_operator",
      action: "decision.executed",
      target: "dec_006",
      timestamp: "2026-10-04T08:20:00Z",
      meta: { action: "ACT", change: "queue-consumer concurrency 4→6" },
    },
  ],

  health: {
    status: "ok",
    checks: [
      { name: "persistence", status: "SUCCESS", detail: "Demo fixtures (no backend configured)." },
      { name: "coordination", status: "SUCCESS", detail: "Demo fixtures (no backend configured)." },
      { name: "artifacts", status: "SUCCESS", detail: "Demo fixture artifact refs." },
      { name: "execution", status: "SUCCESS", detail: "DemoProvider simulated receipts." },
    ],
  },
};
