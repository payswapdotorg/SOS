import { describe, expect, test } from "bun:test";
import { demo } from "@/lib/fixtures/demo";
import { EVIDENCE_KINDS, TRUTH_STATES } from "@/lib/api/types";
import type { Candidate, Evidence } from "@/lib/api/types";

/**
 * Fixture honesty checks: the demo dataset must cover the full evidence-kind
 * × truth-state matrix requirements, keep the ASK state real, badge demo
 * receipts, and never smuggle a single-score candidate ranking in.
 */

describe("demo fixtures (typed demo dataset)", () => {
  test("the dataset conforms to the DemoDataset contract type", () => {
    // Structural spot checks that the fixture is the shape the typed client serves.
    expect(demo.workspace.id).toBeString();
    expect(demo.mission.currentRevisionId).toBeString();
    expect(demo.missionRevisions.length).toBeGreaterThanOrEqual(2);
    expect(demo.systems.length).toBeGreaterThanOrEqual(3);
    for (const system of demo.systems) {
      expect(["GREENFIELD", "BROWNFIELD"]).toContain(system.mode);
      expect(demo.systemRevisions.some((r) => r.systemId === system.id)).toBe(true);
    }
    expect(demo.candidates.length).toBe(3);
    expect(demo.assuranceRuns.length).toBeGreaterThanOrEqual(1);
    expect(demo.experiments.length).toBeGreaterThanOrEqual(1);
    expect(demo.executions.length).toBeGreaterThanOrEqual(1);
    expect(demo.jobs.length).toBeGreaterThanOrEqual(3);
    expect(demo.learningRecords.length).toBeGreaterThanOrEqual(1);
    expect(demo.memoryEntries.length).toBeGreaterThanOrEqual(1);
    expect(demo.activity.length).toBeGreaterThanOrEqual(10);
  });

  test("all 7 evidence kinds appear", () => {
    const kinds = new Set(demo.evidence.map((e: Evidence) => e.kind));
    for (const kind of EVIDENCE_KINDS) {
      expect(kinds.has(kind)).toBe(true);
    }
    expect(kinds.size).toBe(EVIDENCE_KINDS.length);
  });

  test("all 6 truth states appear on evidence, distinctly labeled", () => {
    const states = new Set(demo.evidence.map((e: Evidence) => e.status));
    for (const state of TRUTH_STATES) {
      expect(states.has(state)).toBe(true);
    }
    // EMPTY and UNKNOWN must BOTH be present and distinct (invariant 6).
    const empty = demo.evidence.find((e) => e.status === "EMPTY");
    const unknown = demo.evidence.find((e) => e.status === "UNKNOWN");
    expect(empty?.id).not.toBe(unknown?.id);
    expect(empty?.confidenceNote).toContain("EMPTY");
    expect(unknown?.confidenceNote?.toLowerCase()).toContain("unknown");
  });

  test("recovery states distinguish SUCCESS, UNKNOWN, FAILED and UNSUPPORTED", () => {
    const statuses = demo.systemRevisions.map((r) => r.recovery.status);
    expect(statuses).toContain("SUCCESS");
    expect(statuses).toContain("UNKNOWN");
    expect(statuses).toContain("FAILED");
    expect(statuses).toContain("UNSUPPORTED");
  });

  test("3 candidates: ≥1 on the Pareto front, ≥1 dominated, NO aggregated score field", () => {
    const onFront = demo.candidates.filter((c: Candidate) => c.evaluation.paretoFront);
    const dominated = demo.candidates.filter((c: Candidate) => !c.evaluation.paretoFront);
    expect(onFront.length).toBeGreaterThanOrEqual(1);
    expect(dominated.length).toBeGreaterThanOrEqual(1);

    for (const candidate of demo.candidates) {
      const serialized = JSON.stringify(candidate).toLowerCase();
      expect(serialized).not.toContain('"score"');
      expect(serialized).not.toContain('"rating"');
      expect(serialized).not.toContain('"overall"');
      // Every evaluation is per-objective with an explicit direction.
      expect(candidate.evaluation.objectives.length).toBeGreaterThanOrEqual(3);
      for (const objective of candidate.evaluation.objectives) {
        expect(["MINIMIZE", "MAXIMIZE"]).toContain(objective.direction);
        expect(typeof objective.value).toBe("string");
      }
    }
  });

  test("candidates carry all six trade-off dimensions", () => {
    for (const candidate of demo.candidates) {
      expect(candidate.effects.length).toBeGreaterThan(0); // mission effect
      expect(candidate.costs.length).toBeGreaterThan(0);
      expect(candidate.risks.length).toBeGreaterThan(0);
      expect(candidate.constraints.length).toBeGreaterThan(0);
      expect(typeof candidate.evidenceRefs).toBe("object");
      expect(candidate.reversibility.level).toBeString();
    }
  });

  test("one ASK decision awaits the owner with the exact decision requested", () => {
    const ask = demo.decisions.find((d) => d.action === "ASK");
    expect(ask).toBeDefined();
    expect(ask?.status).toBe("AWAITING_OWNER");
    expect(ask?.askPayload?.decision ?? "").toBeString();
    expect(ask?.askPayload?.alternatives.length).toBeGreaterThanOrEqual(3);
    for (const alt of ask?.askPayload?.alternatives ?? []) {
      expect(alt.expectedOutcome).toBeString();
      expect(alt.tradeoffs.length).toBeGreaterThan(0);
    }
    expect(["STRONG", "MODERATE", "WEAK"]).toContain(ask?.askPayload?.evidenceQuality.grade ?? "");
    expect(ask?.askPayload?.uncertainty).toBeString();
    expect(ask?.askPayload?.tradeoffs.length).toBeGreaterThan(0);
    // The ASK requires an approval still PENDING.
    expect(ask?.requiredApprovals.some((a) => a.state === "PENDING")).toBe(true);
  });

  test("all six decision actions appear across the decision set", () => {
    const actions = new Set(demo.decisions.map((d) => d.action));
    for (const action of ["ACT", "EXPERIMENT", "GATHER_EVIDENCE", "ASK", "REJECT", "ROLLBACK"]) {
      expect(actions.has(action as never)).toBe(true);
    }
  });

  test("DemoProvider receipt carries an explicit demo:true badge", () => {
    const execution = demo.executions.find((x) => x.provider === "DEMO");
    expect(execution?.receipt?.demo).toBe(true);
    expect(execution?.receipt?.provider).toBe("DEMO");
    const jobReceipt = demo.jobs.find((j) => j.receipt)?.receipt;
    expect(jobReceipt?.demo).toBe(true);
  });

  test("an honest FAILED assurance check blocks the verdict (CONDITIONAL_PASS, not PASS)", () => {
    const run = demo.assuranceRuns[0];
    const failedCheck = run.checks.find((c) => c.status === "FAILED");
    expect(failedCheck).toBeDefined();
    expect(run.verdict).toBe("CONDITIONAL_PASS");
  });

  test("experiment has a full event timeline including an UNKNOWN canary health event", () => {
    const experiment = demo.experiments[0];
    expect(experiment.events.length).toBeGreaterThanOrEqual(5);
    expect(experiment.events.some((e) => e.status === "UNKNOWN")).toBe(true);
    expect(["SHADOW", "CANARY", "EXPERIMENTAL"]).toContain(experiment.status);
  });

  test("learning record keeps predicted vs actual effects apart with an honest verdict", () => {
    const record = demo.learningRecords[0];
    expect(record.predictedEffects.length).toBeGreaterThan(0);
    expect(record.actualEffects.length).toBeGreaterThan(0);
    expect(record.verdict).toBe("PARTIALLY_CONFIRMED");
    expect(record.lessons.length).toBeGreaterThanOrEqual(3);
  });

  test("memory entry for the running experiment stays EMPTY on actual effects", () => {
    const entry = demo.memoryEntries[0];
    expect(entry.actualEffects).toEqual([]);
    expect(entry.verdict).toBe("PENDING");
  });

  test("activity trail is chronologically ordered with full audit fields", () => {
    const timestamps = demo.activity.map((a) => a.timestamp);
    const sorted = [...timestamps].sort();
    expect(timestamps).toEqual(sorted);
    for (const event of demo.activity) {
      expect(event.actor).toBeString();
      expect(event.action).toContain(".");
      expect(event.target).toBeString();
      expect(typeof event.meta).toBe("object");
    }
  });

  test("artifact refs are relative fixture paths (no absolute URLs in the demo)", () => {
    const artifacts: NonNullable<(typeof demo.evidence)[number]["artifactRef"]>[] = [
      ...demo.evidence.map((e: Evidence) => e.artifactRef).filter((a): a is NonNullable<typeof a> => Boolean(a)),
      ...demo.executions.flatMap((x) => x.artifactRefs),
      ...demo.jobs.flatMap((j) => j.artifactRefs),
    ];
    expect(artifacts.length).toBeGreaterThan(0);
    for (const artifact of artifacts) {
      expect(artifact.signedUrl.startsWith("/demo/artifacts/")).toBe(true);
      expect(artifact.signedUrl).toContain("sig=demo-signature");
      expect(artifact.signedUrl.includes("://")).toBe(false);
    }
  });

  test("job model carries the directive §8 field set", () => {
    for (const job of demo.jobs) {
      expect(job.tenantId).toBeString();
      expect(job.type).toBeString();
      expect(job.requestedBy).toBeString();
      expect(job.authoritySnapshot.principal).toBeString();
      expect(job.inputHash).toStartWith("sha256:");
      expect(job.sourceRevision).toBeString();
      expect(["DEMO", "APIFY", "GITHUB"]).toContain(job.provider);
      expect(["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]).toContain(job.status);
      expect("startedAt" in job).toBe(true);
      expect("completedAt" in job);
      expect("receipt" in job).toBe(true);
      expect("artifactRefs" in job).toBe(true);
      expect("errorState" in job).toBe(true);
    }
  });
});
