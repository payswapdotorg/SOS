import { Badge } from "./badge";
import { TRUTH_STATE_LABELS, type TruthState } from "@/lib/api/types";

/**
 * Truth-state rendering — six distinct, honest states (architecture
 * invariant 6; contract §A.6). Never map a state to another; never render
 * success for failed/unknown. Each state gets its own tone AND glyph so the
 * distinction survives color-blindness and greyscale.
 */

const TONES: Record<TruthState, { tone: Parameters<typeof Badge>[0]["tone"]; glyph: string }> = {
  SUCCESS: { tone: "emerald", glyph: "●" },
  EMPTY: { tone: "slate", glyph: "○" },
  FAILED: { tone: "rose", glyph: "✕" },
  UNKNOWN: { tone: "zinc", glyph: "?" },
  UNSUPPORTED: { tone: "orange", glyph: "⊘" },
  UNAVAILABLE: { tone: "amber", glyph: "⚠" },
};

export function TruthStatePill({ state, withLabel = true }: { state: TruthState; withLabel?: boolean }) {
  const { tone, glyph } = TONES[state];
  return (
    <Badge tone={tone} title={`Truth state: ${TRUTH_STATE_LABELS[state]}`}>
      <span aria-hidden="true">{glyph}</span>
      {withLabel ? <span>{state}</span> : null}
    </Badge>
  );
}

/** Generic lifecycle/status pill (jobs, experiments, approvals, verdicts). */
export function LifecyclePill({ label, tone = "slate" }: { label: string; tone?: Parameters<typeof Badge>[0]["tone"] }) {
  return <Badge tone={tone}>{label.replaceAll("_", " ")}</Badge>;
}

export function VerdictPill({ verdict }: { verdict: string }) {
  const tone =
    verdict === "PASS"
      ? "emerald"
      : verdict === "CONDITIONAL_PASS"
        ? "amber"
        : verdict === "FAIL"
          ? "rose"
          : "slate";
  return <Badge tone={tone}>{verdict.replaceAll("_", " ")}</Badge>;
}
