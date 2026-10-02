/**
 * Deterministic formatting helpers (no locale drift between server and
 * client rendering; UTC throughout).
 */

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const DATE_ONLY = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  year: "numeric",
  month: "short",
  day: "2-digit",
});

export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${DATE_TIME.format(date)} UTC`;
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return DATE_ONLY.format(date);
}

/** Shorten a revision/commit hash for display while keeping it identifiable. */
export function shortRevision(revision: string, keep = 10): string {
  if (revision === "unknown") return "unknown";
  return revision.length > keep ? `${revision.slice(0, keep)}…` : revision;
}

/** Render confidence as an honest percentage; null stays "—" (not 0%). */
export function formatConfidence(confidence: number | null): string {
  if (confidence === null) return "—";
  return `${Math.round(confidence * 100)}%`;
}

/** Byte formatting for artifact sizes. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
