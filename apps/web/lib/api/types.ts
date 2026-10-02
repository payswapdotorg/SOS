/**
 * SOS wire-contract types — typed mirror of the PUBLIC-DEPLOYMENT-CONTRACT §C
 * DTO minimums (field names binding; richer shapes owned by
 * `services/api/schemas` per contract C.3 — this module records the
 * client-side contract surface and is validated against the fixtures).
 *
 * Law (contract §A.5, architecture-lock): the web client RENDERS what the
 * API provides. These types carry semantics; they never implement them.
 */

// ---------------------------------------------------------------------------
// Truth states (contract C.2 — preserved end-to-end, never silently converted)
// ---------------------------------------------------------------------------

/**
 * The six resource truth states. Exactly the frozen enum; no other values,
 * no silent mapping between them. `EMPTY` means observed-and-empty; `UNKNOWN`
 * means not known; they are distinct and must both stay representable.
 */
export type TruthState =
  | "SUCCESS"
  | "EMPTY"
  | "FAILED"
  | "UNKNOWN"
  | "UNSUPPORTED"
  | "UNAVAILABLE";

export const TRUTH_STATES: readonly TruthState[] = [
  "SUCCESS",
  "EMPTY",
  "FAILED",
  "UNKNOWN",
  "UNSUPPORTED",
  "UNAVAILABLE",
] as const;

/** Human, honest labels for each truth state (no success-washing). */
export const TRUTH_STATE_LABELS: Record<TruthState, string> = {
  SUCCESS: "Success",
  EMPTY: "Empty (observed, none)",
  FAILED: "Failed",
  UNKNOWN: "Unknown",
  UNSUPPORTED: "Unsupported",
  UNAVAILABLE: "Unavailable",
};

// ---------------------------------------------------------------------------
// Error envelope (contract C.2)
// ---------------------------------------------------------------------------

export type ApiErrorCode =
  | "UNAUTHENTICATED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "VALIDATION"
  | "CONFLICT"
  | "RATE_LIMITED"
  | "PAYLOAD_TOO_LARGE"
  | "PROVIDER_UNAVAILABLE";

export const API_ERROR_CODES: readonly ApiErrorCode[] = [
  "UNAUTHENTICATED",
  "FORBIDDEN",
  "NOT_FOUND",
  "VALIDATION",
  "CONFLICT",
  "RATE_LIMITED",
  "PAYLOAD_TOO_LARGE",
  "PROVIDER_UNAVAILABLE",
] as const;

/** Wire shape of every error response: `{"error":{"code","message","details"}}`. */
export interface ApiErrorEnvelope {
  error: {
    code: ApiErrorCode;
    message: string;
    details: Record<string, unknown> | null;
  };
}

// ---------------------------------------------------------------------------
// Collection envelope (contract C.2 — cursor pagination)
// ---------------------------------------------------------------------------

export interface Collection<T> {
  items: T[];
  nextCursor: string | null;
}

// ---------------------------------------------------------------------------
// Core resources (contract C.3 DTO minimums — names binding)
// ---------------------------------------------------------------------------

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  createdAt: string;
}

export interface User {
  id: string;
  githubId: string;
  login: string;
  displayName: string;
  createdAt: string;
}

export type MissionStatus = "DRAFT" | "ACTIVE" | "ARCHIVED";

export interface Mission {
  id: string;
  workspaceId: string;
  title: string;
  status: MissionStatus;
  currentRevisionId: string;
}

// Mission journey inner shapes (client-side mirror; full ownership with
// `services/api/schemas` — names for the six journey arrays are binding).

export interface MissionGoal {
  id: string;
  statement: string;
  rationale: string;
}

export interface MissionOutcome {
  id: string;
  statement: string;
  metric: string;
}

export interface MissionStakeholder {
  id: string;
  name: string;
  role: string;
  interest: string;
}

export interface MissionMeasure {
  id: string;
  name: string;
  target: string;
  current: string | null;
  unit: string;
}

export interface MissionConstraint {
  id: string;
  statement: string;
  severity: "HARD" | "SOFT";
}

export interface MissionPreference {
  id: string;
  statement: string;
}

export type MissionApprovalState = "PROPOSED" | "APPROVED" | "REJECTED";

export interface MissionApproval {
  state: MissionApprovalState;
  requestedBy: string;
  decidedBy: string | null;
  decidedAt: string | null;
}

export interface MissionRevision {
  id: string;
  missionId: string;
  revision: number;
  goals: MissionGoal[];
  outcomes: MissionOutcome[];
  stakeholders: MissionStakeholder[];
  measures: MissionMeasure[];
  constraints: MissionConstraint[];
  preferences: MissionPreference[];
  approval: MissionApproval;
}

// --- Systems ---------------------------------------------------------------

export type SystemMode = "GREENFIELD" | "BROWNFIELD";

export interface System {
  id: string;
  workspaceId: string;
  name: string;
  mode: SystemMode;
  currentRevisionId: string;
}

export type SourceRefKind = "GITHUB_REPO" | "MISSION_HYPOTHESIS" | "OTHER";

export interface SourceRef {
  kind: SourceRefKind;
  url: string;
  revision: string;
  immutable: boolean;
}

export type DriftLevel = "NONE" | "MINOR" | "SIGNIFICANT" | "UNKNOWN";

export interface SystemStateSummary {
  summary: string;
  health: TruthState;
  drift: DriftLevel;
  services: number;
  dataStores: number;
  integrations: number;
}

export interface Uncertainty {
  level: "LOW" | "MODERATE" | "HIGH";
  notes: string;
}

/** Recovery outcome — a truth state, never a fake success. */
export interface RecoveryInfo {
  jobId: string;
  status: TruthState;
  note: string;
}

export interface SystemRevision {
  id: string;
  systemId: string;
  revision: number;
  stateSummary: SystemStateSummary;
  uncertainty: Uncertainty;
  sourceRef: SourceRef;
  recovery: RecoveryInfo;
}

// --- Architecture graph -----------------------------------------------------

export type ArchitectureNodeKind =
  | "SERVICE"
  | "COMPONENT"
  | "DATA_STORE"
  | "INTERFACE"
  | "DEPLOYMENT"
  | "TRUST_BOUNDARY"
  | "CAPABILITY";

export interface ArchitectureNode {
  id: string;
  label: string;
  kind: ArchitectureNodeKind;
  notes: string;
}

export type ArchitectureEdgeKind =
  | "CALLS"
  | "DEPENDS_ON"
  | "DEPLOYS"
  | "READS"
  | "WRITES"
  | "TRUSTS"
  | "OBSERVES";

export interface ArchitectureEdge {
  id: string;
  source: string;
  target: string;
  kind: ArchitectureEdgeKind;
  label: string;
}

export interface ArchitectureGraph {
  nodes: ArchitectureNode[];
  edges: ArchitectureEdge[];
}

// --- Evidence ---------------------------------------------------------------

export type EvidenceKind =
  | "source_revision"
  | "runtime_observation"
  | "test_result"
  | "telemetry"
  | "environment"
  | "experiment"
  | "business_outcome";

export const EVIDENCE_KINDS: readonly EvidenceKind[] = [
  "source_revision",
  "runtime_observation",
  "test_result",
  "telemetry",
  "environment",
  "experiment",
  "business_outcome",
] as const;

export const EVIDENCE_KIND_LABELS: Record<EvidenceKind, string> = {
  source_revision: "Source revision",
  runtime_observation: "Runtime observation",
  test_result: "Test result",
  telemetry: "Telemetry",
  environment: "Environment",
  experiment: "Experiment",
  business_outcome: "Business outcome",
};

export interface ArtifactRef {
  name: string;
  signedUrl: string;
  mediaType: string;
  sizeBytes: number;
}

export interface Evidence {
  id: string;
  workspaceId: string;
  systemId?: string;
  kind: EvidenceKind;
  status: TruthState;
  provenance: string;
  timestamp: string;
  sourceRevision: string;
  relatedSystemState: string;
  confidence: number | null;
  confidenceNote: string;
  artifactRef?: ArtifactRef;
}

// --- Hypotheses --------------------------------------------------------------

export interface CausalModel {
  cause: string;
  effect: string;
  mechanism: string;
}

export type HypothesisStatus =
  | "PROPOSED"
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "REFUTED"
  | "INCONCLUSIVE";

export interface Hypothesis {
  id: string;
  statement: string;
  causal: CausalModel;
  evidenceRefs: string[];
  status: HypothesisStatus;
}

// --- Candidates (multi-objective; NO single score — architecture-lock) ------

export type EffectDirection = "IMPROVE" | "REGRESS" | "NEUTRAL" | "UNCERTAIN";

export interface CandidateEffect {
  onObjective: string;
  description: string;
  direction: EffectDirection;
}

export type Magnitude = "LOW" | "MEDIUM" | "HIGH";

export interface CandidateCost {
  description: string;
  magnitude: Magnitude;
  quantifier: string;
}

export interface CandidateRisk {
  description: string;
  likelihood: Magnitude;
  severity: Magnitude;
  mitigation: string;
}

export type ConstraintCompliance =
  | "SATISFIED"
  | "VIOLATED"
  | "AT_RISK"
  | "UNCERTAIN";

export interface CandidateConstraint {
  constraint: string;
  compliance: ConstraintCompliance;
  note: string;
}

export type ReversibilityLevel =
  | "FULLY_REVERSIBLE"
  | "PARTIALLY_REVERSIBLE"
  | "IRREVERSIBLE";

export interface Reversibility {
  level: ReversibilityLevel;
  rollbackPath: string;
  notes: string;
}

export interface SubgraphReplacementNode {
  id: string;
  label: string;
  kind: ArchitectureNodeKind;
}

export interface SubgraphReplacement {
  /** The boundary-preserving replacement `A' = A - S + S'` (architecture §3.6). */
  boundary: string;
  removes: string[];
  adds: SubgraphReplacementNode[];
  boundaryInvariants: string[];
}

export type ObjectiveDirection = "MINIMIZE" | "MAXIMIZE";

/**
 * One objective, evaluated separately. The evaluation carries a Pareto-front
 * membership flag and per-objective values — never an aggregated scalar.
 */
export interface ObjectiveEvaluation {
  objectiveId: string;
  objective: string;
  direction: ObjectiveDirection;
  value: string;
  unit: string;
  assessment: "GOOD" | "NEUTRAL" | "BAD" | "UNKNOWN";
}

export interface CandidateEvaluation {
  objectives: ObjectiveEvaluation[];
  paretoFront: boolean;
}

export interface Candidate {
  id: string;
  name: string;
  subgraphReplacement: SubgraphReplacement;
  effects: CandidateEffect[];
  costs: CandidateCost[];
  risks: CandidateRisk[];
  constraints: CandidateConstraint[];
  evidenceRefs: string[];
  reversibility: Reversibility;
  evaluation: CandidateEvaluation;
}

// --- Assurance ---------------------------------------------------------------

export interface AssuranceCheck {
  id: string;
  name: string;
  status: TruthState;
  detail: string;
}

export type AssuranceVerdict = "PASS" | "CONDITIONAL_PASS" | "FAIL" | "PENDING";

export interface AssuranceRun {
  id: string;
  candidateId: string;
  checks: AssuranceCheck[];
  verdict: AssuranceVerdict;
  verdictNote: string;
}

// --- Decisions (incl. ASK as a first-class outcome) ---------------------------

export type DecisionAction =
  | "ACT"
  | "EXPERIMENT"
  | "GATHER_EVIDENCE"
  | "ASK"
  | "REJECT"
  | "ROLLBACK";

export const DECISION_ACTIONS: readonly DecisionAction[] = [
  "ACT",
  "EXPERIMENT",
  "GATHER_EVIDENCE",
  "ASK",
  "REJECT",
  "ROLLBACK",
] as const;

export interface AuthoritySnapshot {
  principal: string;
  autonomy: string;
  constraints: string[];
}

export interface DecisionRisk {
  level: Magnitude;
  summary: string;
}

export interface BlastRadius {
  level: Magnitude;
  description: string;
}

export type ApprovalState = "PENDING" | "GRANTED" | "DENIED";

export interface RequiredApproval {
  approver: string;
  scope: string;
  state: ApprovalState;
}

export interface AskAlternative {
  label: string;
  expectedOutcome: string;
  tradeoffs: string[];
}

export interface AskEvidenceQuality {
  grade: "STRONG" | "MODERATE" | "WEAK";
  note: string;
}

export interface AskPayload {
  decision: string;
  alternatives: AskAlternative[];
  evidenceQuality: AskEvidenceQuality;
  uncertainty: string;
  tradeoffs: string[];
}

/**
 * Client-side extension (pending PUB-01 full schemas): the demo cockpit needs
 * to know which candidate a decision governs and its lifecycle position.
 * The contract-minimum fields remain exactly as bound above.
 */
export type DecisionStatus = "AWAITING_OWNER" | "EXECUTED" | "SUPERSEDED";

export interface Decision {
  id: string;
  action: DecisionAction;
  candidateId?: string;
  candidateName?: string;
  createdAt: string;
  status: DecisionStatus;
  rationale: string;
  evidenceRefs: string[];
  authoritySnapshot: AuthoritySnapshot;
  expectedImpact: string;
  risk: DecisionRisk;
  blastRadius: BlastRadius;
  reversibility: string;
  requiredApprovals: RequiredApproval[];
  askPayload?: AskPayload;
}

// --- Authorizations -----------------------------------------------------------

export type AuthorizationDecision = "GRANTED" | "DENIED";

export interface Authorization {
  id: string;
  decisionId?: string;
  principal: string;
  scope: string;
  decision: AuthorizationDecision;
  createdAt: string;
}

// --- Experiments --------------------------------------------------------------

/**
 * Candidate lifecycle (architecture §9): PROPOSED → ANALYZED → ASSURED →
 * TESTED → SIMULATED/REPLAYED → SHADOW → CANARY → EXPERIMENTAL → PROMOTED,
 * with ROLLBACK reachable at any live stage.
 */
export type ExperimentStatus =
  | "PROPOSED"
  | "ANALYZED"
  | "ASSURED"
  | "TESTED"
  | "SIMULATED"
  | "REPLAYED"
  | "SHADOW"
  | "CANARY"
  | "EXPERIMENTAL"
  | "PROMOTED"
  | "ROLLED_BACK";

export const EXPERIMENT_LIFECYCLE: readonly ExperimentStatus[] = [
  "PROPOSED",
  "ANALYZED",
  "ASSURED",
  "TESTED",
  "SIMULATED",
  "REPLAYED",
  "SHADOW",
  "CANARY",
  "EXPERIMENTAL",
  "PROMOTED",
  "ROLLED_BACK",
] as const;

export interface ExperimentEvent {
  id: string;
  at: string;
  kind: string;
  label: string;
  detail: string;
  status?: TruthState;
}

export interface Experiment {
  id: string;
  candidateId: string;
  candidateName: string;
  status: ExperimentStatus;
  events: ExperimentEvent[];
}

// --- Executions & receipts ------------------------------------------------------

export type ExecutionProvider = "DEMO" | "APIFY";

export interface ExecutionReceipt {
  provider: ExecutionProvider;
  /** Demo receipts carry an explicit DEMO badge (directive §9 truthfulness). */
  demo: boolean;
  runId: string;
  completedAt: string;
  summary: string;
}

export interface Execution {
  id: string;
  experimentId?: string;
  jobId?: string;
  provider: ExecutionProvider;
  requestHash: string;
  receipt?: ExecutionReceipt;
  artifactRefs: ArtifactRef[];
  status: TruthState;
}

// --- Learning / memory -----------------------------------------------------------

export type LearningVerdict =
  | "CONFIRMED"
  | "PARTIALLY_CONFIRMED"
  | "REFUTED"
  | "INCONCLUSIVE"
  | "PENDING";

export interface LearningRecord {
  id: string;
  context: string;
  candidate: string;
  predictedEffects: string[];
  actualEffects: string[];
  uncertainty: string;
  verdict: LearningVerdict;
  lessons: string[];
}

export interface MemoryEntry {
  id: string;
  context: string;
  candidate: string;
  predictedEffects: string[];
  actualEffects: string[];
  uncertainty: string;
  verdict: LearningVerdict;
  lessons: string[];
}

// --- Jobs (directive §8 fields, camelCase per contract C.3) --------------------

export type JobStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type JobProvider = "DEMO" | "APIFY" | "GITHUB";

export interface JobErrorState {
  code: string;
  message: string;
  details: Record<string, unknown> | null;
}

/** Receipt of a job run (provider may be a source adapter, not just execution providers). */
export interface JobReceipt {
  provider: JobProvider;
  demo: boolean;
  runId: string;
  completedAt: string;
  summary: string;
}

export interface Job {
  id: string;
  tenantId: string;
  type: string;
  requestedBy: string;
  authoritySnapshot: AuthoritySnapshot;
  inputHash: string;
  sourceRevision: string;
  provider: JobProvider;
  status: JobStatus;
  startedAt: string | null;
  completedAt: string | null;
  receipt?: JobReceipt;
  artifactRefs: ArtifactRef[];
  errorState: JobErrorState | null;
}

// --- Health & audit ---------------------------------------------------------------

export interface HealthCheck {
  name: string;
  status: TruthState;
  detail: string;
}

export interface Health {
  status: "ok" | "degraded";
  checks: HealthCheck[];
}

export interface ActivityEvent {
  id: string;
  actor: string;
  action: string;
  target: string;
  timestamp: string;
  meta: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Demo dataset root (fixture mode)
// ---------------------------------------------------------------------------

export interface DemoDataset {
  workspace: Workspace;
  users: User[];
  mission: Mission;
  missionRevisions: MissionRevision[];
  systems: System[];
  systemRevisions: SystemRevision[];
  architectureGraphs: Record<string, ArchitectureGraph>;
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  candidates: Candidate[];
  assuranceRuns: AssuranceRun[];
  decisions: Decision[];
  authorizations: Authorization[];
  experiments: Experiment[];
  executions: Execution[];
  jobs: Job[];
  learningRecords: LearningRecord[];
  memoryEntries: MemoryEntry[];
  activity: ActivityEvent[];
  health: Health;
}
