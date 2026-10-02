import { describe, expect, test, afterEach } from "bun:test";
import {
  mapWireAuditEvent,
  mapWireGraph,
  mapWireSystemRevision,
  mapWireSystemCurrentRevision,
  type WireAuditEvent,
  type WireGraph,
  type WireSystem,
  type WireSystemRevision,
} from "@/lib/api/wire";
import { endpoints } from "@/lib/api/endpoints";
import { createSosClient } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Graph vocabulary — 1:1 with the frozen W3 wire enums
// ---------------------------------------------------------------------------

describe("wire graph vocabulary mapping (frozen W3 enums)", () => {
  test("every wire NodeType maps to exactly one UI kind (1:1, none dropped)", () => {
    const wireTypes = [
      "capability",
      "service",
      "component",
      "data_store",
      "interface",
      "deployment",
      "trust_boundary",
      "policy",
      "model",
      "adapter",
      "external_dependency",
    ];
    const graph: WireGraph = {
      nodes: wireTypes.map((type, i) => ({
        id: `n${i}`,
        type,
        name: `node-${type}`,
        attributes: { notes: `note-${type}` },
      })),
      edges: [],
    };
    const mapped = mapWireGraph(graph);
    expect(mapped.nodes.map((n) => n.kind)).toEqual([
      "CAPABILITY",
      "SERVICE",
      "COMPONENT",
      "DATA_STORE",
      "INTERFACE",
      "DEPLOYMENT",
      "TRUST_BOUNDARY",
      "POLICY",
      "MODEL",
      "ADAPTER",
      "EXTERNAL_DEPENDENCY",
    ]);
    // label carries the wire name; notes carry the wire attributes
    expect(mapped.nodes[0]?.label).toBe("node-capability");
    expect(mapped.nodes[0]?.notes).toBe("note-capability");
  });

  test("every wire EdgeType maps to exactly one UI edge kind (1:1, none dropped)", () => {
    const wireTypes = [
      "call",
      "data-flow",
      "dependency",
      "trust",
      "deployment",
      "runtime-interaction",
      "realizes",
      "observes",
      "influences",
      "owns",
      "constrains",
    ];
    const graph: WireGraph = {
      nodes: [
        { id: "a", type: "service", name: "A" },
        { id: "b", type: "service", name: "B" },
      ],
      edges: wireTypes.map((type, i) => ({
        id: `e${i}`,
        type,
        sourceId: "a",
        targetId: "b",
        attributes: { label: `label-${type}` },
      })),
    };
    const mapped = mapWireGraph(graph);
    expect(mapped.edges.map((e) => e.kind)).toEqual([
      "CALLS",
      "DATA_FLOW",
      "DEPENDS_ON",
      "TRUSTS",
      "DEPLOYS",
      "RUNTIME_INTERACTION",
      "REALIZES",
      "OBSERVES",
      "INFLUENCES",
      "OWNS",
      "CONSTRAINS",
    ]);
    expect(mapped.edges[1]?.source).toBe("a");
    expect(mapped.edges[1]?.target).toBe("b");
    expect(mapped.edges[1]?.label).toBe("label-data-flow");
  });

  test("unknown future wire kinds fall back to a display kind (never crash, never drop the node)", () => {
    const mapped = mapWireGraph({
      nodes: [{ id: "x", type: "brand-new-kind", name: "X" }],
      edges: [{ id: "y", type: "brand-new-flow", sourceId: "x", targetId: "x" }],
    });
    expect(mapped.nodes[0]?.kind).toBe("COMPONENT");
    expect(mapped.edges[0]?.kind).toBe("DEPENDS_ON");
    expect(mapped.nodes[0]?.label).toBe("X");
  });

  test("absent graph degrades to an honest empty graph (no invented topology)", () => {
    expect(mapWireGraph(null)).toEqual({ nodes: [], edges: [] });
    expect(mapWireGraph({})).toEqual({ nodes: [], edges: [] });
  });
});

// ---------------------------------------------------------------------------
// Audit events (Activity surface)
// ---------------------------------------------------------------------------

describe("wire audit event mapping", () => {
  test("ts maps to timestamp; meta values stringify without loss", () => {
    const event: WireAuditEvent = {
      id: "ae1",
      actor: "user_1",
      action: "mission.revision.approve",
      target: "mrev_1",
      meta: { count: 3, nested: { a: 1 }, plain: "text" },
      ts: "2026-10-02T03:38:47Z",
    };
    const mapped = mapWireAuditEvent(event);
    expect(mapped.timestamp).toBe("2026-10-02T03:38:47Z");
    expect(mapped.meta.count).toBe("3");
    expect(mapped.meta.plain).toBe("text");
    expect(JSON.parse(mapped.meta.nested ?? "{}")).toEqual({ a: 1 });
    expect(mapped.id).toBe("ae1");
    expect(mapped.actor).toBe("user_1");
  });

  test("missing meta degrades to an empty record", () => {
    const mapped = mapWireAuditEvent({
      id: "ae2",
      actor: "anon",
      action: "read",
      target: "evidence",
      ts: "2026-10-02T00:00:00Z",
    });
    expect(mapped.meta).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// SystemRevision mapping (honest degradation)
// ---------------------------------------------------------------------------

describe("wire system revision mapping", () => {
  const wireRevision: WireSystemRevision = {
    id: "srev_1",
    systemId: "sys_1",
    revision: 4,
    stateSummary: "modular monolith with queue workers",
    uncertainty: { state: "UNKNOWN", reason: "partially observed", confidence: 0.82 },
    sourceRef: { kind: "GITHUB_REPO", url: "https://github.com/x/y", revision: "abc123", immutable: true },
    recovery: { jobId: "job_1", status: "SUCCESS" },
    graph: {
      nodes: [
        { id: "s", type: "service", name: "svc" },
        { id: "db", type: "data_store", name: "db" },
        { id: "i", type: "interface", name: "api" },
        { id: "ext", type: "external_dependency", name: "partner" },
      ],
      edges: [{ id: "e", type: "call", sourceId: "i", targetId: "s" }],
    },
    createdAt: "2026-10-02T00:00:00Z",
  };

  test("carries the wire summary verbatim; aggregates the wire lacks are UNKNOWN", () => {
    const r = mapWireSystemRevision(wireRevision);
    expect(r.stateSummary.summary).toBe("modular monolith with queue workers");
    expect(r.stateSummary.health).toBe("UNKNOWN");
    expect(r.stateSummary.drift).toBe("UNKNOWN");
  });

  test("topology counts derive ONLY from the provided graph", () => {
    const r = mapWireSystemRevision(wireRevision);
    expect(r.stateSummary.services).toBe(1);
    expect(r.stateSummary.dataStores).toBe(1);
    // interface + external_dependency count as integrations
    expect(r.stateSummary.integrations).toBe(2);
  });

  test("uncertainty mirrors the wire shape (state/reason/confidence)", () => {
    const r = mapWireSystemRevision(wireRevision);
    expect(r.uncertainty).toEqual({ state: "UNKNOWN", reason: "partially observed", confidence: 0.82 });
  });

  test("recovery is a truth state; note is absent (wire does not carry it)", () => {
    const r = mapWireSystemRevision(wireRevision);
    expect(r.recovery).toEqual({ jobId: "job_1", status: "SUCCESS" });
    expect(r.recovery.note).toBeUndefined();
  });

  test("missing wire fields degrade truthfully (UNKNOWN, empty, false)", () => {
    const r = mapWireSystemRevision({ id: "srev_2" }, "sys_2");
    expect(r.systemId).toBe("sys_2");
    expect(r.stateSummary.health).toBe("UNKNOWN");
    expect(r.uncertainty.state).toBe("UNKNOWN");
    expect(r.uncertainty.confidence).toBeNull();
    expect(r.sourceRef.immutable).toBe(false);
    expect(r.recovery.status).toBe("UNKNOWN");
    expect(r.stateSummary.services).toBe(0);
  });

  test("non-truth-state wire status values never masquerade as one", () => {
    const r = mapWireSystemRevision({
      id: "srev_3",
      recovery: { jobId: "j", status: "SOME_FUTURE_STATE" },
    });
    expect(r.recovery.status).toBe("UNKNOWN");
  });

  test("system without a current revision maps to null (caller decides)", () => {
    const system: WireSystem = {
      id: "sys_9",
      workspaceId: "w1",
      name: "no-revision-yet",
      currentRevisionId: null,
    };
    expect(mapWireSystemCurrentRevision(system)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Endpoint map after reconciliation (no invented wire paths)
// ---------------------------------------------------------------------------

describe("endpoint map reconciled to the PUB-01 OpenAPI", () => {
  test("providers surface matches the wire path /api/v1/providers/status", () => {
    expect(endpoints.providers()).toBe("/api/v1/providers/status");
  });

  test("no invented wire paths remain in the endpoint map", () => {
    const map = endpoints as unknown as Record<string, unknown>;
    expect(map.audit).toBeUndefined(); // retired → workspace detail recentActivity
    expect(map.systemArchitecture).toBeUndefined(); // retired → revision graph
    expect(map.missionRevision).toBeUndefined(); // retired → collection narrowing
  });
});

// ---------------------------------------------------------------------------
// API-mode client uses the authoritative paths + params (mocked fetch)
// ---------------------------------------------------------------------------

describe("api-mode client hits the authoritative wire (mocked fetch)", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  function mockFetch(routes: Record<string, unknown>) {
    const calls: string[] = [];
    globalThis.fetch = (async (url: string | URL | Request) => {
      const path = String(url);
      calls.push(path);
      const key = Object.keys(routes).find((k) => path.startsWith(k));
      const body = key !== undefined ? routes[key] : { items: [], nextCursor: null };
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;
    return { calls };
  }

  test("getMission filters by workspaceId (the OpenAPI parameter name)", async () => {
    const { calls } = mockFetch({
      "/api/v1/missions": { items: [], nextCursor: null },
    });
    const client = createSosClient({ apiBase: "" });
    await client.getMission("w1").catch(() => undefined);
    expect(calls[0]).toBe("/api/v1/missions?workspaceId=w1");
  });

  test("listAssuranceRuns filters by candidateId (the OpenAPI parameter name)", async () => {
    const { calls } = mockFetch({
      "/api/v1/assurance": { items: [], nextCursor: null },
    });
    const client = createSosClient({ apiBase: "" });
    await client.listAssuranceRuns("c1");
    expect(calls[0]).toBe("/api/v1/assurance?candidateId=c1");
  });

  test("getSystemRevision fetches GET /systems/{id} and maps the current revision", async () => {
    const { calls } = mockFetch({
      "/api/v1/systems/sys_1": {
        id: "sys_1",
        workspaceId: "w1",
        name: "svc",
        currentRevisionId: "srev_1",
        currentRevision: {
          id: "srev_1",
          systemId: "sys_1",
          revision: 2,
          stateSummary: "summary text",
          graph: {
            nodes: [{ id: "n", type: "service", name: "svc" }],
            edges: [],
          },
        },
      },
    });
    const client = createSosClient({ apiBase: "" });
    const revision = await client.getSystemRevision("sys_1");
    expect(calls[0]).toBe("/api/v1/systems/sys_1"); // no invented projection param
    expect(revision.id).toBe("srev_1");
    expect(revision.stateSummary.summary).toBe("summary text");
    expect(revision.stateSummary.health).toBe("UNKNOWN"); // honest degradation
    expect(revision.stateSummary.services).toBe(1); // derived from the graph
  });

  test("getArchitectureGraph derives from the revision graph; empty when none", async () => {
    mockFetch({
      "/api/v1/systems/sys_1": { id: "sys_1", workspaceId: "w1", name: "svc" },
    });
    const client = createSosClient({ apiBase: "" });
    const graph = await client.getArchitectureGraph("sys_1");
    expect(graph).toEqual({ nodes: [], edges: [] }); // honest empty, no invented topology
  });

  test("listActivity consumes the workspace detail recentActivity (ts → timestamp)", async () => {
    const { calls } = mockFetch({
      "/api/v1/workspaces/ws_demo": {
        id: "ws_demo",
        name: "Demo",
        slug: "demo",
        createdAt: "2026-10-02T00:00:00Z",
        recentActivity: [
          { id: "a1", actor: "owner", action: "mission.approve", target: "m1", ts: "2026-10-02T01:00:00Z" },
        ],
      },
      "/api/v1/workspaces": { items: [{ id: "ws_demo", name: "Demo", slug: "demo", createdAt: "x" }], nextCursor: null },
    });
    const client = createSosClient({ apiBase: "" });
    const activity = await client.listActivity({ workspaceId: "ws_demo" });
    expect(calls[0]).toBe("/api/v1/workspaces/ws_demo");
    expect(calls).not.toContain("/api/v1/audit"); // the invented path is gone
    expect(activity.items[0]?.timestamp).toBe("2026-10-02T01:00:00Z");
    expect(activity.nextCursor).toBeNull();
  });

  test("getMissionRevision narrows the revisions collection (no invented single-resource route)", async () => {
    const { calls } = mockFetch({
      "/api/v1/missions/m1/revisions": {
        items: [
          { id: "r1", missionId: "m1" },
          { id: "r2", missionId: "m1" },
        ],
        nextCursor: null,
      },
    });
    const client = createSosClient({ apiBase: "" });
    const revision = await client.getMissionRevision("m1", "r2");
    expect(calls[0]).toBe("/api/v1/missions/m1/revisions");
    expect((revision as { id: string }).id).toBe("r2");
  });
});
