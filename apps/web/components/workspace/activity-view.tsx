"use client";

import { useResource } from "@/hooks/use-resource";
import { useAskResponses } from "@/hooks/use-demo-state";
import type { ActivityEvent } from "@/lib/api/types";
import { Badge, DemoBadge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/key-value";
import { Timeline, TimelineItem } from "@/components/ui/timeline";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { formatTimestamp } from "@/lib/format";

export function ActivityView() {
  const activity = useResource<ActivityEvent[]>((c) => c.listActivity().then((r) => r.items), []);
  const ask = useAskResponses();

  const merged = [
    ...(activity.data ?? []),
    ...ask.activity,
  ]
    .slice()
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  return (
    <div>
      <PageHeader
        eyebrow="Activity"
        title="Audit trail"
        description="Chronological consequential actions — actor, action, target, timestamp, metadata. Every mutation in a real deployment carries one of these; the demo trail mirrors the seed story."
      />

      {activity.isLoading ? <LoadingState label="Loading activity…" /> : null}
      {activity.error ? <ErrorState error={activity.error} onRetry={activity.refetch} /> : null}
      {activity.data && !activity.isLoading ? (
        activity.data.length === 0 && ask.activity.length === 0 ? (
          <EmptyState title="No activity recorded yet" hint="Consequential actions appear here as they happen." />
        ) : (
          <Card>
            <CardHeader
              title="Event stream"
              description="Newest first. Demo-local entries (owner ASK actions from this session) are badged."
              actions={<DemoBadge />}
            />
            <CardBody>
              <div className="scroll-area pr-2">
                <Timeline>
                  {merged.map((event) => {
                    const isDemoLocal = event.id.startsWith("act_demo_");
                    return (
                      <TimelineItem
                        key={event.id}
                        at={formatTimestamp(event.timestamp)}
                        title={`${event.actor} — ${event.action}`}
                        badge={
                          <span className="flex items-center gap-2">
                            <Badge tone={isDemoLocal ? "amber" : "slate"}>{event.target}</Badge>
                            {isDemoLocal ? <DemoBadge /> : null}
                          </span>
                        }
                      >
                        <dl className="flex flex-wrap gap-x-4 gap-y-0.5">
                          {Object.entries(event.meta).map(([key, value]) => (
                            <div key={key} className="text-xs text-slate-500">
                              <dt className="inline font-medium">{key}: </dt>
                              <dd className="inline font-mono">{value}</dd>
                            </div>
                          ))}
                        </dl>
                      </TimelineItem>
                    );
                  })}
                </Timeline>
              </div>
            </CardBody>
          </Card>
        )
      ) : null}
    </div>
  );
}
