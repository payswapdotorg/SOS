"use client";

import { Brain, BookOpen } from "lucide-react";
import { useResource } from "@/hooks/use-resource";
import type { LearningRecord, MemoryEntry } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/key-value";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";

export function MemoryView() {
  const learning = useResource<LearningRecord[]>((c) => c.listLearningRecords().then((r) => r.items), []);
  const memory = useResource<MemoryEntry[]>((c) => c.listMemoryEntries().then((r) => r.items), []);

  return (
    <div>
      <PageHeader
        eyebrow="Memory"
        title="Learning & architecture memory"
        description="Durable experience: context, candidate, predicted vs actual effects, uncertainty, verdict and lessons. Memory is a prior — never proof."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="learning-heading">
          <h2 id="learning-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-500 uppercase">
            <BookOpen aria-hidden="true" className="h-4 w-4 text-teal-700" />
            Learning records
          </h2>
          {learning.isLoading ? <LoadingState label="Loading learning records…" /> : null}
          {learning.error ? <ErrorState error={learning.error} onRetry={learning.refetch} /> : null}
          {learning.data && !learning.isLoading ? (
            learning.data.length === 0 ? (
              <EmptyState title="No learning records yet" hint="Records appear after interventions complete." />
            ) : (
              <div className="space-y-4">
                {learning.data.map((record) => (
                  <LearningCard key={record.id} record={record} />
                ))}
              </div>
            )
          ) : null}
        </section>

        <section aria-labelledby="memory-heading">
          <h2 id="memory-heading" className="mb-3 flex items-center gap-2 text-sm font-semibold tracking-wide text-slate-500 uppercase">
            <Brain aria-hidden="true" className="h-4 w-4 text-teal-700" />
            Architecture memory
          </h2>
          {memory.isLoading ? <LoadingState label="Loading memory entries…" /> : null}
          {memory.error ? <ErrorState error={memory.error} onRetry={memory.refetch} /> : null}
          {memory.data && !memory.isLoading ? (
            memory.data.length === 0 ? (
              <EmptyState title="No memory entries yet" hint="Entries accumulate from every meaningful intervention." />
            ) : (
              <div className="space-y-4">
                {memory.data.map((entry) => (
                  <MemoryCard key={entry.id} entry={entry} />
                ))}
              </div>
            )
          ) : null}
        </section>
      </div>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const tone =
    verdict === "CONFIRMED"
      ? "emerald"
      : verdict === "PARTIALLY_CONFIRMED"
        ? "amber"
        : verdict === "REFUTED"
          ? "rose"
          : "slate";
  return <Badge tone={tone}>{verdict.toLowerCase().replaceAll("_", " ")}</Badge>;
}

function LearningCard({ record }: { record: LearningRecord }) {
  return (
    <Card as="article">
      <CardHeader title={record.context} actions={<VerdictBadge verdict={record.verdict} />} />
      <CardBody className="space-y-3">
        <Section label="Candidate">
          <p className="text-sm text-slate-700">{record.candidate}</p>
        </Section>
        <Section label="Predicted effects">
          <ul className="list-disc pl-4 text-sm text-slate-600">
            {record.predictedEffects.map((effect) => (
              <li key={effect}>{effect}</li>
            ))}
          </ul>
        </Section>
        <Section label="Actual effects">
          <ul className="list-disc pl-4 text-sm text-slate-600">
            {record.actualEffects.map((effect) => (
              <li key={effect}>{effect}</li>
            ))}
          </ul>
        </Section>
        <Section label="Uncertainty">
          <p className="text-sm text-slate-600">{record.uncertainty}</p>
        </Section>
        <Section label="Lessons">
          <ul className="list-disc pl-4 text-sm text-slate-700">
            {record.lessons.map((lesson) => (
              <li key={lesson}>{lesson}</li>
            ))}
          </ul>
        </Section>
      </CardBody>
    </Card>
  );
}

function MemoryCard({ entry }: { entry: MemoryEntry }) {
  return (
    <Card as="article">
      <CardHeader
        title={entry.context}
        actions={
          <span className="flex items-center gap-2">
            <VerdictBadge verdict={entry.verdict} />
            {entry.verdict === "PENDING" ? <DemoBadge /> : null}
          </span>
        }
      />
      <CardBody className="space-y-3">
        <Section label="Candidate">
          <p className="text-sm text-slate-700">{entry.candidate}</p>
        </Section>
        <Section label="Predicted effects">
          <ul className="list-disc pl-4 text-sm text-slate-600">
            {entry.predictedEffects.map((effect) => (
              <li key={effect}>{effect}</li>
            ))}
          </ul>
        </Section>
        <Section label="Actual effects">
          {entry.actualEffects.length === 0 ? (
            <p className="text-sm text-slate-500">
              None yet — experiment still running. This stays EMPTY (not invented) until evidence
              lands.
            </p>
          ) : (
            <ul className="list-disc pl-4 text-sm text-slate-600">
              {entry.actualEffects.map((effect) => (
                <li key={effect}>{effect}</li>
              ))}
            </ul>
          )}
        </Section>
        <Section label="Uncertainty">
          <p className="text-sm text-slate-600">{entry.uncertainty}</p>
        </Section>
        <Section label="Lessons">
          <ul className="list-disc pl-4 text-sm text-slate-700">
            {entry.lessons.map((lesson) => (
              <li key={lesson}>{lesson}</li>
            ))}
          </ul>
        </Section>
      </CardBody>
    </Card>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section aria-label={label}>
      <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{label}</h4>
      <div className="mt-1">{children}</div>
    </section>
  );
}
