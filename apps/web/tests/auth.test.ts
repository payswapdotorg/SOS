import { describe, expect, test, afterEach } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";

import {
  createSosClient,
  githubStartUrl,
  isSafeRelativePath,
  mutationHeaders,
  readCsrfToken,
  resolveRuntime,
  __resetSosClientForTests,
  CSRF_COOKIE_NAME,
} from "@/lib/api/client";
import { endpoints } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { WorkspaceNavStatic } from "@/components/shell/workspace-nav";
import SignInPage from "@/app/signin/page";

import { demo } from "@/lib/fixtures/demo";

// ---------------------------------------------------------------------------
// OAuth start URL + open-redirect guard
// ---------------------------------------------------------------------------

describe("githubStartUrl", () => {
  test("api mode: same-origin start URL with the encoded next path", () => {
    const runtime = resolveRuntime({ apiBase: "" });
    expect(githubStartUrl(runtime, "/workspace")).toBe(
      "/api/v1/auth/github/start?next=%2Fworkspace",
    );
  });

  test("custom base joins before the start path", () => {
    const runtime = resolveRuntime({ apiBase: "/custom" });
    expect(githubStartUrl(runtime, "/workspace")).toBe(
      "/custom/api/v1/auth/github/start?next=%2Fworkspace",
    );
  });

  test("an unsafe next falls back to /workspace (never an open redirect)", () => {
    const runtime = resolveRuntime({ apiBase: "" });
    expect(githubStartUrl(runtime, "https://evil.example.com")).toBe(
      "/api/v1/auth/github/start?next=%2Fworkspace",
    );
    expect(githubStartUrl(runtime, "//evil.example.com")).toBe(
      "/api/v1/auth/github/start?next=%2Fworkspace",
    );
  });
});

describe("isSafeRelativePath", () => {
  test("relative paths pass; absolute and scheme forms fail", () => {
    expect(isSafeRelativePath("/workspace")).toBe(true);
    expect(isSafeRelativePath("/workspace?ws=ws-demo")).toBe(true);
    expect(isSafeRelativePath("https://evil.example.com")).toBe(false);
    expect(isSafeRelativePath("//evil.example.com")).toBe(false);
    expect(isSafeRelativePath("\\\\evil")).toBe(false);
    expect(isSafeRelativePath("workspace")).toBe(false);
    expect(isSafeRelativePath(`/${"a".repeat(200)}`)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// CSRF double-submit helpers
// ---------------------------------------------------------------------------

describe("csrf helpers", () => {
  const realDocument = globalThis.document;

  afterEach(() => {
    // @ts-expect-error test restore
    if (realDocument === undefined) delete globalThis.document;
    else globalThis.document = realDocument;
  });

  test("readCsrfToken reads the sos_csrf cookie; null without a document", () => {
    // @ts-expect-error test stub
    globalThis.document = { cookie: `other=1; ${CSRF_COOKIE_NAME}=tok-123; x=y` };
    expect(readCsrfToken()).toBe("tok-123");
    // @ts-expect-error test stub
    globalThis.document = { cookie: "other=1" };
    expect(readCsrfToken()).toBe(null);
    // @ts-expect-error test stub
    delete globalThis.document;
    expect(readCsrfToken()).toBe(null); // SSR: no cookie access
  });

  test("mutationHeaders carries the x-sos-csrf echo when present", () => {
    // @ts-expect-error test stub
    globalThis.document = { cookie: `${CSRF_COOKIE_NAME}=tok-abc` };
    expect(mutationHeaders()).toEqual({ "x-sos-csrf": "tok-abc" });
    // @ts-expect-error test stub
    globalThis.document = { cookie: "unrelated=1" };
    expect(mutationHeaders()).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// The auth client surface — API mode against a fetch stub
// ---------------------------------------------------------------------------

function withFetchStub(responder: (url: string, init?: RequestInit) => { status: number; body: unknown }) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const { status, body } = responder(url, init);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return {
    calls,
    restore() {
      globalThis.fetch = original;
    },
  };
}

describe("auth client (api mode)", () => {
  test("session() maps the SessionDTO wire shape", async () => {
    const stub = withFetchStub(() => ({
      status: 200,
      body: {
        authenticated: true,
        user: {
          id: "user-octo-newcomer",
          githubId: "910001",
          login: "octo-newcomer",
          displayName: "Octo Newcomer",
          createdAt: "2026-10-02T00:00:00Z",
        },
        stub: false,
        provider: "fake-github",
      },
    }));
    try {
      const client = createSosClient({ apiBase: "" });
      const session = await client.session();
      expect(session.authenticated).toBe(true);
      expect(session.user?.login).toBe("octo-newcomer");
      expect(session.stub).toBe(false);
      expect(session.provider).toBe("fake-github");
      expect(stub.calls[0]?.url).toBe(endpoints.auth.session());
    } finally {
      stub.restore();
    }
  });

  test("account() returns memberships with roles", async () => {
    const stub = withFetchStub(() => ({
      status: 200,
      body: {
        authenticated: true,
        user: { id: "u1", githubId: "1", login: "alice", displayName: "A", createdAt: "t" },
        stub: false,
        provider: "github",
        workspaces: [
          {
            id: "ws-alice",
            name: "Alice Lab",
            slug: "alice-lab",
            isDemo: false,
            createdAt: "t",
            role: "owner",
          },
        ],
      },
    }));
    try {
      const client = createSosClient({ apiBase: "" });
      const account = await client.account();
      expect(account.workspaces[0]?.role).toBe("owner");
      expect(account.workspaces[0]?.id).toBe("ws-alice");
    } finally {
      stub.restore();
    }
  });

  test("logout() POSTs with the CSRF header when the cookie is present", async () => {
    // @ts-expect-error test stub
    globalThis.document = { cookie: `${CSRF_COOKIE_NAME}=tok-xyz` };
    const stub = withFetchStub(() => ({ status: 200, body: { ok: true } }));
    try {
      const client = createSosClient({ apiBase: "" });
      const result = await client.logout();
      expect(result.ok).toBe(true);
      const call = stub.calls[0];
      expect(call?.url).toBe(endpoints.auth.logout());
      expect(call?.init?.method).toBe("POST");
      expect((call?.init?.headers as Record<string, string>)["x-sos-csrf"]).toBe("tok-xyz");
    } finally {
      stub.restore();
      // @ts-expect-error test restore
      delete globalThis.document;
    }
  });

  test("createWorkspace() POSTs the JSON body + CSRF header", async () => {
    // @ts-expect-error test stub
    globalThis.document = { cookie: `${CSRF_COOKIE_NAME}=tok-create` };
    const stub = withFetchStub(() => ({
      status: 200,
      body: { id: "ws-newco-lab", name: "Newco Lab", slug: "newco-lab", createdAt: "t" },
    }));
    try {
      const client = createSosClient({ apiBase: "" });
      const workspace = await client.createWorkspace({ name: "Newco Lab", slug: "newco-lab" });
      expect(workspace.id).toBe("ws-newco-lab");
      const call = stub.calls[0];
      expect(call?.url).toBe(endpoints.workspaces());
      expect(call?.init?.method).toBe("POST");
      expect(JSON.parse(String(call?.init?.body))).toEqual({
        name: "Newco Lab",
        slug: "newco-lab",
      });
      expect((call?.init?.headers as Record<string, string>)["x-sos-csrf"]).toBe("tok-create");
    } finally {
      stub.restore();
      // @ts-expect-error test restore
      delete globalThis.document;
    }
  });

  test("me() maps the session DTO to the user (transport mapping only)", async () => {
    const stub = withFetchStub(() => ({
      status: 200,
      body: {
        authenticated: true,
        user: { id: "u1", githubId: "9", login: "bob", displayName: "B", createdAt: "t" },
        stub: false,
        provider: "github",
      },
    }));
    try {
      const client = createSosClient({ apiBase: "" });
      const user = await client.me();
      expect(user.login).toBe("bob");
      expect(stub.calls[0]?.url).toBe(endpoints.me());
    } finally {
      stub.restore();
    }
  });

  test("me() refuses an anonymous session honestly (401-style error)", async () => {
    const stub = withFetchStub(() => ({
      status: 200,
      body: { authenticated: false, user: null, stub: false, provider: "none" },
    }));
    try {
      const client = createSosClient({ apiBase: "" });
      const thrown = await client
        .me()
        .then(() => null)
        .catch((error: unknown) => error);
      expect(thrown).toBeInstanceOf(ApiError);
      expect((thrown as ApiError).code).toBe("UNAUTHENTICATED");
    } finally {
      stub.restore();
    }
  });

  test("error envelopes from the API surface as ApiError", async () => {
    const stub = withFetchStub(() => ({
      status: 409,
      body: { error: { code: "CONFLICT", message: "workspace slug 'demo' already exists", details: null } },
    }));
    try {
      const client = createSosClient({ apiBase: "" });
      const thrown = await client
        .createWorkspace({ name: "X", slug: "demo" })
        .then(() => null)
        .catch((error: unknown) => error);
      expect(thrown).toBeInstanceOf(ApiError);
      expect((thrown as ApiError).status).toBe(409);
      expect((thrown as ApiError).code).toBe("CONFLICT");
    } finally {
      stub.restore();
    }
  });
});

// ---------------------------------------------------------------------------
// The auth client surface — fixture/demo mode (honest labels)
// ---------------------------------------------------------------------------

describe("auth client (fixture mode)", () => {
  test("session/account expose the labeled demo identity", async () => {
    const client = createSosClient({ forceFixtures: true });
    const session = await client.session();
    expect(session.authenticated).toBe(true);
    expect(session.stub).toBe(true);
    expect(session.provider).toBe("local-stub");
    expect(session.user?.id).toBe(demo.users[0].id);
    const account = await client.account();
    expect(account.workspaces[0]?.isDemo).toBe(true);
    expect(account.workspaces[0]?.role).toBe("owner");
    expect(await client.logout()).toEqual({ ok: true });
  });

  test("createWorkspace refuses honestly (no server to mutate)", async () => {
    const client = createSosClient({ forceFixtures: true });
    const thrown = await client
      .createWorkspace({ name: "X", slug: "x-lab" })
      .then(() => null)
      .catch((error: unknown) => error);
    expect(thrown).toBeInstanceOf(ApiError);
    expect((thrown as ApiError).status).toBe(401);
  });
});

// ---------------------------------------------------------------------------
// Components: nav preserves the tenant selection; sign-in page states truth
// ---------------------------------------------------------------------------

describe("tenant-aware components", () => {
  test("nav links preserve the ?ws= selection", () => {
    const html = renderToStaticMarkup(
      createElement(WorkspaceNavStatic, {
        currentPath: "/workspace/systems",
        wsParam: "ws-newco-lab",
      }),
    );
    expect(html).toContain("/workspace?ws=ws-newco-lab");
    expect(html).toContain("/workspace/systems?ws=ws-newco-lab");
    expect(html).toContain("/workspace/decisions?ws=ws-newco-lab");
  });

  test("nav links without a selection stay plain", () => {
    const html = renderToStaticMarkup(
      createElement(WorkspaceNavStatic, { currentPath: "/workspace" }),
    );
    expect(html).toContain('href="/workspace/systems"');
    expect(html).not.toContain("?ws=");
  });

  test("sign-in page in fixture mode explains demo truth (no fake login)", () => {
    __resetSosClientForTests();
    const html = renderToStaticMarkup(createElement(SignInPage));
    expect(html).toContain("Demo mode");
    expect(html).toContain("does not fake a login");
    expect(html).toContain("Explore Demo");
  });

  test("sign-in page in api mode links the real OAuth start", () => {
    const original = process.env.NEXT_PUBLIC_API_BASE;
    process.env.NEXT_PUBLIC_API_BASE = "";
    __resetSosClientForTests();
    try {
      const html = renderToStaticMarkup(createElement(SignInPage));
      expect(html).toContain("/api/v1/auth/github/start?next=%2Fworkspace");
      expect(html).toContain("Continue with GitHub");
    } finally {
      if (original === undefined) delete process.env.NEXT_PUBLIC_API_BASE;
      else process.env.NEXT_PUBLIC_API_BASE = original;
      __resetSosClientForTests();
    }
  });
});
