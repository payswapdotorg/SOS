/**
 * THE typed API client (the single module through which every API call
 * flows — law §8). Relative URLs only: every request path is joined with the
 * configured API base. The base comes exclusively from
 * `NEXT_PUBLIC_API_BASE` (same-origin `/api/v1` when set-but-empty; an
 * absolute deployment URL when the operator configures one). No absolute URL
 * is ever hardcoded here.
 *
 * Fixture/demo mode: when no API is configured (`NEXT_PUBLIC_API_BASE`
 * unset, or `NEXT_PUBLIC_API_MODE=fixtures`), the client serves the typed
 * demo FIXTURES so the whole cockpit is demonstrable standalone. The mode is
 * reported truthfully to the UI (`mode: "fixtures"`) and every fixture-backed
 * surface is labeled demo data.
 *
 * The client never interprets SOS decision rules — it renders what the
 * contract provides (architecture-lock; contract §A.5).
 */

import { endpoints, withQuery } from "./endpoints";
import { ApiError, isApiErrorEnvelope } from "./errors";
import {
  mapWireAuditEvent,
  mapWireSystemCurrentRevision,
  type WireCollection,
  type WireSystem,
  type WireWorkspaceDetail,
} from "./wire";
import type {
  ActivityEvent,
  ApiErrorEnvelope,
  ArchitectureGraph,
  ArtifactRef,
  AssuranceRun,
  Authorization,
  Candidate,
  Collection,
  Decision,
  DemoDataset,
  Evidence,
  EvidenceKind,
  Execution,
  Experiment,
  Health,
  Hypothesis,
  Job,
  LearningRecord,
  MemoryEntry,
  Mission,
  MissionRevision,
  System,
  SystemRevision,
  TruthState,
  User,
  Workspace,
} from "./types";
import { demo } from "@/lib/fixtures/demo";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export type ClientMode = "fixtures" | "api";

export interface SosClientConfig {
  /**
   * API base override (tests / embedding). When omitted, environment
   * resolution applies. Same-origin default is `/api/v1`.
   */
  apiBase?: string;
  /** Force fixture/demo mode regardless of env (tests, storybook). */
  forceFixtures?: boolean;
}

/** Resolved runtime configuration of the client. */
export interface ClientRuntime {
  mode: ClientMode;
  apiBase: string;
  /** True when the demo dataset is being served (UI labels it honestly). */
  demo: boolean;
}

/**
 * Environment resolution (build-time inlined by Next.js):
 * - `NEXT_PUBLIC_API_MODE=fixtures` → fixture mode (explicit override);
 * - `NEXT_PUBLIC_API_BASE` set (possibly empty string) → API mode;
 *   empty string means same-origin, base `/api/v1`;
 * - `NEXT_PUBLIC_API_BASE` unset (no API configured) → fixture mode.
 */
export function resolveRuntime(override?: SosClientConfig): ClientRuntime {
  if (override?.forceFixtures) {
    return { mode: "fixtures", apiBase: "", demo: true };
  }
  if (override?.apiBase !== undefined) {
    return { mode: "api", apiBase: normalizeBase(override.apiBase), demo: false };
  }
  const envMode = process.env.NEXT_PUBLIC_API_MODE;
  if (envMode === "fixtures") {
    return { mode: "fixtures", apiBase: "", demo: true };
  }
  const envBase = process.env.NEXT_PUBLIC_API_BASE;
  if (envBase === undefined) {
    // No API configured → the typed fixtures make the cockpit demonstrable
    // standalone (contract §D PUB-02, fixture/demo mode).
    return { mode: "fixtures", apiBase: "", demo: true };
  }
  return { mode: "api", apiBase: normalizeBase(envBase), demo: false };
}

/**
 * The base is an ORIGIN-level prefix (e.g. "" for same-origin, or
 * "https://api.example.com"). The `/api/v1` version prefix lives in the
 * endpoint map, so an empty configured base yields plain relative URLs —
 * same-origin by construction.
 */
function normalizeBase(base: string): string {
  const trimmed = base.trim();
  return trimmed.replace(/\/+$/, "");
}

/** Join the configured base with a relative endpoint path. */
export function buildUrl(runtime: ClientRuntime, path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${runtime.apiBase}${p}`;
}

// ---------------------------------------------------------------------------
// Fixture serving (deterministic; small artificial latency only so honest
// loading states are actually visible in the demo — the data itself is
// fully typed and clearly labeled demo)
// ---------------------------------------------------------------------------

const FIXTURE_LATENCY_MS = 180;

function fixtureDelay(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, FIXTURE_LATENCY_MS));
}

function page<T>(items: T[]): Collection<T> {
  return { items, nextCursor: null };
}

function notFound(what: string): ApiError {
  return new ApiError({ message: `Not found: ${what}`, code: "NOT_FOUND", status: 404 });
}

// ---------------------------------------------------------------------------
// The client
// ---------------------------------------------------------------------------

export interface EvidenceFilter {
  workspaceId?: string;
  systemId?: string;
  kind?: EvidenceKind;
  status?: TruthState;
  cursor?: string;
}

export interface CollectionFilter {
  workspaceId?: string;
  cursor?: string;
}

export interface SosClient {
  runtime: ClientRuntime;
  health(): Promise<Health>;
  me(): Promise<User>;
  listWorkspaces(filter?: CollectionFilter): Promise<Collection<Workspace>>;
  getWorkspace(id: string): Promise<Workspace>;
  getMission(workspaceId: string): Promise<Mission>;
  listMissionRevisions(missionId: string, filter?: CollectionFilter): Promise<Collection<MissionRevision>>;
  getMissionRevision(missionId: string, revisionId: string): Promise<MissionRevision>;
  listSystems(filter?: CollectionFilter): Promise<Collection<System>>;
  getSystem(id: string): Promise<System>;
  getSystemRevision(systemId: string): Promise<SystemRevision>;
  getArchitectureGraph(systemId: string): Promise<ArchitectureGraph>;
  listEvidence(filter?: EvidenceFilter): Promise<Collection<Evidence>>;
  getEvidence(id: string): Promise<Evidence>;
  listHypotheses(filter?: CollectionFilter): Promise<Collection<Hypothesis>>;
  listCandidates(filter?: CollectionFilter): Promise<Collection<Candidate>>;
  getCandidate(id: string): Promise<Candidate>;
  listAssuranceRuns(candidateId?: string): Promise<Collection<AssuranceRun>>;
  listDecisions(filter?: CollectionFilter): Promise<Collection<Decision>>;
  getDecision(id: string): Promise<Decision>;
  listAuthorizations(filter?: CollectionFilter): Promise<Collection<Authorization>>;
  listExperiments(filter?: CollectionFilter): Promise<Collection<Experiment>>;
  getExperiment(id: string): Promise<Experiment>;
  listExecutions(filter?: CollectionFilter): Promise<Collection<Execution>>;
  getExecution(id: string): Promise<Execution>;
  listLearningRecords(filter?: CollectionFilter): Promise<Collection<LearningRecord>>;
  listMemoryEntries(filter?: CollectionFilter): Promise<Collection<MemoryEntry>>;
  listJobs(filter?: CollectionFilter): Promise<Collection<Job>>;
  getJob(id: string): Promise<Job>;
  listActivity(filter?: CollectionFilter): Promise<Collection<ActivityEvent>>;
}

/**
 * The fetch wrapper honoring the API base. Relative URLs always; error
 * envelope parsed into `ApiError`; transport failures surface as
 * `ApiError` with `code = null` (never a truth-state masquerade).
 */
async function apiFetch<T>(runtime: ClientRuntime, path: string, init?: RequestInit): Promise<T> {
  const url = buildUrl(runtime, path);
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    throw new ApiError({
      message: cause instanceof Error ? cause.message : "Network request failed",
      code: null,
    });
  }
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    if (isApiErrorEnvelope(body)) {
      throw ApiError.fromEnvelope(response.status, body);
    }
    throw new ApiError({
      message: `HTTP ${response.status} (no error envelope)`,
      code: null,
      status: response.status,
    });
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Parse an error envelope payload (exposed for tests). */
export function parseErrorEnvelope(payload: unknown): ApiError | null {
  if (!isApiErrorEnvelope(payload)) return null;
  return ApiError.fromEnvelope(0, payload as ApiErrorEnvelope);
}

export function createSosClient(config?: SosClientConfig): SosClient {
  const runtime = resolveRuntime(config);
  const useFixtures = runtime.mode === "fixtures";
  const d: DemoDataset = demo;

  if (useFixtures) {
    return createFixtureClient(runtime, d);
  }
  return createApiClient(runtime);
}

function createApiClient(runtime: ClientRuntime): SosClient {
  const f = <T>(path: string, init?: RequestInit) => apiFetch<T>(runtime, path, init);
  // Directive §7 defines {id} routes only for workspaces, missions (+revisions),
  // systems, experiments, executions and jobs. Other resources are fetched as
  // workspace-scoped collections and narrowed client-side — transport mapping
  // only, no SOS semantics. Wire DTO shapes pass through lib/api/wire.ts
  // mappers (PUB-01 OpenAPI = the authoritative wire contract).
  const oneFrom = async <T>(
    collection: Promise<Collection<T>>,
    pred: (item: T) => boolean,
    what: string,
  ): Promise<T> => {
    const c = await collection;
    const found = c.items.find(pred);
    if (!found) throw notFound(what);
    return found;
  };
  return {
    runtime,
    health: () => f<Health>(endpoints.health()),
    me: () => f<User>(endpoints.me()),
    listWorkspaces: (filter) =>
      f<Collection<Workspace>>(withQuery(endpoints.workspaces(), filter ?? {})),
    getWorkspace: (id) => f<Workspace>(endpoints.workspace(id)),
    getMission: (workspaceId) =>
      oneFrom(
        f<Collection<Mission>>(withQuery(endpoints.missions(), { workspaceId })),
        (m) => m.workspaceId === workspaceId,
        `mission for workspace ${workspaceId}`,
      ),
    listMissionRevisions: (missionId, filter) =>
      f<Collection<MissionRevision>>(withQuery(endpoints.missionRevisions(missionId), filter ?? {})),
    getMissionRevision: (missionId, revisionId) =>
      oneFrom(
        f<Collection<MissionRevision>>(withQuery(endpoints.missionRevisions(missionId), {})),
        (r) => r.id === revisionId,
        `mission revision ${revisionId}`,
      ),
    listSystems: (filter) => f<Collection<System>>(withQuery(endpoints.systems(), filter ?? {})),
    getSystem: (id) => f<System>(endpoints.system(id)),
    getSystemRevision: async (systemId) => {
      const system = await f<WireSystem>(endpoints.system(systemId));
      const mapped = mapWireSystemCurrentRevision(system);
      if (!mapped) throw notFound(`current revision for system ${systemId}`);
      return mapped.revision;
    },
    getArchitectureGraph: async (systemId) => {
      const system = await f<WireSystem>(endpoints.system(systemId));
      return mapWireSystemCurrentRevision(system)?.graph ?? { nodes: [], edges: [] };
    },
    listEvidence: (filter) => f<Collection<Evidence>>(withQuery(endpoints.evidence(), filter ?? {})),
    getEvidence: (id) =>
      oneFrom(
        f<Collection<Evidence>>(withQuery(endpoints.evidence(), {})),
        (e) => e.id === id,
        `evidence ${id}`,
      ),
    listHypotheses: (filter) =>
      f<Collection<Hypothesis>>(withQuery(endpoints.hypotheses(), filter ?? {})),
    listCandidates: (filter) =>
      f<Collection<Candidate>>(withQuery(endpoints.candidates(), filter ?? {})),
    getCandidate: (id) =>
      oneFrom(
        f<Collection<Candidate>>(withQuery(endpoints.candidates(), {})),
        (c) => c.id === id,
        `candidate ${id}`,
      ),
    listAssuranceRuns: (candidateId) =>
      f<Collection<AssuranceRun>>(
        withQuery(endpoints.assurance(), candidateId ? { candidateId } : {}),
      ),
    listDecisions: (filter) => f<Collection<Decision>>(withQuery(endpoints.decisions(), filter ?? {})),
    getDecision: (id) =>
      oneFrom(
        f<Collection<Decision>>(withQuery(endpoints.decisions(), {})),
        (d) => d.id === id,
        `decision ${id}`,
      ),
    listAuthorizations: (filter) =>
      f<Collection<Authorization>>(withQuery(endpoints.authorizations(), filter ?? {})),
    listExperiments: (filter) =>
      f<Collection<Experiment>>(withQuery(endpoints.experiments(), filter ?? {})),
    getExperiment: (id) => f<Experiment>(endpoints.experiment(id)),
    listExecutions: (filter) =>
      f<Collection<Execution>>(withQuery(endpoints.executions(), filter ?? {})),
    getExecution: (id) => f<Execution>(endpoints.execution(id)),
    listLearningRecords: (filter) =>
      f<Collection<LearningRecord>>(withQuery(endpoints.learning(), filter ?? {})),
    listMemoryEntries: (filter) =>
      f<Collection<MemoryEntry>>(withQuery(endpoints.memory(), filter ?? {})),
    listJobs: (filter) => f<Collection<Job>>(withQuery(endpoints.jobs(), filter ?? {})),
    getJob: (id) => f<Job>(endpoints.job(id)),
    listActivity: async (filter) => {
      // The audit trail ships on the workspace detail (recentActivity —
      // AuditEventDTO[]); there is no /api/v1/audit collection path. With no
      // explicit workspace, the first workspace serves the single-workspace
      // cockpit stage (documented transport mapping).
      const workspaceId =
        filter?.workspaceId ??
        (await f<WireCollection<Workspace>>(withQuery(endpoints.workspaces(), {}))).items[0]
          ?.id;
      if (!workspaceId) return { items: [], nextCursor: null };
      const detail = await f<WireWorkspaceDetail>(endpoints.workspace(workspaceId));
      return {
        items: (detail.recentActivity ?? []).map(mapWireAuditEvent),
        nextCursor: null,
      };
    },
  };
}

function createFixtureClient(runtime: ClientRuntime, d: DemoDataset): SosClient {
  const after = async <T>(value: T): Promise<T> => {
    await fixtureDelay();
    return value;
  };
  const byId = <T extends { id: string }>(items: T[], id: string, what: string): T => {
    const found = items.find((item) => item.id === id);
    if (!found) throw notFound(`${what} ${id}`);
    return found;
  };
  return {
    runtime,
    health: () => after(d.health),
    me: () => after(d.users[0]),
    listWorkspaces: () => after(page([d.workspace])),
    getWorkspace: (id) => after(byId([d.workspace], id, "workspace")),
    getMission: (workspaceId) => {
      if (d.mission.workspaceId !== workspaceId) {
        return Promise.reject(notFound(`mission for workspace ${workspaceId}`));
      }
      return after(d.mission);
    },
    listMissionRevisions: (missionId) =>
      after(page(d.missionRevisions.filter((r) => r.missionId === missionId))),
    getMissionRevision: (missionId, revisionId) =>
      after(
        byId(
          d.missionRevisions.filter((r) => r.missionId === missionId),
          revisionId,
          "mission revision",
        ),
      ),
    listSystems: () => after(page(d.systems)),
    getSystem: (id) => after(byId(d.systems, id, "system")),
    getSystemRevision: (systemId) => {
      const system = byId(d.systems, systemId, "system");
      const rev = byId(d.systemRevisions, system.currentRevisionId, "system revision");
      if (rev.systemId !== systemId) throw notFound(`revision for system ${systemId}`);
      return after(rev);
    },
    getArchitectureGraph: (systemId) =>
      after(d.architectureGraphs[systemId] ?? { nodes: [], edges: [] }),
    listEvidence: (filter) =>
      after(
        page(
          d.evidence.filter(
            (e) =>
              (!filter?.workspaceId || e.workspaceId === filter.workspaceId) &&
              (!filter?.systemId || e.systemId === filter.systemId) &&
              (!filter?.kind || e.kind === filter.kind) &&
              (!filter?.status || e.status === filter.status),
          ),
        ),
      ),
    getEvidence: (id) => after(byId(d.evidence, id, "evidence")),
    listHypotheses: () => after(page(d.hypotheses)),
    listCandidates: () => after(page(d.candidates)),
    getCandidate: (id) => after(byId(d.candidates, id, "candidate")),
    listAssuranceRuns: (candidateId) =>
      after(
        page(d.assuranceRuns.filter((a) => !candidateId || a.candidateId === candidateId)),
      ),
    listDecisions: () => after(page(d.decisions)),
    getDecision: (id) => after(byId(d.decisions, id, "decision")),
    listAuthorizations: () => after(page(d.authorizations)),
    listExperiments: () => after(page(d.experiments)),
    getExperiment: (id) => after(byId(d.experiments, id, "experiment")),
    listExecutions: () => after(page(d.executions)),
    getExecution: (id) => after(byId(d.executions, id, "execution")),
    listLearningRecords: () => after(page(d.learningRecords)),
    listMemoryEntries: () => after(page(d.memoryEntries)),
    listJobs: () => after(page(d.jobs)),
    getJob: (id) => after(byId(d.jobs, id, "job")),
    listActivity: () => after(page(d.activity)),
  };
}

// ---------------------------------------------------------------------------
// Shared singleton (the app uses exactly one client instance)
// ---------------------------------------------------------------------------

let singleton: SosClient | null = null;

/** The app-wide client. Created once from environment resolution. */
export function getSosClient(): SosClient {
  if (!singleton) {
    singleton = createSosClient();
  }
  return singleton;
}

/** Test helper — reset the singleton (never used by app code). */
export function __resetSosClientForTests(): void {
  singleton = null;
}

export type { ArtifactRef };
