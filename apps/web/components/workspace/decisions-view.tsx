"use client";

import { useState } from "react";
import { AlertCircle, Check, FileQuestion, X } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import { useAskResponses } from "@/hooks/use-demo-state";
import { getSosClient } from "@/lib/api/client";
import type { Decision } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/key-value";
import { Timeline, TimelineItem } from "@/components/ui/timeline";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatTimestamp } from "@/lib/format";

const ACTION_TONES: Record<Decision["action"], "teal" | "emerald" | "amber" | "rose" | "slate" | "orange"> = {
  ACT: "teal",
  EXPERIMENT: "emerald",
  GATHER_EVIDENCE: "amber",
  ASK: "amber",
  REJECT: "rose",
  ROLLBACK: "orange",
};

export function DecisionsView() {
  const decisions = useResource<Decision[]>((c) => c.listDecisions().then((r) => r.items), []);
  const ask = useAskResponses();
  const client = getSosClient();
  const isDemo = client.runtime.mode === "fixtures";
  const [filter, setFilter] = useState<Decision["action"] | "ALL">("ALL");

  const items = (decisions.data ?? []).filter((d) => filter === "ALL" || d.action === filter);

  return (
    <div>
      <PageHeader
        eyebrow="Decisions"
        title="Decision panel"
        description="Every consequential action shows its governing decision: why, evidence, authority, expected impact, risk, blast radius, reversibility and required approvals. ASK is a first-class state — when autonomy is insufficient, the exact decision needed is surfaced to the owner."
      />

      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by decision action">
        <button
          type="button"
          onClick={() => setFilter("ALL")}
          aria-pressed={filter === "ALL"}
          className={`inline-flex min-h-[32px] items-center rounded-full border px-3 text-xs font-medium transition-surface ${
            filter === "ALL" ? "border-teal-300 bg-teal-50 text-teal-800" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
          }`}
        >
          All actions
        </button>
        {(["ASK", "EXPERIMENT", "GATHER_EVIDENCE", "REJECT", "ACT", "ROLLBACK"] as const).map((action) => (
          <button
            key={action}
            type="button"
            onClick={() => setFilter(action)}
            aria-pressed={filter === action}
            className={`inline-flex min-h-[32px] items-center rounded-full border px-3 text-xs font-medium transition-surface ${
              filter === action ? "border-teal-300 bg-teal-50 text-teal-800" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            }`}
          >
            {action.replaceAll("_", " ")}
          </button>
        ))}
      </div>

      {decisions.isLoading ? <LoadingState label="Loading decisions…" /> : null}
      {decisions.error ? <ErrorState error={decisions.error} onRetry={decisions.refetch} /> : null}
      {decisions.data && !decisions.isLoading ? (
        items.length === 0 ? (
          <EmptyState title="No decisions match the filter" hint="Clear the filter to see all governing decisions." />
        ) : (
          <div className="space-y-4">
            {items.map((decision) =>
              decision.action === "ASK" && decision.status === "AWAITING_OWNER" ? (
                <AskPanel key={decision.id} decision={decision} ask={ask} isDemo={isDemo} />
              ) : (
                <DecisionPanel key={decision.id} decision={decision} isDemo={isDemo} />
              ),
            )}
          </div>
        )
      ) : null}

      {ask.authorizations.length > 0 ? (
        <div className="mt-6">
          <h2 className="text-sm font-semibold tracking-wide text-slate-500 uppercase">
            Demo authorizations (this session)
          </h2>
          <ul className="mt-2 space-y-2">
            {ask.authorizations.map((auth) => (
              <li key={auth.id} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <DemoBadge /> <span className="font-mono">{auth.id}</span> — {auth.decision} ·{" "}
                {auth.scope} · {formatTimestamp(auth.createdAt)} (demo-local, not persisted)
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function DecisionPanel({ decision, isDemo }: { decision: Decision; isDemo: boolean }) {
  return (
    <Card as="article">
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone={ACTION_TONES[decision.action]}>DECISION: {decision.action}</Badge>
            <span className="text-sm font-semibold">{decision.candidateName ?? decision.id}</span>
            <Badge tone={decision.status === "EXECUTED" ? "slate" : "amber"}>{decision.status.toLowerCase().replaceAll("_", " ")}</Badge>
          </span>
        }
        description={<time>{formatTimestamp(decision.createdAt)}</time>}
        actions={isDemo ? <DemoBadge /> : null}
      />
      <CardBody>
        <dl className="divide-y divide-slate-100">
          <Field label="Why?">
            <p className="leading-relaxed">{decision.rationale}</p>
          </Field>
          <Field label="Evidence">
            <EvidenceRefs refs={decision.evidenceRefs} />
          </Field>
          <Field label="Authority">
            <p>
              {decision.authoritySnapshot.principal} — {decision.authoritySnapshot.autonomy}
            </p>
            <ul className="mt-1 list-disc pl-4 text-xs text-slate-500">
              {decision.authoritySnapshot.constraints.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </Field>
          <Field label="Expected impact">
            <p>{decision.expectedImpact}</p>
          </Field>
          <Field label="Risk">
            <span className="flex items-center gap-2">
              <Badge tone={decision.risk.level === "HIGH" ? "rose" : decision.risk.level === "MEDIUM" ? "amber" : "emerald"}>
                {decision.risk.level}
              </Badge>
              <span>{decision.risk.summary}</span>
            </span>
          </Field>
          <Field label="Blast radius">
            <span className="flex items-center gap-2">
              <Badge tone={decision.blastRadius.level === "HIGH" ? "rose" : decision.blastRadius.level === "MEDIUM" ? "amber" : "emerald"}>
                {decision.blastRadius.level}
              </Badge>
              <span>{decision.blastRadius.description}</span>
            </span>
          </Field>
          <Field label="Reversibility">
            <p>{decision.reversibility}</p>
          </Field>
          <Field label="Required approvals">
            {decision.requiredApprovals.length === 0 ? (
              <p className="text-xs text-slate-500">None required for this action.</p>
            ) : (
              <ul className="space-y-1">
                {decision.requiredApprovals.map((approval) => (
                  <li key={`${approval.approver}-${approval.scope}`} className="flex items-center gap-2 text-xs">
                    <Badge
                      tone={
                        approval.state === "GRANTED"
                          ? "emerald"
                          : approval.state === "DENIED"
                            ? "rose"
                            : "amber"
                      }
                    >
                      {approval.state.toLowerCase()}
                    </Badge>
                    <span className="font-mono">{approval.approver}</span>
                    <span className="text-slate-500">{approval.scope}</span>
                  </li>
                ))}
              </ul>
            )}
          </Field>
        </dl>
      </CardBody>
    </Card>
  );
}

export function AskPanel({
  decision,
  ask,
  isDemo,
}: {
  decision: Decision;
  ask: ReturnType<typeof useAskResponses>;
  isDemo: boolean;
}) {
  const [note, setNote] = useState("");
  const payload = decision.askPayload;
  const response = ask.responses[decision.id];

  return (
    <Card as="article" className="border-amber-300 ring-1 ring-amber-200">
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone="amber">
              <AlertCircle aria-hidden="true" className="h-3 w-3" />
              DECISION: ASK — awaiting owner action
            </Badge>
            <span className="text-sm font-semibold">{decision.candidateName ?? decision.id}</span>
            {isDemo ? <DemoBadge /> : null}
          </span>
        }
        description={
          payload ? (
            <>
              <time>{formatTimestamp(decision.createdAt)}</time> — insufficient autonomy for
              autonomous action; the owner decides.
            </>
          ) : null
        }
      />
      <CardBody>
        {payload ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <h4 className="flex items-center gap-2 text-sm font-bold text-amber-900">
                <FileQuestion aria-hidden="true" className="h-4 w-4" />
                Exact decision requested
              </h4>
              <p className="mt-1.5 text-sm text-amber-900">{payload.decision}</p>
            </div>

            <section aria-label="Alternatives with expected outcomes and trade-offs">
              <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                Alternatives
              </h4>
              <ul className="mt-2 grid gap-2 lg:grid-cols-3">
                {payload.alternatives.map((alt) => (
                  <li key={alt.label} className="rounded-lg border border-slate-200 bg-white p-3">
                    <p className="text-sm font-semibold text-slate-800">{alt.label}</p>
                    <p className="mt-1 text-xs text-slate-600">{alt.expectedOutcome}</p>
                    <p className="mt-1.5 text-xs font-medium text-slate-500">Trade-offs:</p>
                    <ul className="list-disc pl-4 text-xs text-slate-500">
                      {alt.tradeoffs.map((t) => (
                        <li key={t}>{t}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            </section>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                  Evidence quality
                </h4>
                <p className="mt-1 text-sm text-slate-700">
                  <Badge tone={payload.evidenceQuality.grade === "STRONG" ? "emerald" : payload.evidenceQuality.grade === "MODERATE" ? "amber" : "rose"}>
                    {payload.evidenceQuality.grade}
                  </Badge>{" "}
                  {payload.evidenceQuality.note}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                  Uncertainty
                </h4>
                <p className="mt-1 text-sm text-slate-700">{payload.uncertainty}</p>
              </div>
            </div>

            <section aria-label="Decision context">
              <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                <Field label="Why ASK?">
                  <p className="leading-relaxed">{decision.rationale}</p>
                </Field>
                <Field label="Expected impact">
                  <p>{decision.expectedImpact}</p>
                </Field>
                <Field label="Risk / blast radius">
                  <p>
                    {decision.risk.level} — {decision.risk.summary}
                  </p>
                  <p className="mt-1">{decision.blastRadius.description}</p>
                </Field>
                <Field label="Reversibility">{decision.reversibility}</Field>
                <Field label="Required approvals">
                  <ul className="space-y-1">
                    {decision.requiredApprovals.map((approval) => (
                      <li key={`${approval.approver}-${approval.scope}`} className="flex items-center gap-2 text-xs">
                        <Badge tone={approval.state === "PENDING" ? "amber" : approval.state === "GRANTED" ? "emerald" : "rose"}>
                          {approval.state.toLowerCase()}
                        </Badge>
                        <span className="font-mono">{approval.approver}</span>
                        <span className="text-slate-500">{approval.scope}</span>
                      </li>
                    ))}
                  </ul>
                </Field>
              </dl>
            </section>

            <section aria-label="Owner actions">
              <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                Your decision
              </h4>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() =>
                    ask.respond(
                      decision.id,
                      "approved",
                      "Approved: shadow experiment authorized (demo-local record).",
                      new Date().toISOString(),
                    )
                  }
                  disabled={response?.kind === "approved"}
                >
                  <Check aria-hidden="true" className="h-3.5 w-3.5" />
                  Approve
                </Button>
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() =>
                    ask.respond(
                      decision.id,
                      "rejected",
                      "Rejected: the owner declined this alternative (demo-local record).",
                      new Date().toISOString(),
                    )
                  }
                  disabled={response?.kind === "rejected"}
                >
                  <X aria-hidden="true" className="h-3.5 w-3.5" />
                  Reject
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    ask.respond(
                      decision.id,
                      "evidence",
                      note.trim().length > 0
                        ? `Evidence provided: ${note.trim()} (demo-local).`
                        : "Provide evidence text first — nothing was sent.",
                      new Date().toISOString(),
                    )
                  }
                >
                  Provide evidence
                </Button>
              </div>
              <label htmlFor={`evidence-note-${decision.id}`} className="mt-3 block text-xs font-medium text-slate-600">
                Evidence you want to attach (optional)
              </label>
              <textarea
                id={`evidence-note-${decision.id}`}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="e.g. Finance confirmed the peak-week traces cover the seasonal pattern…"
                className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm focus-visible:outline-2 focus-visible:outline-teal-600"
              />
              {response ? (
                <p
                  className={`mt-3 rounded-lg border p-3 text-sm ${
                    response.kind === "approved"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : response.kind === "rejected"
                        ? "border-rose-200 bg-rose-50 text-rose-800"
                        : "border-slate-200 bg-slate-50 text-slate-700"
                  }`}
                  role="status"
                >
                  {response.message}
                  {isDemo ? " Demo mode: this records locally in this session only — no API call is made, nothing is fabricated as persisted." : ""}
                </p>
              ) : (
                <p className="mt-3 text-xs text-slate-400">
                  {isDemo
                    ? "Demo mode: owner actions record demo-local state so the flow is demonstrable; with a configured API they POST authorizations and audit events."
                    : "Your response records an authorization and an audit event."}
                </p>
              )}
            </section>
          </div>
        ) : (
          <p className="text-sm text-slate-600">
            ASK decision without payload — the decision detail is unavailable (rendered honestly
            rather than guessed).
          </p>
        )}
      </CardBody>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-0.5 py-2.5 sm:grid-cols-[10rem_1fr] sm:gap-3">
      <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className="text-sm text-slate-800">{children}</dd>
    </div>
  );
}

function EvidenceRefs({ refs }: { refs: string[] }) {
  return refs.length === 0 ? (
    <p className="text-xs text-slate-500">No evidence references (explicitly none).</p>
  ) : (
    <ul className="space-y-0.5">
      {refs.map((ref) => (
        <li key={ref}>
          <a
            href={`/workspace/evidence#evidence-${ref}`}
            className="font-mono text-xs text-teal-700 underline decoration-teal-300 transition-surface hover:text-teal-800"
          >
            {ref}
          </a>
        </li>
      ))}
    </ul>
  );
}

export function DecisionTrailTimeline({ decisions }: { decisions: Decision[] }) {
  return (
    <Timeline>
      {decisions
        .slice()
        .sort((a, b) => a.createdAt.localeCompare(b.createdAt))
        .map((d) => (
          <TimelineItem
            key={d.id}
            at={formatTimestamp(d.createdAt)}
            title={`${d.action} — ${d.candidateName ?? d.id}`}
            badge={<Badge tone={ACTION_TONES[d.action]}>{d.status.toLowerCase().replaceAll("_", " ")}</Badge>}
          >
            {d.rationale}
          </TimelineItem>
        ))}
    </Timeline>
  );
}
