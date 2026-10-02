"use client";

import { useMemo, useState } from "react";
import { Check, Crown, X } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import type { AssuranceRun, Candidate, ObjectiveEvaluation } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/key-value";
import { TruthStatePill, VerdictPill } from "@/components/ui/state-pill";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import Link from "next/link";

const TRADE_OFF_DIMENSIONS = [
  { key: "mission effect", hint: "expected effects on mission objectives" },
  { key: "cost", hint: "engineering + infrastructure" },
  { key: "risk", hint: "likelihood × severity, with mitigations" },
  { key: "constraints", hint: "compliance with mission constraints" },
  { key: "evidence", hint: "what backs the claims" },
  { key: "reversibility", hint: "rollback path quality" },
] as const;

const ASSESSMENT_TONE: Record<ObjectiveEvaluation["assessment"], "emerald" | "slate" | "rose" | "zinc"> = {
  GOOD: "emerald",
  NEUTRAL: "slate",
  BAD: "rose",
  UNKNOWN: "zinc",
};

export function CandidatesView() {
  const candidates = useResource<Candidate[]>((c) => c.listCandidates().then((r) => r.items), []);
  const assurance = useResource<AssuranceRun[]>((c) => c.listAssuranceRuns().then((r) => r.items), []);
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  const visible = useMemo(
    () => (candidates.data ?? []).filter((c) => !hidden.has(c.id)),
    [candidates.data, hidden],
  );

  const objectives = useMemo(() => {
    const order: string[] = [];
    for (const candidate of visible) {
      for (const obj of candidate.evaluation.objectives) {
        if (!order.includes(obj.objectiveId)) order.push(obj.objectiveId);
      }
    }
    return order;
  }, [visible]);

  return (
    <div>
      <PageHeader
        eyebrow="Candidates"
        title="Candidate comparison"
        description="Side-by-side trade-offs across six dimensions plus a multi-objective evaluation. There is deliberately NO single score — SOS reasons over a Pareto set, not one number."
      />

      {candidates.isLoading ? <LoadingState label="Loading candidates…" /> : null}
      {candidates.error ? <ErrorState error={candidates.error} onRetry={candidates.refetch} /> : null}
      {candidates.data && !candidates.isLoading ? (
        <>
          <Card>
            <CardHeader title="Compare" description="Select the candidates to include in the comparison." />
            <CardBody>
              <div className="flex flex-wrap gap-2">
                {candidates.data.map((candidate) => {
                  const included = !hidden.has(candidate.id);
                  return (
                    <button
                      key={candidate.id}
                      type="button"
                      onClick={() =>
                        setHidden((prev) => {
                          const next = new Set(prev);
                          if (next.has(candidate.id)) next.delete(candidate.id);
                          else next.add(candidate.id);
                          return next;
                        })
                      }
                      aria-pressed={included}
                      className={`inline-flex min-h-[36px] items-center gap-2 rounded-full border px-3 text-xs font-medium transition-surface ${
                        included
                          ? "border-teal-300 bg-teal-50 text-teal-800"
                          : "border-slate-200 bg-white text-slate-400 hover:bg-slate-50"
                      }`}
                    >
                      {included ? (
                        <Check aria-hidden="true" className="h-3.5 w-3.5" />
                      ) : (
                        <X aria-hidden="true" className="h-3.5 w-3.5" />
                      )}
                      {candidate.name}
                    </button>
                  );
                })}
              </div>
            </CardBody>
          </Card>

          {visible.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="No candidates selected" hint="Toggle at least one candidate above." />
            </div>
          ) : (
            <>
              <div className="mt-4 grid gap-4 xl:grid-cols-3">
                {visible.map((candidate) => (
                  <TradeOffCard key={candidate.id} candidate={candidate} />
                ))}
              </div>

              <div className="mt-4">
                <EvaluationTable candidates={visible} objectiveOrder={objectives} />
              </div>

              <div className="mt-4">
                <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
                  Assurance
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  Assurance runs with checks and a verdict per candidate — verdicts gate the
                  lifecycle, they never authorize promotion by themselves.
                </p>
                <div className="mt-3 space-y-4">
                  {assurance.data && assurance.data.length > 0 ? (
                    assurance.data
                      .filter((run) => visible.some((c) => c.id === run.candidateId))
                      .map((run) => <AssuranceCard key={run.id} run={run} candidates={visible} />)
                  ) : (
                    <EmptyState
                      title="No assurance runs for the selected candidates"
                      hint="Runs appear here when candidates pass through assurance."
                    />
                  )}
                </div>
              </div>
            </>
          )}
        </>
      ) : null}
    </div>
  );
}

export function TradeOffCard({ candidate }: { candidate: Candidate }) {
  return (
    <Card as="article" className="flex flex-col">
      <CardHeader
        title={candidate.name}
        description={<span className="font-mono text-xs">{candidate.id}</span>}
        actions={
          candidate.evaluation.paretoFront ? (
            <Badge tone="emerald" title="Not dominated on any objective by another candidate">
              <Crown aria-hidden="true" className="h-3 w-3" />
              Pareto front
            </Badge>
          ) : (
            <Badge tone="slate" title="Dominated by at least one candidate on the objectives shown">
              dominated
            </Badge>
          )
        }
      />
      <CardBody className="flex-1 space-y-4">
        <section aria-label="Subgraph replacement">
          <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Subgraph replacement (A′ = A − S + S′)
          </h4>
          <p className="mt-1 text-xs text-slate-600">{candidate.subgraphReplacement.boundary}</p>
          <p className="mt-1 font-mono text-xs text-slate-500">
            − [{candidate.subgraphReplacement.removes.join(", ")}] + [
            {candidate.subgraphReplacement.adds.map((a) => a.id).join(", ")}]
          </p>
          <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-slate-500">
            {candidate.subgraphReplacement.boundaryInvariants.map((inv) => (
              <li key={inv}>{inv}</li>
            ))}
          </ul>
        </section>

        <section aria-label="Trade-offs">
          <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Trade-offs
          </h4>
          <dl className="mt-2 space-y-3">
            {TRADE_OFF_DIMENSIONS.map(({ key, hint }) => (
              <div key={key} className="rounded-lg border border-slate-100 bg-slate-50 p-2.5">
                <dt className="flex items-center justify-between text-xs font-semibold text-slate-700">
                  {key}
                  <span className="font-normal text-slate-400">{hint}</span>
                </dt>
                <dd className="mt-1">
                  <TradeOffDetail dimension={key} candidate={candidate} />
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </CardBody>
    </Card>
  );
}

function TradeOffDetail({
  dimension,
  candidate,
}: {
  dimension: (typeof TRADE_OFF_DIMENSIONS)[number]["key"];
  candidate: Candidate;
}) {
  switch (dimension) {
    case "mission effect":
      return (
        <ul className="space-y-1 text-xs text-slate-600">
          {candidate.effects.map((effect) => (
            <li key={effect.onObjective}>
              <Badge
                tone={
                  effect.direction === "IMPROVE"
                    ? "emerald"
                    : effect.direction === "REGRESS"
                      ? "rose"
                      : effect.direction === "UNCERTAIN"
                        ? "zinc"
                        : "slate"
                }
              >
                {effect.direction.toLowerCase()}
              </Badge>{" "}
              <span className="font-mono text-[11px]">{effect.onObjective}</span> — {effect.description}
            </li>
          ))}
        </ul>
      );
    case "cost":
      return (
        <ul className="space-y-1 text-xs text-slate-600">
          {candidate.costs.map((cost) => (
            <li key={cost.description}>
              <Badge tone={cost.magnitude === "HIGH" ? "rose" : cost.magnitude === "MEDIUM" ? "amber" : "emerald"}>
                {cost.magnitude}
              </Badge>{" "}
              {cost.description} ({cost.quantifier})
            </li>
          ))}
        </ul>
      );
    case "risk":
      return (
        <ul className="space-y-1.5 text-xs text-slate-600">
          {candidate.risks.map((risk) => (
            <li key={risk.description}>
              <Badge tone={risk.severity === "HIGH" ? "rose" : risk.severity === "MEDIUM" ? "amber" : "slate"}>
                severity {risk.severity}
              </Badge>{" "}
              <Badge tone={risk.likelihood === "HIGH" ? "rose" : risk.likelihood === "MEDIUM" ? "amber" : "slate"}>
                likelihood {risk.likelihood}
              </Badge>
              <p className="mt-0.5">{risk.description}</p>
              <p className="text-slate-500">Mitigation: {risk.mitigation}</p>
            </li>
          ))}
        </ul>
      );
    case "constraints":
      return (
        <ul className="space-y-1 text-xs text-slate-600">
          {candidate.constraints.map((c) => (
            <li key={c.constraint}>
              <Badge
                tone={
                  c.compliance === "SATISFIED"
                    ? "emerald"
                    : c.compliance === "VIOLATED"
                      ? "rose"
                      : c.compliance === "AT_RISK"
                        ? "amber"
                        : "zinc"
                }
              >
                {c.compliance.toLowerCase()}
              </Badge>{" "}
              {c.constraint}
              <p className="text-slate-500">{c.note}</p>
            </li>
          ))}
        </ul>
      );
    case "evidence":
      return (
        <ul className="space-y-0.5 text-xs">
          {candidate.evidenceRefs.length === 0 ? (
            <li className="text-slate-500">No codebase-specific evidence — claims rest on nothing.</li>
          ) : (
            candidate.evidenceRefs.map((ref) => (
              <li key={ref}>
                <Link
                  href={`/workspace/evidence#evidence-${ref}`}
                  className="font-mono text-teal-700 underline decoration-teal-300 transition-surface hover:text-teal-800"
                >
                  {ref}
                </Link>
              </li>
            ))
          )}
        </ul>
      );
    case "reversibility":
      return (
        <div className="text-xs text-slate-600">
          <Badge
            tone={
              candidate.reversibility.level === "FULLY_REVERSIBLE"
                ? "emerald"
                : candidate.reversibility.level === "PARTIALLY_REVERSIBLE"
                  ? "amber"
                  : "rose"
            }
          >
            {candidate.reversibility.level.toLowerCase().replaceAll("_", " ")}
          </Badge>
          <p className="mt-1">{candidate.reversibility.rollbackPath}</p>
          <p className="text-slate-500">{candidate.reversibility.notes}</p>
        </div>
      );
  }
}

export function EvaluationTable({
  candidates,
  objectiveOrder,
}: {
  candidates: Candidate[];
  objectiveOrder: string[];
}) {
  return (
    <Card>
      <CardHeader
        title="Multi-objective evaluation"
        description="One row per objective, evaluated separately. No aggregated score exists by design — the last row records Pareto-front membership only."
      />
      <CardBody className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <caption className="sr-only">
            Multi-objective evaluation table: objectives as rows, candidates as columns
          </caption>
          <thead>
            <tr>
              <th scope="col" className="border-b border-slate-200 py-2 pr-4 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
                Objective
              </th>
              {candidates.map((candidate) => (
                <th
                  key={candidate.id}
                  scope="col"
                  className="border-b border-slate-200 px-3 py-2 text-left text-xs font-semibold text-slate-700"
                >
                  {candidate.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objectiveOrder.map((objectiveId) => {
              const sample = candidates
                .flatMap((c) => c.evaluation.objectives)
                .find((o) => o.objectiveId === objectiveId);
              return (
                <tr key={objectiveId} className="odd:bg-slate-50/60">
                  <th scope="row" className="border-b border-slate-100 py-2.5 pr-4 text-left">
                    <span className="text-xs font-semibold text-slate-700">
                      {sample?.objective ?? objectiveId}
                    </span>
                    <span className="ml-2 text-[11px] font-normal text-slate-400">
                      {sample?.direction.toLowerCase()}
                    </span>
                  </th>
                  {candidates.map((candidate) => {
                    const evaluation = candidate.evaluation.objectives.find(
                      (o) => o.objectiveId === objectiveId,
                    );
                    return (
                      <td key={candidate.id} className="border-b border-slate-100 px-3 py-2.5 align-top">
                        {evaluation ? (
                          <span className="flex items-center gap-2">
                            <span className="font-mono text-xs text-slate-800">{evaluation.value}</span>
                            <span className="text-[11px] text-slate-400">{evaluation.unit}</span>
                            <Badge tone={ASSESSMENT_TONE[evaluation.assessment]}>
                              {evaluation.assessment.toLowerCase()}
                            </Badge>
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400">not evaluated</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            <tr>
              <th scope="row" className="py-2.5 pr-4 text-left text-xs font-semibold text-slate-700">
                Pareto-front membership
              </th>
              {candidates.map((candidate) => (
                <td key={candidate.id} className="px-3 py-2.5">
                  {candidate.evaluation.paretoFront ? (
                    <Badge tone="emerald">
                      <Crown aria-hidden="true" className="h-3 w-3" />
                      on the front
                    </Badge>
                  ) : (
                    <Badge tone="slate">dominated</Badge>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
        <p className="mt-3 text-xs text-slate-500">
          A single scalar score would hide the trade-offs the architecture requires — that is why
          none is shown.
        </p>
      </CardBody>
    </Card>
  );
}

function AssuranceCard({ run, candidates }: { run: AssuranceRun; candidates: Candidate[] }) {
  const candidate = candidates.find((c) => c.id === run.candidateId);
  return (
    <Card>
      <CardHeader
        title={`Assurance run — ${candidate?.name ?? run.candidateId}`}
        description={`${run.id} · ${run.checks.length} checks`}
        actions={<VerdictPill verdict={run.verdict} />}
      />
      <CardBody>
        <ul className="space-y-2">
          {run.checks.map((check) => (
            <li
              key={check.id}
              className="flex items-start gap-2.5 rounded-lg border border-slate-100 bg-slate-50 p-2.5"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-800">{check.name}</p>
                <p className="text-xs text-slate-600">{check.detail}</p>
              </div>
              <TruthStatePill state={check.status} />
            </li>
          ))}
        </ul>
        <p className="mt-3 rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">
          <strong>Verdict: {run.verdict}.</strong> {run.verdictNote}
        </p>
      </CardBody>
    </Card>
  );
}
