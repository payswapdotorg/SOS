"use client";

import { useState } from "react";
import type { DemoDataset } from "@/lib/api/types";
import { demo } from "@/lib/fixtures/demo";
import type {
  Authorization,
  ActivityEvent,
} from "@/lib/api/types";

/**
 * Demo-mode interaction state. Fixture mode has no backend, so owner actions
 * (mission approval, ASK responses) are expressed as LOCAL demo state —
 * clearly labeled demo, never presented as persisted truth. In API mode these
 * flows POST to the contract endpoints instead (wired when PUB-01/PUB-04
 * land; the buttons explain the demo behavior honestly).
 */

export interface AskActionFeedback {
  kind: "approved" | "rejected" | "evidence" | "info";
  message: string;
}

export function useDemoDataset(): DemoDataset {
  return demo;
}

/** Local approval state for the mission journey editor (demo). */
export function useMissionApproval() {
  const [state, setState] = useState<"PROPOSED" | "APPROVED">("APPROVED");
  const [decidedAt, setDecidedAt] = useState<string | null>(
    demo.missionRevisions[1]?.approval.decidedAt ?? null,
  );
  const approve = (isoNow: string) => {
    setState("APPROVED");
    setDecidedAt(isoNow);
  };
  const propose = () => {
    setState("PROPOSED");
    setDecidedAt(null);
  };
  return { state, decidedAt, approve, propose };
}

/** Local ASK response state (demo) + generated authorization/activity rows. */
export function useAskResponses() {
  const [responses, setResponses] = useState<Record<string, AskActionFeedback>>({});
  const [authorizations, setAuthorizations] = useState<Authorization[]>([]);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);

  const respond = (
    decisionId: string,
    kind: AskActionFeedback["kind"],
    message: string,
    atIso: string,
  ) => {
    setResponses((prev) => ({ ...prev, [decisionId]: { kind, message } }));
    if (kind === "approved" || kind === "rejected") {
      setAuthorizations((prev) => [
        {
          id: `auth_demo_${decisionId}_${kind}`,
          decisionId,
          principal: "user_owner",
          scope: "experiment.approve (shadow) — demo action",
          decision: kind === "approved" ? "GRANTED" : "DENIED",
          createdAt: atIso,
        },
        ...prev,
      ]);
      setActivity((prev) => [
        {
          id: `act_demo_${decisionId}_${kind}`,
          actor: "user_owner",
          action: kind === "approved" ? "authorization.granted" : "authorization.denied",
          target: decisionId,
          timestamp: atIso,
          meta: { mode: "demo", source: "cockpit demo action" },
        },
        ...prev,
      ]);
    }
  };

  return { responses, authorizations, activity, respond };
}

/** Deterministic "now" for demo stamps (client-side local clock, labeled demo). */
export function demoNow(): string {
  return new Date().toISOString();
}
