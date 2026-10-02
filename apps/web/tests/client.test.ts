import { describe, expect, test, afterEach } from "bun:test";
import { endpoints, withQuery } from "@/lib/api/endpoints";
import { ApiError, isApiErrorEnvelope } from "@/lib/api/errors";
import { buildUrl, createSosClient, parseErrorEnvelope, resolveRuntime } from "@/lib/api/client";
import { API_ERROR_CODES, TRUTH_STATES } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Endpoint map — the directive §7 surface
// ---------------------------------------------------------------------------

describe("endpoint map (directive §7)", () => {
  test("health endpoint", () => {
    expect(endpoints.health()).toBe("/api/v1/health");
  });

  test("resource endpoints are relative /api/v1 paths", () => {
    const paths = [
      endpoints.me(),
      endpoints.workspaces(),
      endpoints.workspace("w1"),
      endpoints.missions(),
      endpoints.mission("m1"),
      endpoints.missionRevisions("m1"),
      endpoints.systems(),
      endpoints.system("s1"),
      endpoints.systemRecovery("s1"),
      endpoints.evidence(),
      endpoints.hypotheses(),
      endpoints.candidates(),
      endpoints.assurance(),
      endpoints.decisions(),
      endpoints.authorizations(),
      endpoints.experiments(),
      endpoints.experiment("e1"),
      endpoints.executions(),
      endpoints.execution("x1"),
      endpoints.learning(),
      endpoints.memory(),
      endpoints.jobs(),
      endpoints.job("j1"),
      endpoints.providers(),
    ];
    for (const path of paths) {
      expect(path.startsWith("/api/v1/")).toBe(true);
      expect(path.includes("://")).toBe(false); // never absolute
    }
  });

  test("withQuery appends only present params", () => {
    expect(withQuery("/api/v1/evidence", { kind: undefined, status: null, systemId: "" })).toBe(
      "/api/v1/evidence",
    );
    expect(withQuery("/api/v1/evidence", { kind: "telemetry", cursor: "abc" })).toBe(
      "/api/v1/evidence?kind=telemetry&cursor=abc",
    );
  });
});

// ---------------------------------------------------------------------------
// Runtime resolution (fixture mode vs API mode)
// ---------------------------------------------------------------------------

describe("client runtime resolution", () => {
  test("no config and no env → fixture demo mode", () => {
    const runtime = resolveRuntime();
    expect(runtime.mode).toBe("fixtures");
    expect(runtime.demo).toBe(true);
    expect(runtime.apiBase).toBe("");
  });

  test("forced fixtures wins", () => {
    const runtime = resolveRuntime({ forceFixtures: true });
    expect(runtime.mode).toBe("fixtures");
  });

  test("explicit api base → api mode with normalized base", () => {
    expect(resolveRuntime({ apiBase: "/custom/base" })).toEqual({
      mode: "api",
      apiBase: "/custom/base",
      demo: false,
    });
    expect(resolveRuntime({ apiBase: "/trailing/" }).apiBase).toBe("/trailing");
  });

  test("empty api base means same-origin (relative /api/v1 paths)", () => {
    const runtime = resolveRuntime({ apiBase: "" });
    expect(runtime.mode).toBe("api");
    expect(runtime.apiBase).toBe("");
    expect(buildUrl(runtime, endpoints.candidates())).toBe("/api/v1/candidates");
  });

  test("buildUrl joins base and path relatively", () => {
    const runtime = resolveRuntime({ apiBase: "/custom" });
    expect(buildUrl(runtime, "/api/v1/evidence")).toBe("/custom/api/v1/evidence");
    expect(buildUrl(runtime, "evidence")).toBe("/custom/evidence");
  });
});

// ---------------------------------------------------------------------------
// Error envelope
// ---------------------------------------------------------------------------

describe("error envelope", () => {
  test("parses a contract envelope into ApiError", () => {
    const envelope = {
      error: { code: "FORBIDDEN", message: "tenant isolation", details: { workspace: "w1" } },
    };
    expect(isApiErrorEnvelope(envelope)).toBe(true);
    const error = parseErrorEnvelope(envelope);
    expect(error).toBeInstanceOf(ApiError);
    expect(error?.code).toBe("FORBIDDEN");
    expect(error?.message).toBe("tenant isolation");
    expect(error?.details).toEqual({ workspace: "w1" });
  });

  test("rejects non-envelope payloads", () => {
    expect(isApiErrorEnvelope(null)).toBe(false);
    expect(isApiErrorEnvelope({})).toBe(false);
    expect(isApiErrorEnvelope({ error: { code: 5 } })).toBe(false);
    expect(parseErrorEnvelope({ ok: true })).toBeNull();
  });

  test("the eight contract error codes are exactly the enum", () => {
    expect(API_ERROR_CODES).toEqual([
      "UNAUTHENTICATED",
      "FORBIDDEN",
      "NOT_FOUND",
      "VALIDATION",
      "CONFLICT",
      "RATE_LIMITED",
      "PAYLOAD_TOO_LARGE",
      "PROVIDER_UNAVAILABLE",
    ]);
  });

  test("the six truth states are exactly the frozen enum", () => {
    expect(TRUTH_STATES).toEqual([
      "SUCCESS",
      "EMPTY",
      "FAILED",
      "UNKNOWN",
      "UNSUPPORTED",
      "UNAVAILABLE",
    ]);
  });
});

// ---------------------------------------------------------------------------
// Fixture-mode client behavior
// ---------------------------------------------------------------------------

describe("fixture-mode client", () => {
  test("serves the demo dataset through the typed contract", async () => {
    const client = createSosClient({ forceFixtures: true });
    expect(client.runtime.mode).toBe("fixtures");

    const workspaces = await client.listWorkspaces();
    expect(workspaces.items.length).toBe(1);
    expect(workspaces.nextCursor).toBeNull();
    expect(workspaces.items[0]?.slug).toBe("aurora-fulfillment-demo");

    const mission = await client.getMission(workspaces.items[0]!.id);
    expect(mission.status).toBe("ACTIVE");

    const revisions = await client.listMissionRevisions(mission.id);
    expect(revisions.items.length).toBe(2);
    const approved = revisions.items.find((r) => r.id === mission.currentRevisionId);
    expect(approved?.approval.state).toBe("APPROVED");

    const systems = await client.listSystems();
    expect(systems.items.length).toBeGreaterThanOrEqual(3);

    const graph = await client.getArchitectureGraph(systems.items[0]!.id);
    expect(graph.nodes.length).toBeGreaterThan(0);
    expect(graph.edges.length).toBeGreaterThan(0);

    const decisions = await client.listDecisions();
    const ask = decisions.items.find((d) => d.action === "ASK");
    expect(ask?.askPayload).toBeDefined();
    expect(ask?.askPayload?.alternatives.length).toBeGreaterThanOrEqual(2);

    const executions = await client.listExecutions();
    const demoReceipt = executions.items.find((x) => x.provider === "DEMO")?.receipt;
    expect(demoReceipt?.demo).toBe(true);

    const health = await client.health();
    expect(["ok", "degraded"]).toContain(health.status);
  });

  test("getMission rejects unknown workspaces with NOT_FOUND", async () => {
    const client = createSosClient({ forceFixtures: true });
    const error = await client.getMission("ws_nope").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("NOT_FOUND");
  });

  test("evidence filtering by kind and status", async () => {
    const client = createSosClient({ forceFixtures: true });
    const telemetry = await client.listEvidence({ kind: "telemetry" });
    expect(telemetry.items.every((e) => e.kind === "telemetry")).toBe(true);
    const failed = await client.listEvidence({ status: "FAILED" });
    expect(failed.items.length).toBeGreaterThan(0);
    expect(failed.items.every((e) => e.status === "FAILED")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// API-mode client behavior (mocked fetch)
// ---------------------------------------------------------------------------

describe("api-mode client (mocked fetch)", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  test("fetches the endpoint with the configured base and parses the DTO", async () => {
    const calls: Array<{ url: string; init: RequestInit | undefined }> = [];
    globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      return new Response(JSON.stringify({ items: [{ id: "c1" }], nextCursor: null }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as unknown as typeof fetch;

    const client = createSosClient({ apiBase: "" });
    const candidates = await client.listCandidates();
    expect(candidates.items as Array<{ id: string }>).toEqual([{ id: "c1" }]);
    expect(calls[0]?.url).toBe("/api/v1/candidates");
    expect(calls[0]?.init?.headers).toMatchObject({ Accept: "application/json" });
  });

  test("error envelope surfaces as ApiError with the contract code", async () => {
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          error: { code: "RATE_LIMITED", message: "too many", details: null },
        }),
        { status: 429, headers: { "content-type": "application/json" } },
      )) as unknown as typeof fetch;

    const client = createSosClient({ apiBase: "/api" });
    const error = await client.listEvidence().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.code).toBe("RATE_LIMITED");
    expect(apiError.status).toBe(429);
    expect(apiError.message).toBe("too many");
  });

  test("non-envelope HTTP error keeps code null (no truth-state masquerade)", async () => {
    globalThis.fetch = (async () => new Response("boom", { status: 502 })) as unknown as typeof fetch;
    const client = createSosClient({ apiBase: "" });
    const error = await client.listDecisions().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBeNull();
    expect((error as ApiError).status).toBe(502);
  });

  test("network failure surfaces as ApiError with code null", async () => {
    globalThis.fetch = (async () => {
      throw new Error("ECONNREFUSED");
    }) as unknown as typeof fetch;
    const client = createSosClient({ apiBase: "" });
    const error = await client.listJobs().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBeNull();
    expect((error as ApiError).message).toBe("ECONNREFUSED");
  });
});
