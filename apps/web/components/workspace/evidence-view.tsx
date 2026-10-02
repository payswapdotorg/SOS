"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { FileSearch } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import type { Evidence, EvidenceKind, TruthState } from "@/lib/api/types";
import { EVIDENCE_KINDS, EVIDENCE_KIND_LABELS, TRUTH_STATES } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/key-value";
import { TruthStatePill } from "@/components/ui/state-pill";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatConfidence, formatTimestamp, shortRevision } from "@/lib/format";

export function EvidenceView() {
  const evidence = useResource<Evidence[]>((c) => c.listEvidence().then((r) => r.items), []);
  const [kind, setKind] = useState<EvidenceKind | "ALL">("ALL");
  const [status, setStatus] = useState<TruthState | "ALL">("ALL");

  const filtered = useMemo(() => {
    const items = evidence.data ?? [];
    return items.filter(
      (e) => (kind === "ALL" || e.kind === kind) && (status === "ALL" || e.status === status),
    );
  }, [evidence.data, kind, status]);

  const counts = useMemo(() => {
    const items = evidence.data ?? [];
    return TRUTH_STATES.reduce<Record<string, number>>((acc, state) => {
      acc[state] = items.filter((e) => e.status === state).length;
      return acc;
    }, {});
  }, [evidence.data]);

  return (
    <div>
      <PageHeader
        eyebrow="Evidence"
        title="Evidence explorer"
        description="Seven evidence kinds, six truth states, honest provenance. Every item keeps its exact revision, related system state and confidence — failures and unknowns stay failures and unknowns."
      />

      <Card>
        <CardHeader title="Filters" description="Filter by kind and truth state — the state counts below are live." />
        <CardBody>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by evidence kind">
            <FilterChip label="All kinds" active={kind === "ALL"} onClick={() => setKind("ALL")} />
            {EVIDENCE_KINDS.map((k) => (
              <FilterChip
                key={k}
                label={EVIDENCE_KIND_LABELS[k]}
                active={kind === k}
                onClick={() => setKind(k)}
              />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2" role="group" aria-label="Filter by truth state">
            <FilterChip label="All states" active={status === "ALL"} onClick={() => setStatus("ALL")} />
            {TRUTH_STATES.map((state) => (
              <button
                key={state}
                type="button"
                onClick={() => setStatus(status === state ? "ALL" : state)}
                aria-pressed={status === state}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-surface ${
                  status === state
                    ? "border-teal-300 bg-teal-50 text-teal-800"
                    : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                <TruthStatePill state={state} withLabel={false} />
                {state}
                <span className="text-slate-400">{counts[state] ?? 0}</span>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="mt-4">
        {evidence.isLoading ? <LoadingState label="Loading evidence…" /> : null}
        {evidence.error ? <ErrorState error={evidence.error} onRetry={evidence.refetch} /> : null}
        {evidence.data && !evidence.isLoading ? (
          filtered.length === 0 ? (
            <EmptyState
              title="No evidence matches the current filters"
              hint="This is a real EMPTY result for the filtered view — clear a filter to see the rest."
            />
          ) : (
            <ul className="space-y-3">
              {filtered.map((item) => (
                <EvidenceCard key={item.id} item={item} />
              ))}
            </ul>
          )
        ) : null}
      </div>
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex min-h-[32px] items-center rounded-full border px-3 text-xs font-medium transition-surface ${
        active
          ? "border-teal-300 bg-teal-50 text-teal-800"
          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
      }`}
    >
      {label}
    </button>
  );
}

export function EvidenceCard({ item }: { item: Evidence }) {
  return (
    <Card as="article">
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <FileSearch aria-hidden="true" className="h-4 w-4 text-teal-700" />
            <span className="font-mono text-sm">{item.id}</span>
            <Badge tone="slate">{EVIDENCE_KIND_LABELS[item.kind]}</Badge>
          </span>
        }
        description={item.provenance}
        actions={<TruthStatePill state={item.status} />}
        id={`evidence-${item.id}`}
      />
      <CardBody>
        <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
          <Row label="Timestamp">
            <time>{formatTimestamp(item.timestamp)}</time>
          </Row>
          <Row label="Exact revision" mono>
            {shortRevision(item.sourceRevision, 16)}
          </Row>
          <Row label="Related system state" mono>
            {item.relatedSystemState}
          </Row>
          <Row label="Confidence">
            {formatConfidence(item.confidence)}
            {item.confidenceNote ? (
              <span className="ml-1 text-xs text-slate-500">— {item.confidenceNote}</span>
            ) : null}
          </Row>
        </dl>
        {item.artifactRef ? (
          <p className="mt-3 border-t border-slate-100 pt-3">
            <Link
              href={item.artifactRef.signedUrl}
              className="font-mono text-xs text-teal-700 underline decoration-teal-300 transition-surface hover:text-teal-800"
            >
              {item.artifactRef.name}
            </Link>
            <span className="ml-2 text-xs text-slate-400">
              artifact · signed URL ({item.artifactRef.mediaType})
            </span>
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Row({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="py-0.5">
      <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className={`text-sm text-slate-800 ${mono ? "font-mono text-xs break-all" : ""}`}>
        {children}
      </dd>
    </div>
  );
}
