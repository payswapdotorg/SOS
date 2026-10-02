"use client";

import { useResource } from "@/hooks/use-resource";
import type { Execution, Experiment } from "@/lib/api/types";
import { EXPERIMENT_LIFECYCLE } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/key-value";
import { Timeline, TimelineItem } from "@/components/ui/timeline";
import { TruthStatePill } from "@/components/ui/state-pill";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatTimestamp, shortRevision } from "@/lib/format";

export function ExperimentsView() {
  const experiments = useResource<Experiment[]>((c) => c.listExperiments().then((r) => r.items), []);
  const executions = useResource<Execution[]>((c) => c.listExecutions().then((r) => r.items), []);

  return (
    <div>
      <PageHeader
        eyebrow="Experiments"
        title="Experiment lifecycle"
        description="Bounded interventions (shadow, canary) with a status timeline, executions and provider receipts. Demo receipts are badged DEMO — never presented as real infrastructure runs."
      />

      {experiments.isLoading ? <LoadingState label="Loading experiments…" /> : null}
      {experiments.error ? <ErrorState error={experiments.error} onRetry={experiments.refetch} /> : null}
      {experiments.data && !experiments.isLoading ? (
        experiments.data.length === 0 ? (
          <EmptyState title="No experiments yet" hint="Experiments appear when an EXPERIMENT decision is executed." />
        ) : (
          <div className="space-y-4">
            {experiments.data.map((experiment) => (
              <ExperimentCard
                key={experiment.id}
                experiment={experiment}
                executions={(executions.data ?? []).filter((x) => x.experimentId === experiment.id)}
              />
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function LifecycleTrack({ status }: { status: Experiment["status"] }) {
  const rolledBack = status === "ROLLED_BACK";
  const activeIndex = EXPERIMENT_LIFECYCLE.indexOf(status);
  const stages = EXPERIMENT_LIFECYCLE.filter((s) => s !== "ROLLED_BACK");
  return (
    <div className="overflow-x-auto">
      <ol className="flex min-w-max items-center gap-1.5" aria-label="Experiment lifecycle stages">
        {stages.map((stage, index) => {
          const reached = !rolledBack && activeIndex >= index && activeIndex >= 0;
          const current = !rolledBack && stage === status;
          return (
            <li key={stage} className="flex items-center gap-1.5">
              <span
                aria-current={current ? "step" : undefined}
                className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-surface ${
                  current
                    ? "border-teal-300 bg-teal-50 text-teal-800"
                    : reached
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 bg-white text-slate-400"
                }`}
              >
                {stage.toLowerCase()}
              </span>
              {index < stages.length - 1 ? (
                <span aria-hidden="true" className={reached ? "text-emerald-400" : "text-slate-300"}>
                  →
                </span>
              ) : null}
            </li>
          );
        })}
        {rolledBack ? (
          <li className="flex items-center gap-1.5">
            <span aria-hidden="true" className="text-slate-400">…</span>
            <span className="rounded-full border border-orange-300 bg-orange-50 px-2.5 py-0.5 text-[11px] font-medium text-orange-800">
              rolled back
            </span>
          </li>
        ) : null}
      </ol>
    </div>
  );
}

function ExperimentCard({
  experiment,
  executions,
}: {
  experiment: Experiment;
  executions: Execution[];
}) {
  return (
    <Card as="article">
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm">{experiment.id}</span>
            <Badge tone="teal">{experiment.candidateName}</Badge>
          </span>
        }
        description={`Current stage: ${experiment.status.toLowerCase()}`}
        actions={<Badge tone={experiment.status === "ROLLED_BACK" ? "orange" : "emerald"}>{experiment.status}</Badge>}
      />
      <CardBody className="space-y-5">
        <section aria-label="Lifecycle">
          <LifecycleTrack status={experiment.status} />
        </section>

        <section aria-label="Event timeline">
          <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Events</h4>
          <div className="scroll-area mt-2 pr-2">
            <Timeline>
              {experiment.events.map((event) => (
                <TimelineItem
                  key={event.id}
                  at={formatTimestamp(event.at)}
                  title={event.label}
                  badge={event.status ? <TruthStatePill state={event.status} /> : undefined}
                >
                  {event.detail}
                </TimelineItem>
              ))}
            </Timeline>
          </div>
        </section>

        <section aria-label="Executions and receipts">
          <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
            Executions &amp; receipts
          </h4>
          {executions.length === 0 ? (
            <p className="mt-2 text-sm text-slate-500">
              No execution for this experiment yet — EMPTY (observed, none), not unknown.
            </p>
          ) : (
            <ul className="mt-2 space-y-3">
              {executions.map((execution) => (
                <ExecutionCard key={execution.id} execution={execution} />
              ))}
            </ul>
          )}
        </section>
      </CardBody>
    </Card>
  );
}

export function ExecutionCard({ execution }: { execution: Execution }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs font-semibold text-slate-700">{execution.id}</span>
        <Badge tone={execution.provider === "DEMO" ? "amber" : "violet"}>provider: {execution.provider}</Badge>
        <TruthStatePill state={execution.status} />
        {execution.receipt?.demo ? <DemoBadge label="DEMO RECEIPT" /> : null}
      </div>
      <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
        <div>
          <dt className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">Request hash</dt>
          <dd className="font-mono text-xs break-all text-slate-700">{execution.requestHash}</dd>
        </div>
        <div>
          <dt className="text-[11px] font-medium tracking-wide text-slate-500 uppercase">Experiment</dt>
          <dd className="font-mono text-xs text-slate-700">{execution.experimentId ?? execution.jobId ?? "—"}</dd>
        </div>
      </dl>
      {execution.receipt ? (
        <div className="mt-2 rounded-md border border-slate-200 bg-white p-2.5">
          <p className="text-xs font-semibold text-slate-700">
            Receipt — run {execution.receipt.runId}
            {execution.receipt.demo ? (
              <span className="ml-2">
                <DemoBadge />
              </span>
            ) : null}
          </p>
          <p className="mt-1 text-xs text-slate-600">{execution.receipt.summary}</p>
          <p className="mt-1 text-[11px] text-slate-400">
            completed {formatTimestamp(execution.receipt.completedAt)}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-500">
          No receipt yet — {execution.status === "UNKNOWN" ? "outcome UNKNOWN (run in progress); no success is claimed." : "receipt pending."}
        </p>
      )}
      {execution.artifactRefs.length > 0 ? (
        <p className="mt-2">
          {execution.artifactRefs.map((artifact) => (
            <a
              key={artifact.name}
              href={artifact.signedUrl}
              className="mr-3 font-mono text-xs text-teal-700 underline decoration-teal-300 transition-surface hover:text-teal-800"
            >
              {artifact.name}
            </a>
          ))}
          <span className="text-xs text-slate-400">(signed artifact URLs)</span>
        </p>
      ) : null}
      <p className="mt-1 text-[11px] text-slate-400">
        request hash: {shortRevision(execution.requestHash, 18)}…
      </p>
    </li>
  );
}
