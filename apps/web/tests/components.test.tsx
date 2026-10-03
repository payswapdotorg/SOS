import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";

import { TruthStatePill, VerdictPill } from "@/components/ui/state-pill";
import { DemoBadge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Timeline, TimelineItem } from "@/components/ui/timeline";
import { ArchitectureGraphView } from "@/components/workspace/architecture-graph";
import LandingPage from "@/app/page";
import SignInPage from "@/app/signin/page";

import { demo } from "@/lib/fixtures/demo";
import type { ArchitectureGraph, Candidate, TruthState } from "@/lib/api/types";

function render(element: React.ReactElement): string {
  return renderToStaticMarkup(element);
}

// ---------------------------------------------------------------------------
// Truth-state rendering — six distinct, honest states
// ---------------------------------------------------------------------------

describe("TruthStatePill", () => {
  const states: TruthState[] = ["SUCCESS", "EMPTY", "FAILED", "UNKNOWN", "UNSUPPORTED", "UNAVAILABLE"];

  test("all six states render, each with its own label", () => {
    for (const state of states) {
      const html = render(createElement(TruthStatePill, { state }));
      expect(html).toContain(state);
      expect(html.length).toBeGreaterThan(0);
    }
    const htmls = states.map((state) => render(createElement(TruthStatePill, { state })));
    expect(new Set(htmls).size).toBe(6); // visually distinct renderings
  });

  test("a FAILED state never renders success styling", () => {
    const failed = render(createElement(TruthStatePill, { state: "FAILED" }));
    expect(failed).not.toContain("emerald");
    const success = render(createElement(TruthStatePill, { state: "SUCCESS" }));
    expect(success).toContain("emerald");
  });
});

describe("VerdictPill", () => {
  test("verdicts render with human labels", () => {
    expect(render(createElement(VerdictPill, { verdict: "CONDITIONAL_PASS" }))).toContain(
      "CONDITIONAL PASS",
    );
    expect(render(createElement(VerdictPill, { verdict: "PASS" }))).toContain("PASS");
  });
});

// ---------------------------------------------------------------------------
// Honest loading / error / empty states
// ---------------------------------------------------------------------------

describe("honest states", () => {
  test("loading announces itself (aria role=status)", () => {
    const html = render(createElement(LoadingState, { label: "Loading evidence…" }));
    expect(html).toContain("Loading evidence");
    expect(html).toContain('role="status"');
  });

  test("error names the failure and never invents data", () => {
    const html = render(
      createElement(ErrorState, {
        error: new Error("ECONNREFUSED"),
        onRetry: undefined,
      }),
    );
    expect(html).toContain("Could not load this section");
    expect(html).toContain("ECONNREFUSED");
    expect(html).toContain('role="alert"');
  });

  test("empty is explicitly distinct from unknown", () => {
    const html = render(createElement(EmptyState, { title: "No evidence yet" }));
    expect(html).toContain("No evidence yet");
    expect(html).toContain("EMPTY");
    expect(html).toContain("Distinct from UNKNOWN");
  });

  test("demo badge is explicit", () => {
    expect(render(createElement(DemoBadge))).toContain("DEMO");
  });
});

// ---------------------------------------------------------------------------
// Architecture graph rendering
// ---------------------------------------------------------------------------

describe("ArchitectureGraphView", () => {
  const graph: ArchitectureGraph = demo.architectureGraphs["sys_fulfillment"]!;

  test("renders every node and edge from the graph", () => {
    const html = render(createElement(ArchitectureGraphView, { graph }));
    for (const node of graph.nodes) {
      expect(html).toContain(node.id);
    }
    for (const edge of graph.edges) {
      expect(html).toContain(edge.source);
      expect(html).toContain(edge.target);
    }
  });

  test("empty graph renders an honest message, not a fabricated topology", () => {
    const html = render(createElement(ArchitectureGraphView, { graph: { nodes: [], edges: [] } }));
    expect(html).toContain("No architecture graph");
    expect(html).toContain("honest");
  });
});

// ---------------------------------------------------------------------------
// Landing + sign-in pages (server-rendered, fixture mode)
// ---------------------------------------------------------------------------

describe("landing page", () => {
  test("product name, tagline and both entry actions render", () => {
    const html = render(createElement(LandingPage));
    expect(html).toContain("SOS");
    expect(html).toContain("Mission-governed software evolution");
    expect(html).toContain("Explore Demo");
    expect(html).toContain("Sign in with GitHub");
  });

  test("demo mode is disclosed, not hidden", () => {
    const html = render(createElement(LandingPage));
    expect(html).toContain("DEMO DATA");
  });
});

describe("sign-in page", () => {
  test("explains the OAuth flow honestly in fixture mode (PUB-04 landed)", () => {
    const html = render(createElement(SignInPage));
    expect(html).toContain("Demo mode");
    // PUB-04 landed: fixture mode now explains it needs a configured API
    // (the copy no longer says "wired in PUB-04" — the flow IS wired).
    expect(html).toContain("needs a configured API");
    expect(html).toContain("does not fake a login");
  });
});

// ---------------------------------------------------------------------------
// Workspace shell structure (sticky footer + semantic landmarks)
// ---------------------------------------------------------------------------

describe("workspace shell structure", () => {
  test("footer sticks to the bottom (mt-auto on the footer element)", async () => {
    const { SiteFooter } = await import("@/components/shell/site-footer");
    const html = render(createElement(SiteFooter));
    expect(html).toContain("<footer");
    expect(html).toContain("mt-auto");
  });

  test("workspace nav exposes the eight directive sections", async () => {
    const { WorkspaceNavStatic } = await import("@/components/shell/workspace-nav");
    const html = render(createElement(WorkspaceNavStatic));
    for (const label of [
      "Mission",
      "Systems",
      "Evidence",
      "Candidates",
      "Experiments",
      "Decisions",
      "Memory",
      "Activity",
    ]) {
      expect(html).toContain(label);
    }
  });
});

// ---------------------------------------------------------------------------
// Decision / ASK / candidate rendering through the exported views
// ---------------------------------------------------------------------------

describe("ASK renders as a first-class UI state", () => {
  test("the ASK panel shows the exact decision, alternatives and owner actions", async () => {
    const { AskPanel } = await import("@/components/workspace/decisions-view");
    const ask = demo.decisions.find((d) => d.action === "ASK")!;
    const html = render(
      createElement(AskPanel, {
        decision: ask,
        ask: {
          responses: {},
          authorizations: [],
          activity: [],
          respond: () => {},
        },
        isDemo: true,
      }),
    );
    expect(html).toContain("DECISION: ASK");
    expect(html).toContain("awaiting owner action");
    expect(html).toContain("Exact decision requested");
    expect(html).toContain(ask.askPayload!.decision);
    for (const alt of ask.askPayload!.alternatives) {
      expect(html).toContain(alt.label);
    }
    expect(html).toContain("Approve");
    expect(html).toContain("Reject");
    expect(html).toContain("Provide evidence");
    expect(html).toContain("Evidence quality");
    expect(html).toContain("Uncertainty");
  });
});

describe("decision panel shows the governing decision fields", () => {
  test("why / evidence / authority / impact / risk / blast radius / reversibility / approvals", async () => {
    const { DecisionPanel } = await import("@/components/workspace/decisions-view");
    const decision = demo.decisions.find((d) => d.action === "EXPERIMENT")!;
    const html = render(createElement(DecisionPanel, { decision, isDemo: true }));
    expect(html).toContain("DECISION: EXPERIMENT");
    expect(html).toContain("Why?");
    expect(html).toContain("Evidence");
    expect(html).toContain("Authority");
    expect(html).toContain("Expected impact");
    expect(html).toContain("Risk");
    expect(html).toContain("Blast radius");
    expect(html).toContain("Reversibility");
    expect(html).toContain("Required approvals");
  });
});

describe("candidate comparison", () => {
  test("side-by-side cards show all six trade-off dimensions and NO single score", async () => {
    const { TradeOffCard } = await import("@/components/workspace/candidates-view");
    for (const candidate of demo.candidates as Candidate[]) {
      const html = render(createElement(TradeOffCard, { candidate }));
      expect(html).toContain("mission effect");
      expect(html).toContain("cost");
      expect(html).toContain("risk");
      expect(html).toContain("constraints");
      expect(html).toContain("evidence");
      expect(html).toContain("reversibility");
      expect(html.toLowerCase()).not.toContain("ai score");
      expect(html).not.toContain('"score"');
    }
  });

  test("pareto membership is shown, dominated is labeled honestly", async () => {
    const { TradeOffCard } = await import("@/components/workspace/candidates-view");
    const onFront = demo.candidates.find((c) => c.evaluation.paretoFront)!;
    const dominated = demo.candidates.find((c) => !c.evaluation.paretoFront)!;
    expect(render(createElement(TradeOffCard, { candidate: onFront }))).toContain("Pareto front");
    expect(render(createElement(TradeOffCard, { candidate: dominated }))).toContain("dominated");
  });

  test("evaluation table renders objectives per candidate without aggregation", async () => {
    const { EvaluationTable } = await import("@/components/workspace/candidates-view");
    const html = render(
      createElement(EvaluationTable, {
        candidates: demo.candidates as Candidate[],
        objectiveOrder: demo.candidates[0]!.evaluation.objectives.map((o) => o.objectiveId),
      }),
    );
    expect(html).toContain("Multi-objective evaluation");
    expect(html).toContain("No aggregated score exists by design");
    expect(html).toContain("Pareto-front membership");
    for (const objective of demo.candidates[0]!.evaluation.objectives) {
      expect(html).toContain(objective.objective);
    }
  });
});

describe("evidence card", () => {
  test("renders provenance, timestamp, revision, related state and confidence", async () => {
    const { EvidenceCard } = await import("@/components/workspace/evidence-view");
    const item = demo.evidence[0]!;
    const html = render(createElement(EvidenceCard, { item }));
    expect(html).toContain(item.provenance);
    expect(html).toContain("Exact revision");
    expect(html).toContain("Related system state");
    expect(html).toContain("Confidence");
    if (item.artifactRef) {
      expect(html).toContain(item.artifactRef.name);
      expect(html).toContain("signed URL");
    }
  });
});

describe("execution receipt rendering", () => {
  test("demo receipt carries the explicit DEMO badge", async () => {
    const { ExecutionCard } = await import("@/components/workspace/experiments-view");
    const execution = demo.executions.find((x) => x.provider === "DEMO")!;
    const html = render(createElement(ExecutionCard, { execution }));
    expect(html).toContain("DEMO RECEIPT");
    expect(html).toContain(execution.requestHash);
    expect(html).toContain(execution.receipt!.runId);
  });

  test("running execution shows UNKNOWN honestly, without a receipt", async () => {
    const { ExecutionCard } = await import("@/components/workspace/experiments-view");
    const execution = demo.executions.find((x) => x.status === "UNKNOWN")!;
    const html = render(createElement(ExecutionCard, { execution }));
    expect(html).toContain("UNKNOWN");
    expect(html).toContain("no success is claimed");
    expect(html).not.toContain("DEMO RECEIPT");
  });
});

describe("system detail", () => {
  test("recovery states render distinctly with their truth pills", async () => {
    const { SystemSummaryRows } = await import("@/components/workspace/systems-view");
    const failedRevision = demo.systemRevisions.find((r) => r.recovery.status === "FAILED")!;
    const unknownRevision = demo.systemRevisions.find((r) => r.recovery.status === "UNKNOWN")!;
    const failed = render(createElement(SystemSummaryRows, { revision: failedRevision }));
    const unknown = render(createElement(SystemSummaryRows, { revision: unknownRevision }));
    expect(failed).toContain("FAILED");
    expect(unknown).toContain("UNKNOWN");
    expect(failed).not.toEqual(unknown);
  });
});

describe("timeline", () => {
  test("events render with timestamps and titles", () => {
    const html = render(
      createElement(
        Timeline,
        null,
        createElement(TimelineItem, {
          at: "2026-10-03T10:00:00Z",
          title: "Canary stage entered",
        }),
      ),
    );
    expect(html).toContain("<time");
    expect(html).toContain("Canary stage entered");
    expect(html).toContain("<ol");
  });
});
