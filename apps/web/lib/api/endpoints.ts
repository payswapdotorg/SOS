/**
 * The `/api/v1` endpoint map (directive §7, contract C.1).
 *
 * Every path here is RELATIVE (starts with `/api/v1`); the client joins it
 * with the configured API base (same-origin by default). No absolute URL
 * ever appears in this package (law §8 — the base comes only from env).
 */

const V = "/api/v1";

export const endpoints = {
  health: () => `${V}/health`,
  me: () => `${V}/me`,
  auth: {
    /** PUB-04 wires the real flow; the sign-in route references this path. */
    githubStart: () => `${V}/auth/github/start`,
    githubCallback: () => `${V}/auth/github/callback`,
    logout: () => `${V}/auth/logout`,
  },
  workspaces: () => `${V}/workspaces`,
  workspace: (id: string) => `${V}/workspaces/${id}`,
  missions: () => `${V}/missions`,
  mission: (id: string) => `${V}/missions/${id}`,
  missionRevisions: (missionId: string) => `${V}/missions/${missionId}/revisions`,
  missionRevision: (missionId: string, revisionId: string) =>
    `${V}/missions/${missionId}/revisions/${revisionId}`,
  systems: () => `${V}/systems`,
  system: (id: string) => `${V}/systems/${id}`,
  systemRecovery: (id: string) => `${V}/systems/${id}/recovery`,
  systemArchitecture: (id: string) => `${V}/systems/${id}/architecture`,
  evidence: () => `${V}/evidence`,
  hypotheses: () => `${V}/hypotheses`,
  candidates: () => `${V}/candidates`,
  candidate: (id: string) => `${V}/candidates/${id}`,
  assurance: () => `${V}/assurance`,
  assuranceRun: (id: string) => `${V}/assurance/${id}`,
  decisions: () => `${V}/decisions`,
  decision: (id: string) => `${V}/decisions/${id}`,
  authorizations: () => `${V}/authorizations`,
  experiments: () => `${V}/experiments`,
  experiment: (id: string) => `${V}/experiments/${id}`,
  executions: () => `${V}/executions`,
  execution: (id: string) => `${V}/executions/${id}`,
  learning: () => `${V}/learning`,
  memory: () => `${V}/memory`,
  /**
   * Audit-event collection (Activity surface). Directive §7 does not spell
   * this path out; contract §C.2 mandates persisted audit events (actor,
   * action, target, timestamp, meta) for every mutation. This path is the
   * client's provisional reference, to be reconciled when PUB-01 finalizes
   * the wire surface — disclosed in the PUB-02 checkpoint.
   */
  audit: () => `${V}/audit`,
  jobs: () => `${V}/jobs`,
  job: (id: string) => `${V}/jobs/${id}`,
  providers: () => `${V}/providers`,
} as const;

/** Query-string builder for collection filters + cursor pagination. */
export function withQuery(path: string, params?: object | null): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (typeof value === "string" && value !== "") {
      search.set(key, value);
    }
  }
  const qs = search.toString();
  return qs.length > 0 ? `${path}?${qs}` : path;
}
