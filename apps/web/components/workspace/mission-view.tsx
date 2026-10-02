"use client";

import { useMemo, useState } from "react";
import { Check, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import { getSosClient } from "@/lib/api/client";
import type { Mission, MissionRevision } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { formatTimestamp } from "@/lib/format";

const WORKSPACE_ID = "ws_aurora_demo";

type Stage = {
  key: "mission" | "goals" | "outcomes" | "stakeholders" | "measures" | "constraints" | "preferences" | "approve";
  label: string;
  hint: string;
};

const STAGES: Stage[] = [
  { key: "mission", label: "Mission", hint: "The enduring purpose — why this system exists." },
  { key: "goals", label: "Goals", hint: "What must improve, stated as intent." },
  { key: "outcomes", label: "Outcomes", hint: "Observable results you want to see in the world." },
  { key: "stakeholders", label: "Stakeholders", hint: "Who holds a stake and what they care about." },
  { key: "measures", label: "Measures", hint: "Measurable indicators with targets and current values." },
  { key: "constraints", label: "Constraints", hint: "Hard limits and soft limits. Hard outranks preference." },
  { key: "preferences", label: "Preferences", hint: "Directional preferences — weighed, never absolute." },
  { key: "approve", label: "Approve Mission Revision", hint: "Your explicit authorization records this revision." },
];

interface Draft {
  goals: { statement: string; rationale: string }[];
  outcomes: { statement: string; metric: string }[];
  stakeholders: { name: string; role: string; interest: string }[];
  measures: { name: string; target: string; current: string; unit: string }[];
  constraints: { statement: string; severity: "HARD" | "SOFT" }[];
  preferences: { statement: string }[];
}

function draftFromRevision(revision: MissionRevision): Draft {
  return {
    goals: revision.goals.map((g) => ({ statement: g.statement, rationale: g.rationale })),
    outcomes: revision.outcomes.map((o) => ({ statement: o.statement, metric: o.metric })),
    stakeholders: revision.stakeholders.map((s) => ({ name: s.name, role: s.role, interest: s.interest })),
    measures: revision.measures.map((m) => ({ name: m.name, target: m.target, current: m.current ?? "", unit: m.unit })),
    constraints: revision.constraints.map((c) => ({ statement: c.statement, severity: c.severity })),
    preferences: revision.preferences.map((p) => ({ statement: p.statement })),
  };
}

const emptyRow: Record<keyof Draft, () => Record<string, string>> = {
  goals: () => ({ statement: "", rationale: "" }),
  outcomes: () => ({ statement: "", metric: "" }),
  stakeholders: () => ({ name: "", role: "", interest: "" }),
  measures: () => ({ name: "", target: "", current: "", unit: "" }),
  constraints: () => ({ statement: "", severity: "SOFT" }),
  preferences: () => ({ statement: "" }),
};

export function MissionView() {
  const client = getSosClient();
  const isDemo = client.runtime.mode === "fixtures";
  const [active, setActive] = useState<Stage["key"]>("mission");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [dirty, setDirty] = useState(false);
  const [proposed, setProposed] = useState(false);
  const [approvedAt, setApprovedAt] = useState<string | null>(null);
  const [approvedBy, setApprovedBy] = useState<string | null>(null);

  const mission = useResource<Mission>((c) => c.getMission(WORKSPACE_ID), []);
  const revision = useResource<MissionRevision | null>(async (c) => {
    const m = await c.getMission(WORKSPACE_ID);
    const revs = (await c.listMissionRevisions(m.id)).items;
    return revs.find((r) => r.id === m.currentRevisionId) ?? revs[revs.length - 1] ?? null;
  }, []);

  const workingDraft = useMemo<Draft | null>(
    () => draft ?? (revision.data ? draftFromRevision(revision.data) : null),
    [draft, revision.data],
  );

  const update = <K extends keyof Draft>(key: K, index: number, field: string, value: string) => {
    if (!workingDraft) return;
    const next = { ...workingDraft, [key]: workingDraft[key].map((row, i) => (i === index ? { ...row, [field]: value } : row)) };
    setDraft(next as Draft);
    setDirty(true);
    setProposed(false);
    setApprovedAt(null);
  };

  const addRow = (key: keyof Draft) => {
    if (!workingDraft) return;
    setDraft({ ...workingDraft, [key]: [...workingDraft[key], emptyRow[key]()] } as Draft);
    setDirty(true);
    setProposed(false);
    setApprovedAt(null);
  };

  const removeRow = (key: keyof Draft, index: number) => {
    if (!workingDraft) return;
    setDraft({ ...workingDraft, [key]: workingDraft[key].filter((_, i) => i !== index) } as Draft);
    setDirty(true);
    setProposed(false);
    setApprovedAt(null);
  };

  const resetDraft = () => {
    setDraft(revision.data ? draftFromRevision(revision.data) : null);
    setDirty(false);
    setProposed(false);
    setApprovedAt(null);
  };

  const proposeRevision = () => {
    setProposed(true);
    setApprovedAt(null);
  };

  const approveRevision = () => {
    setApprovedAt(new Date().toISOString());
    setApprovedBy(isDemo ? "you (demo owner)" : "you");
  };

  return (
    <div>
      <header className="mb-5">
        <p className="text-xs font-semibold tracking-widest text-teal-700 uppercase">Mission</p>
        <h1 className="mt-1 text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">
          Mission journey
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          Mission → Goals → Outcomes → Stakeholders → Measures → Constraints → Preferences →
          Approve. <strong>You are the mission authority</strong> — no revision is inferred from
          telemetry, and approval is your explicit act.
        </p>
      </header>

      {mission.isLoading || revision.isLoading ? <LoadingState label="Loading mission…" /> : null}
      {mission.error ? <ErrorState error={mission.error} onRetry={mission.refetch} /> : null}
      {revision.error ? <ErrorState error={revision.error} onRetry={revision.refetch} /> : null}

      {mission.data && revision.data && workingDraft ? (
        <div className="grid gap-4 lg:grid-cols-[13rem_1fr]">
          <nav aria-label="Mission journey stages" className="lg:sticky lg:top-20 lg:self-start">
            <ol className="flex gap-2 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible">
              {STAGES.map((stage, index) => {
                const isActive = active === stage.key;
                return (
                  <li key={stage.key} className="shrink-0">
                    <button
                      type="button"
                      onClick={() => setActive(stage.key)}
                      aria-current={isActive ? "step" : undefined}
                      className={`flex min-h-[40px] w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium whitespace-nowrap transition-surface ${
                        isActive
                          ? "bg-teal-50 text-teal-800 ring-1 ring-teal-200"
                          : "text-slate-600 hover:bg-slate-100"
                      }`}
                    >
                      <span
                        aria-hidden="true"
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${
                          isActive ? "bg-teal-700 text-white" : "bg-slate-200 text-slate-600"
                        }`}
                      >
                        {index + 1}
                      </span>
                      {stage.label}
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>

          <div className="min-w-0 space-y-4">
            <Card>
              <CardHeader
                title={mission.data.title}
                description={`Status: ${mission.data.status} · current revision ${revision.data.revision} (approval: ${revision.data.approval.state.toLowerCase()}${revision.data.approval.decidedAt ? ` by ${revision.data.approval.decidedBy} at ${formatTimestamp(revision.data.approval.decidedAt)}` : ""})`}
                actions={isDemo ? <DemoBadge /> : null}
              />
              <CardBody>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {dirty ? <Badge tone="amber">unsaved draft edits (demo-local)</Badge> : <Badge tone="emerald">in sync with current revision</Badge>}
                  {proposed ? <Badge tone="amber">proposed — awaiting approval</Badge> : null}
                  {approvedAt ? (
                    <Badge tone="emerald">
                      approved by {approvedBy} · {formatTimestamp(approvedAt)}
                    </Badge>
                  ) : null}
                </div>
              </CardBody>
            </Card>

            {active === "mission" ? (
              <Card>
                <CardHeader title="Mission" description={STAGES[0].hint} />
                <CardBody>
                  <dl className="divide-y divide-slate-100">
                    <div className="py-2 grid sm:grid-cols-[10rem_1fr] gap-1 sm:gap-3">
                      <dt className="text-xs font-medium uppercase text-slate-500">Title</dt>
                      <dd className="text-sm text-slate-800">{mission.data.title}</dd>
                    </div>
                    <div className="py-2 grid sm:grid-cols-[10rem_1fr] gap-1 sm:gap-3">
                      <dt className="text-xs font-medium uppercase text-slate-500">Status</dt>
                      <dd className="text-sm text-slate-800">{mission.data.status}</dd>
                    </div>
                    <div className="py-2 grid sm:grid-cols-[10rem_1fr] gap-1 sm:gap-3">
                      <dt className="text-xs font-medium uppercase text-slate-500">Authority</dt>
                      <dd className="text-sm text-slate-800">
                        The mission owner (you). Revisions are explicit, versioned, and
                        human-authorized.
                      </dd>
                    </div>
                  </dl>
                </CardBody>
              </Card>
            ) : null}

            {active !== "mission" && active !== "approve" ? (
              <EditableStage
                stageKey={active}
                draft={workingDraft}
                onAdd={addRow}
                onRemove={removeRow}
                onUpdate={update}
              />
            ) : null}

            {active === "approve" ? (
              <Card>
                <CardHeader
                  title="Approve Mission Revision"
                  description="The revision you are about to approve, with who proposed it and when."
                />
                <CardBody>
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <p className="text-sm text-slate-600">
                      Revision <strong>{dirty || proposed ? revision.data.revision + 1 : revision.data.revision}</strong>{" "}
                      {dirty || proposed ? "(your draft)" : "(current)"}
                      {proposed || dirty ? " — proposed by you, requested just now" : ` — requested by ${revision.data.approval.requestedBy}`}
                    </p>
                    <ul className="mt-3 space-y-1 text-sm text-slate-700">
                      <li>Goals: {workingDraft.goals.length}</li>
                      <li>Outcomes: {workingDraft.outcomes.length}</li>
                      <li>Stakeholders: {workingDraft.stakeholders.length}</li>
                      <li>Measures: {workingDraft.measures.length}</li>
                      <li>Constraints: {workingDraft.constraints.length} ({workingDraft.constraints.filter((c) => c.severity === "HARD").length} hard)</li>
                      <li>Preferences: {workingDraft.preferences.length}</li>
                    </ul>
                  </div>
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800" role="note">
                    {isDemo ? (
                      <>
                        <DemoBadge /> Demo mode: approval updates this cockpit&apos;s local state
                        only (clearly demo-labeled). With a configured API this records a real
                        approval — audit event, decidedBy, decidedAt — through{" "}
                        <code className="font-mono">POST /api/v1/missions/{mission.data.id}/revisions</code>.
                        The client never decides approval semantics; it records your explicit act.
                      </>
                    ) : (
                      <>Approving records your explicit authorization with an audit event.</>
                    )}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={proposeRevision} disabled={!dirty || proposed}>
                      Propose revision
                    </Button>
                    <Button variant="primary" onClick={approveRevision} disabled={!proposed || !!approvedAt}>
                      <Check aria-hidden="true" className="h-4 w-4" />
                      Approve Mission Revision
                    </Button>
                    <Button variant="ghost" onClick={resetDraft}>
                      <RotateCcw aria-hidden="true" className="h-4 w-4" />
                      Reset demo edits
                    </Button>
                  </div>
                  {approvedAt ? (
                    <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800" role="status">
                      Approved by <strong>{approvedBy}</strong> at {formatTimestamp(approvedAt)}.
                      {isDemo ? " (Demo-local state; the next reload restores the fixture.)" : ""}
                    </p>
                  ) : null}
                </CardBody>
              </Card>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function EditableStage({
  stageKey,
  draft,
  onAdd,
  onRemove,
  onUpdate,
}: {
  stageKey: Exclude<Stage["key"], "mission" | "approve">;
  draft: Draft;
  onAdd: (key: keyof Draft) => void;
  onRemove: (key: keyof Draft, index: number) => void;
  onUpdate: (key: keyof Draft, index: number, field: string, value: string) => void;
}) {
  const stage = STAGES.find((s) => s.key === stageKey);
  if (!stage) return null;
  const rows = draft[stageKey];
  const fields: Record<string, { label: string; placeholder: string }> = {
    goals: { label: "Rationale", placeholder: "Why this goal matters" },
    outcomes: { label: "Metric", placeholder: "metric id" },
    stakeholders: { label: "Role · Interest", placeholder: "role — what they care about" },
    measures: { label: "Target / Current / Unit", placeholder: "target · current · unit" },
    constraints: { label: "Severity", placeholder: "HARD or SOFT" },
    preferences: { label: "Statement", placeholder: "preference statement" },
  };
  return (
    <Card>
      <CardHeader
        title={stage.label}
        description={stage.hint}
        actions={
          <Button size="sm" variant="secondary" onClick={() => onAdd(stageKey)}>
            <Plus aria-hidden="true" className="h-3.5 w-3.5" />
            Add
          </Button>
        }
      />
      <CardBody className="space-y-3">
        {rows.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            No entries — EMPTY (observed, none). Add one to build this stage.
          </p>
        ) : (
          <ul className="space-y-3">
            {rows.map((row, index) => {
              const record = row as Record<string, string>;
              const statement = record.statement ?? record.name ?? "";
              return (
                <li key={index} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-start gap-2">
                    <label className="min-w-0 flex-1">
                      <span className="sr-only">{`Statement ${index + 1}`}</span>
                      <input
                        value={statement}
                        onChange={(e) => {
                          const field = "statement" in row || "name" in row ? ("statement" in row ? "statement" : "name") : "statement";
                          onUpdate(stageKey, index, field, e.target.value);
                        }}
                        placeholder="statement"
                        className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-800 focus-visible:outline-2 focus-visible:outline-teal-600"
                      />
                    </label>
                    <Button size="sm" variant="ghost" onClick={() => onRemove(stageKey, index)} aria-label={`Remove ${stage.label.toLowerCase()} ${index + 1}`}>
                      <Trash2 aria-hidden="true" className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  {stageKey === "stakeholders" ? (
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <input
                        value={(row as { name: string; role: string; interest: string }).name}
                        onChange={(e) => onUpdate(stageKey, index, "name", e.target.value)}
                        placeholder="name"
                        aria-label={`Name ${index + 1}`}
                        className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600"
                      />
                      <input
                        value={(row as { name: string; role: string; interest: string }).role}
                        onChange={(e) => onUpdate(stageKey, index, "role", e.target.value)}
                        placeholder="role"
                        aria-label={`Role ${index + 1}`}
                        className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600"
                      />
                      <input
                        value={(row as { name: string; role: string; interest: string }).interest}
                        onChange={(e) => onUpdate(stageKey, index, "interest", e.target.value)}
                        placeholder="interest"
                        aria-label={`Interest ${index + 1}`}
                        className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600 sm:col-span-2"
                      />
                    </div>
                  ) : null}
                  {stageKey === "measures" ? (
                    <div className="mt-2 grid gap-2 sm:grid-cols-3">
                      {(["target", "current", "unit"] as const).map((field) => (
                        <input
                          key={field}
                          value={(row as Record<string, string>)[field] ?? ""}
                          onChange={(e) => onUpdate(stageKey, index, field, e.target.value)}
                          placeholder={field}
                          aria-label={`${field} ${index + 1}`}
                          className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600"
                        />
                      ))}
                    </div>
                  ) : null}
                  {stageKey === "constraints" ? (
                    <div className="mt-2 flex gap-2">
                      {(["HARD", "SOFT"] as const).map((severity) => (
                        <label key={severity} className="inline-flex cursor-pointer items-center gap-1.5 text-xs font-medium text-slate-600">
                          <input
                            type="radio"
                            name={`severity-${index}`}
                            checked={(row as { severity: string }).severity === severity}
                            onChange={() => onUpdate(stageKey, index, "severity", severity)}
                            className="accent-teal-700"
                          />
                          {severity}
                        </label>
                      ))}
                    </div>
                  ) : null}
                  {stageKey === "goals" ? (
                    <input
                      value={(row as { statement: string; rationale: string }).rationale}
                      onChange={(e) => onUpdate(stageKey, index, "rationale", e.target.value)}
                      placeholder="rationale"
                      aria-label={`Rationale ${index + 1}`}
                      className="mt-2 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600"
                    />
                  ) : null}
                  {stageKey === "outcomes" ? (
                    <input
                      value={(row as { statement: string; metric: string }).metric}
                      onChange={(e) => onUpdate(stageKey, index, "metric", e.target.value)}
                      placeholder="metric id"
                      aria-label={`Metric ${index + 1}`}
                      className="mt-2 w-full rounded-md border border-slate-300 px-2.5 py-1.5 font-mono text-xs focus-visible:outline-2 focus-visible:outline-teal-600"
                    />
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-xs text-slate-400">{fields[stageKey].label} fields edit inline.</p>
      </CardBody>
    </Card>
  );
}
