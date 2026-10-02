"use client";

import Link from "next/link";
import { AlertCircle, ArrowRight, Compass, Gauge } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import { getSosClient } from "@/lib/api/client";
import type { Decision, Mission, MissionRevision, System, SystemRevision } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { DefinitionList, KeyValue } from "@/components/ui/key-value";
import { TruthStatePill } from "@/components/ui/state-pill";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { formatTimestamp, shortRevision } from "@/lib/format";

const WORKSPACE_ID = "ws_aurora_demo";

export function OverviewView() {
  const client = getSosClient();
  const isDemo = client.runtime.mode === "fixtures";

  const mission = useResource<Mission>((c) => c.getMission(WORKSPACE_ID), []);
  const revision = useResource<MissionRevision | null>(
    async (c) => {
      const m = await c.getMission(WORKSPACE_ID);
      const revisions = (await c.listMissionRevisions(m.id)).items;
      return revisions.find((r) => r.id === m.currentRevisionId) ?? null;
    },
    [],
  );
  const systems = useResource<System[]>((c) => c.listSystems().then((r) => r.items), []);
  const decisions = useResource<Decision[]>((c) => c.listDecisions().then((r) => r.items), []);

  const ask = decisions.data?.find((d) => d.action === "ASK" && d.status === "AWAITING_OWNER");
  const mainSystem = systems.data?.find((s) => s.id === "sys_fulfillment");

  return (
    <div>
      <header className="mb-5">
        <p className="text-xs font-semibold tracking-widest text-teal-700 uppercase">Workspace</p>
        <h1 className="mt-1 text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
          Mission-governed cockpit
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          The governing loop for this workspace: what the mission demands, what the current system
          state is, and the next decision that needs an authority.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Compass aria-hidden="true" className="h-4 w-4 text-teal-700" />
                Mission
              </span>
            }
            description="You are the mission authority — revisions are approved by you, never inferred from telemetry."
            actions={
              <Link
                href="/workspace/mission"
                className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-slate-300 px-3 text-xs font-medium text-slate-700 transition-surface hover:bg-slate-50"
              >
                Mission journey
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
              </Link>
            }
          />
          <CardBody>
            {mission.isLoading ? <LoadingState label="Loading mission…" /> : null}
            {mission.error ? <ErrorState error={mission.error} onRetry={mission.refetch} /> : null}
            {mission.data && !mission.isLoading ? (
              <div>
                <p className="text-base font-semibold text-slate-900">{mission.data.title}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Badge tone="teal">{mission.data.status}</Badge>
                  <Badge>revision {revision.data?.revision ?? "—"}</Badge>
                  {revision.data?.approval.state === "APPROVED" ? (
                    <Badge tone="emerald">
                      approved by {revision.data.approval.decidedBy} ·{" "}
                      {formatTimestamp(revision.data.approval.decidedAt ?? "")}
                    </Badge>
                  ) : (
                    <Badge tone="amber">proposed — awaiting approval</Badge>
                  )}
                  {isDemo ? <DemoBadge /> : null}
                </div>
                {revision.data ? (
                  <DefinitionList className="mt-4">
                    <KeyValue label="Goals">
                      {revision.data.goals.length} — first: {revision.data.goals[0]?.statement}
                    </KeyValue>
                    <KeyValue label="Outcomes">{revision.data.outcomes.length}</KeyValue>
                    <KeyValue label="Measures">
                      {revision.data.measures
                        .slice(0, 3)
                        .map((m) => `${m.name}: ${m.current ?? "—"} / ${m.target}`)
                        .join(" · ")}
                    </KeyValue>
                  </DefinitionList>
                ) : null}
              </div>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Gauge aria-hidden="true" className="h-4 w-4 text-teal-700" />
                Current system state
              </span>
            }
            description={mainSystem ? mainSystem.name : "loading…"}
            actions={
              <Link
                href="/workspace/systems"
                className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-slate-300 px-3 text-xs font-medium text-slate-700 transition-surface hover:bg-slate-50"
              >
                Systems
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
              </Link>
            }
          />
          <CardBody>
            {systems.isLoading ? <LoadingState label="Loading systems…" /> : null}
            {systems.error ? <ErrorState error={systems.error} onRetry={systems.refetch} /> : null}
            {systems.data && !systems.isLoading ? (
              <SystemOverviewList systems={systems.data} />
            ) : null}
          </CardBody>
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          <CardHeader
            title="Next governed action"
            description="The decision currently waiting for an authority — ASK is a first-class state here."
            actions={
              <Link
                href="/workspace/decisions"
                className="inline-flex min-h-[36px] items-center gap-1 rounded-lg border border-slate-300 px-3 text-xs font-medium text-slate-700 transition-surface hover:bg-slate-50"
              >
                All decisions
                <ArrowRight aria-hidden="true" className="h-3.5 w-3.5" />
              </Link>
            }
          />
          <CardBody>
            {decisions.isLoading ? <LoadingState label="Loading decisions…" /> : null}
            {decisions.error ? <ErrorState error={decisions.error} onRetry={decisions.refetch} /> : null}
            {decisions.data && !decisions.isLoading ? (
              ask ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="amber">
                      <AlertCircle aria-hidden="true" className="h-3 w-3" />
                      DECISION: ASK
                    </Badge>
                    <span className="text-sm font-semibold text-slate-900">
                      {ask.candidateName ?? ask.id}
                    </span>
                    {isDemo ? <DemoBadge /> : null}
                  </div>
                  <p className="mt-2 text-sm text-slate-700">{ask.askPayload?.decision}</p>
                  <p className="mt-2 text-xs text-slate-500">
                    Approve / reject / provide evidence on the{" "}
                    <Link href="/workspace/decisions" className="font-medium text-teal-700 underline decoration-teal-300">
                      Decisions
                    </Link>{" "}
                    panel.
                  </p>
                </div>
              ) : (
                <p className="text-sm text-slate-600">
                  No decision is currently awaiting an owner action.
                </p>
              )
            ) : null}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function SystemOverviewList({ systems }: { systems: System[] }) {
  return (
    <ul className="space-y-3">
      {systems.slice(0, 4).map((system) => (
        <li key={system.id} className="rounded-lg border border-slate-100 bg-slate-50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-xs text-slate-700">{system.name}</span>
            <Badge tone={system.mode === "BROWNFIELD" ? "slate" : "teal"}>{system.mode}</Badge>
          </div>
          <SystemHealthLine systemId={system.id} />
        </li>
      ))}
    </ul>
  );
}

function SystemHealthLine({ systemId }: { systemId: string }) {
  const revision = useResource<SystemRevision | null>(
    async (c) => {
      try {
        return await c.getSystemRevision(systemId);
      } catch {
        return null;
      }
    },
    [systemId],
  );
  if (revision.isLoading) {
    return <p className="mt-1.5 text-xs text-slate-400">loading state…</p>;
  }
  if (revision.error || !revision.data) {
    return <p className="mt-1.5 text-xs text-slate-400">state unavailable</p>;
  }
  const r = revision.data;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
      <TruthStatePill state={r.stateSummary.health} withLabel={false} />
      <span>
        health · drift: {r.stateSummary.drift.toLowerCase()} · uncertainty:{" "}
        {r.uncertainty.level.toLowerCase()} · rev {shortRevision(r.sourceRef.revision, 7)}
      </span>
    </div>
  );
}
