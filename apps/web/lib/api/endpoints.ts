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
    session: () => `${V}/auth/session`,
    /** The account surface (user + workspace memberships with roles). */
    account: () => `${V}/auth/account`,
    logout: () => `${V}/auth/logout`,
  },
  workspaces: () => `${V}/workspaces`,
  workspace: (id: string) => `${V}/workspaces/${id}`,
  missions: () => `${V}/missions`,
  mission: (id: string) => `${V}/missions/${id}`,
  missionRevisions: (missionId: string) => `${V}/missions/${missionId}/revisions`,
  /**
   * Single revision fetch is NOT a wire path (the OpenAPI exposes only the
   * collection). The client narrows the collection client-side — transport
   * mapping only, no invented server route.
   */
  systems: () => `${V}/systems`,
  system: (id: string) => `${V}/systems/${id}`,
  systemRecovery: (id: string) => `${V}/systems/${id}/recovery`,
  /**
   * The architecture graph is NOT a separate wire path: the authoritative
   * OpenAPI ships it inside the system's current revision
   * (`SystemDTO.currentRevision.graph`). The client derives it from
   * `GET /systems/{id}` — no invented `/architecture` route.
   */
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
   * The Activity surface consumes the audit trail the authoritative wire
   * already ships: `GET /workspaces/{id}` → `recentActivity`
   * (`AuditEventDTO[]`). There is no `/api/v1/audit` collection path in the
   * PUB-01 OpenAPI (the directive §7 endpoint map never listed one) — the
   * earlier provisional path is retired (PUB-02 → PUB-01 reconciliation).
   */
  jobs: () => `${V}/jobs`,
  job: (id: string) => `${V}/jobs/${id}`,
  /** The wire spells the provider surface as `/providers/status` (GET). */
  providers: () => `${V}/providers/status`,
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
