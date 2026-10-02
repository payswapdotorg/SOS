"use client";

import { useState } from "react";
import { Boxes, FileCode2, GitBranch, Sprout } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import { getSosClient } from "@/lib/api/client";
import type { ArchitectureGraph, Job, System, SystemRevision } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DefinitionList, KeyValue, PageHeader } from "@/components/ui/key-value";
import { TruthStatePill } from "@/components/ui/state-pill";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { ArchitectureGraphView } from "./architecture-graph";
import { formatTimestamp, shortRevision } from "@/lib/format";

const GREENFIELD_STEPS = ["Mission only", "Formalize system hypothesis", "Initial System State"];
const BROWNFIELD_STEPS = ["Repository URL", "Exact-revision selection", "Architecture recovery", "Evidence + uncertainty", "Recovered System State"];

export function SystemsView() {
  const systems = useResource<System[]>((c) => c.listSystems().then((r) => r.items), []);
  const [selected, setSelected] = useState<string | null>(null);
  const activeSystem = selected ?? systems.data?.[0]?.id ?? null;

  return (
    <div>
      <PageHeader
        eyebrow="Systems"
        title="Systems"
        description="System states with onboarding modes, recovery status and architecture. UNKNOWN, FAILED, UNAVAILABLE and UNSUPPORTED are distinct — never blended into “empty”."
      />

      <OnboardingPanel />

      {systems.isLoading ? <LoadingState label="Loading systems…" /> : null}
      {systems.error ? <ErrorState error={systems.error} onRetry={systems.refetch} /> : null}
      {systems.data && !systems.isLoading ? (
        systems.data.length === 0 ? (
          <EmptyState title="No systems onboarded yet" hint="Use the onboarding panel above (greenfield or brownfield)." />
        ) : (
          <div className="mt-4 grid gap-4 lg:grid-cols-[16rem_1fr]">
            <nav aria-label="Systems" className="lg:sticky lg:top-20 lg:self-start">
              <ul className="flex gap-2 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible">
                {systems.data.map((system) => (
                  <li key={system.id} className="shrink-0 lg:shrink">
                    <button
                      type="button"
                      onClick={() => setSelected(system.id)}
                      aria-current={activeSystem === system.id ? "true" : undefined}
                      className={`flex min-h-[44px] w-full items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm font-medium whitespace-nowrap transition-surface ${
                        activeSystem === system.id
                          ? "border-teal-200 bg-teal-50 text-teal-800"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <Boxes aria-hidden="true" className="h-4 w-4" />
                      <span className="font-mono text-xs">{system.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
            <div className="min-w-0">
              {activeSystem ? <SystemDetail systemId={activeSystem} /> : null}
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}

function OnboardingPanel() {
  const [mode, setMode] = useState<"GREENFIELD" | "BROWNFIELD" | null>(null);
  const [repoUrl, setRepoUrl] = useState("");
  const [revision, setRevision] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const client = getSosClient();
  const isDemo = client.runtime.mode === "fixtures";

  return (
    <Card>
      <CardHeader
        title="Onboard a system"
        description="Two explicit modes. Greenfield starts from the mission; brownfield starts from a repository at an exact revision."
      />
      <CardBody>
        <div className="grid gap-3 sm:grid-cols-2">
          <ModeCard
            mode="GREENFIELD"
            icon={<Sprout aria-hidden="true" className="h-5 w-5 text-teal-700" />}
            selected={mode === "GREENFIELD"}
            onSelect={() => {
              setMode("GREENFIELD");
              setSubmitted(false);
            }}
            steps={GREENFIELD_STEPS}
          />
          <ModeCard
            mode="BROWNFIELD"
            icon={<GitBranch aria-hidden="true" className="h-5 w-5 text-teal-700" />}
            selected={mode === "BROWNFIELD"}
            onSelect={() => {
              setMode("BROWNFIELD");
              setSubmitted(false);
            }}
            steps={BROWNFIELD_STEPS}
          />
        </div>

        {mode ? (
          <form
            className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
            onSubmit={(e) => {
              e.preventDefault();
              setSubmitted(true);
            }}
          >
            {mode === "GREENFIELD" ? (
              <>
                <label htmlFor="gf-hypothesis" className="block text-sm font-medium text-slate-700">
                  System hypothesis (from the mission)
                </label>
                <p className="mt-1 text-xs text-slate-500">
                  Formalize the initial hypothesis: which capabilities must exist to realize the
                  mission, before any code exists.
                </p>
                <textarea
                  id="gf-hypothesis"
                  value={hypothesis}
                  onChange={(e) => setHypothesis(e.target.value)}
                  rows={3}
                  placeholder="e.g. Order intake with bounded reservation locking, observable and reversible…"
                  className="mt-2 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600"
                />
              </>
            ) : (
              <>
                <label htmlFor="bf-repo" className="block text-sm font-medium text-slate-700">
                  Repository URL
                </label>
                <input
                  id="bf-repo"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/org/repo"
                  className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 font-mono text-xs focus-visible:outline-2 focus-visible:outline-teal-600"
                />
                <label htmlFor="bf-rev" className="mt-3 block text-sm font-medium text-slate-700">
                  Exact revision (commit SHA — pinned, immutable)
                </label>
                <input
                  id="bf-rev"
                  value={revision}
                  onChange={(e) => setRevision(e.target.value)}
                  placeholder="40-hex commit SHA or ref to resolve"
                  className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 font-mono text-xs focus-visible:outline-2 focus-visible:outline-teal-600"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Architecture recovery runs as a job at the pinned revision; evidence and
                  uncertainty land with the recovered state.
                </p>
              </>
            )}
            <div className="mt-3 flex items-center gap-2">
              <Button type="submit" variant="primary" size="sm">
                {mode === "GREENFIELD" ? "Formalize hypothesis" : "Start recovery"}
              </Button>
            </div>
            {submitted ? (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800" role="status">
                {isDemo ? (
                  <>
                    <DemoBadge /> Demo mode: no job is created and nothing is persisted — with a
                    configured API this {mode === "GREENFIELD" ? "formalizes the hypothesis into an initial system state" : "creates a recovery job (POST /api/v1/systems/{id}/recovery) at the exact revision"}.
                  </>
                ) : (
                  <>Submitted — the job is queued and will appear under Systems when it starts.</>
                )}
              </div>
            ) : null}
          </form>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ModeCard({
  mode,
  icon,
  steps,
  selected,
  onSelect,
}: {
  mode: "GREENFIELD" | "BROWNFIELD";
  icon: React.ReactNode;
  steps: string[];
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`rounded-xl border p-4 text-left transition-surface ${
        selected ? "border-teal-300 bg-teal-50 ring-1 ring-teal-200" : "border-slate-200 bg-white hover:bg-slate-50"
      }`}
    >
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-sm font-bold tracking-wide text-slate-900">{mode}</span>
      </div>
      <ol className="mt-3 space-y-1.5 text-xs text-slate-600">
        {steps.map((step, i) => (
          <li key={step} className="flex items-center gap-2">
            <span aria-hidden="true" className="flex h-4 w-4 items-center justify-center rounded-full bg-slate-200 text-[10px] font-bold text-slate-600">
              {i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
    </button>
  );
}

function SystemDetail({ systemId }: { systemId: string }) {
  const system = useResource<System | null>(async (c) => {
    try {
      return await c.getSystem(systemId);
    } catch {
      return null;
    }
  }, [systemId]);
  const revision = useResource<SystemRevision | null>(async (c) => {
    try {
      return await c.getSystemRevision(systemId);
    } catch {
      return null;
    }
  }, [systemId]);
  const graph = useResource<ArchitectureGraph>((c) => c.getArchitectureGraph(systemId), [systemId]);
  const job = useResource<Job | null>(async (c) => {
    const rev = await (async () => {
      try {
        return await c.getSystemRevision(systemId);
      } catch {
        return null;
      }
    })();
    if (!rev) return null;
    try {
      return await c.getJob(rev.recovery.jobId);
    } catch {
      return null;
    }
  }, [systemId]);

  if (system.isLoading || revision.isLoading) {
    return <LoadingState label="Loading system…" />;
  }
  if (system.error) {
    return <ErrorState error={system.error} onRetry={system.refetch} />;
  }
  if (!system.data) {
    return <ErrorState error={new Error(`System ${systemId} not found`)} />;
  }
  const s = system.data;
  const r = revision.data;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <FileCode2 aria-hidden="true" className="h-4 w-4 text-teal-700" />
              <span className="font-mono text-base">{s.name}</span>
            </span>
          }
          description={`Mode: ${s.mode} · current revision: ${s.currentRevisionId}`}
          actions={
            <span className="flex items-center gap-2">
              <Badge tone={s.mode === "BROWNFIELD" ? "slate" : "teal"}>{s.mode}</Badge>
              {r ? <TruthStatePill state={r.recovery.status} /> : null}
            </span>
          }
        />
        <CardBody>
          {revision.error ? (
            <ErrorState error={revision.error} onRetry={revision.refetch} />
          ) : !r ? (
            <LoadingState label="Loading system revision…" />
          ) : (
            <SystemSummaryRows revision={r} />
          )}
        </CardBody>
      </Card>

      {job.data ? <RecoveryJobCard job={job.data} /> : null}

      <Card>
        <CardHeader
          title="Architecture graph"
          description="Recovered topology (typed nodes/edges) — rendered as a diagram plus the exact structured list."
        />
        <CardBody>
          {graph.isLoading ? <LoadingState label="Loading architecture…" /> : null}
          {graph.error ? <ErrorState error={graph.error} onRetry={graph.refetch} /> : null}
          {graph.data && !graph.isLoading ? <ArchitectureGraphView graph={graph.data} /> : null}
        </CardBody>
      </Card>
    </div>
  );
}

/** Static summary rows for a system revision (exported for unit tests). */
export function SystemSummaryRows({ revision: r }: { revision: SystemRevision }) {
  return (
    <DefinitionList>
      <KeyValue label="State summary">{r.stateSummary.summary}</KeyValue>
      <KeyValue label="Health">
        <span className="flex items-center gap-2">
          <TruthStatePill state={r.stateSummary.health} />
          <span className="text-xs text-slate-500">
            drift: {r.stateSummary.drift.toLowerCase()}
          </span>
        </span>
      </KeyValue>
      <KeyValue label="Uncertainty">
        <span className="flex flex-wrap items-center gap-2">
          <TruthStatePill state={r.uncertainty.state} />
          <span className="text-xs text-slate-500">
            {r.uncertainty.confidence !== null ? `confidence ${r.uncertainty.confidence} · ` : ""}
            {r.uncertainty.reason}
          </span>
        </span>
      </KeyValue>
      <KeyValue label="Source" mono>
        {r.sourceRef.kind} · {r.sourceRef.url} @ {shortRevision(r.sourceRef.revision, 12)}{" "}
        {r.sourceRef.immutable ? "(immutable)" : "(NOT immutable)"}
      </KeyValue>
      <KeyValue label="Recovery">
        <span className="flex flex-wrap items-center gap-2">
          <TruthStatePill state={r.recovery.status} />
          <span className="text-xs text-slate-600">{r.recovery.note}</span>
        </span>
      </KeyValue>
      <KeyValue label="Topology">
        {r.stateSummary.services} services · {r.stateSummary.dataStores} data stores ·{" "}
        {r.stateSummary.integrations} integrations
      </KeyValue>
    </DefinitionList>
  );
}

function RecoveryJobCard({ job }: { job: Job }) {
  return (
    <Card>
      <CardHeader
        title="Recovery job"
        description={`${job.type} · provider ${job.provider}`}
        actions={
          <span className="flex items-center gap-2">
            <Badge tone={job.status === "COMPLETED" ? "emerald" : job.status === "RUNNING" ? "amber" : job.status === "FAILED" ? "rose" : "slate"}>
              {job.status}
            </Badge>
            {job.receipt?.demo ? <DemoBadge /> : null}
          </span>
        }
      />
      <CardBody>
        <DefinitionList>
          <KeyValue label="Job">{job.id}</KeyValue>
          <KeyValue label="Requested by">{job.requestedBy}</KeyValue>
          <KeyValue label="Input hash" mono>{job.inputHash}</KeyValue>
          <KeyValue label="Source revision" mono>{shortRevision(job.sourceRevision, 16)}</KeyValue>
          <KeyValue label="Started / completed">
            {job.startedAt ? formatTimestamp(job.startedAt) : "—"} /{" "}
            {job.completedAt ? formatTimestamp(job.completedAt) : "— (still running or cancelled)"}
          </KeyValue>
          {job.errorState ? (
            <KeyValue label="Error state">
              <span className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 font-mono text-xs text-rose-800">
                {job.errorState.code}: {job.errorState.message}
              </span>
            </KeyValue>
          ) : null}
          {job.artifactRefs.length > 0 ? (
            <KeyValue label="Artifacts">
              <ul className="space-y-1">
                {job.artifactRefs.map((a) => (
                  <li key={a.name}>
                    <a
                      href={a.signedUrl}
                      className="font-mono text-xs text-teal-700 underline decoration-teal-300 transition-surface hover:text-teal-800"
                    >
                      {a.name}
                    </a>{" "}
                    <span className="text-xs text-slate-400">(signed URL)</span>
                  </li>
                ))}
              </ul>
            </KeyValue>
          ) : null}
        </DefinitionList>
      </CardBody>
    </Card>
  );
}
