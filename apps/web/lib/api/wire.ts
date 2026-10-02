/**
 * Wire shapes + mappers — the PUB-01 OpenAPI is the authoritative wire
 * contract (services/api, merged as PR #25). This module mirrors the exact
 * wire DTOs the client consumes and maps them into the UI presentation
 * types (`./types`). Mapping rules:
 *
 *  - paths and parameter names always match the OpenAPI (never invented);
 *  - enums are carried verbatim (truth states, node/edge kinds — the frozen
 *    W3 graph vocabulary, display-uppercased 1:1);
 *  - fields the wire does not carry degrade truthfully (UNKNOWN / derived
 *    only from provided data) — never fabricated;
 *  - this is transport mapping only: no SOS decision semantics live here.
 *
 * The demo fixtures exercise the RICHER presentation shapes directly
 * (fixture mode); API mode always passes through these mappers, so the two
 * modes can never drift into parallel semantics.
 */

import type {
  ActivityEvent,
  ArchitectureEdge,
  ArchitectureEdgeKind,
  ArchitectureGraph,
  ArchitectureNode,
  ArchitectureNodeKind,
  SystemRevision,
  TruthState,
} from "./types";

// ---------------------------------------------------------------------------
// Wire interfaces (PUB-01 OpenAPI / services/api/schemas — verbatim shapes)
// ---------------------------------------------------------------------------

export interface WireCollection<T> {
  items: T[];
  nextCursor: string | null;
}

export interface WireAuditEvent {
  id: string;
  tenantId?: string | null;
  actor: string;
  action: string;
  target: string;
  meta?: Record<string, unknown> | null;
  ts: string;
}

export interface WireWorkspaceDetail {
  id: string;
  name: string;
  slug: string;
  createdAt: string;
  isDemo?: boolean;
  recentActivity?: WireAuditEvent[] | null;
}

/** Frozen W3 `NodeType` (wire enum, lowercase-hyphenated). */
export type WireNodeType =
  | "capability"
  | "service"
  | "component"
  | "data_store"
  | "interface"
  | "deployment"
  | "trust_boundary"
  | "policy"
  | "model"
  | "adapter"
  | "external_dependency";

/** Frozen W3 `EdgeType` (wire enum, lowercase-hyphenated). */
export type WireEdgeType =
  | "call"
  | "data-flow"
  | "dependency"
  | "trust"
  | "deployment"
  | "runtime-interaction"
  | "realizes"
  | "observes"
  | "influences"
  | "owns"
  | "constrains";

export interface WireGraphNode {
  id: string;
  type: WireNodeType | string;
  name: string;
  attributes?: Record<string, unknown> | null;
  uncertainty?: unknown;
}

export interface WireGraphEdge {
  id: string;
  type: WireEdgeType | string;
  sourceId: string;
  targetId: string;
  attributes?: Record<string, unknown> | null;
  uncertainty?: unknown;
}

export interface WireGraph {
  nodes?: WireGraphNode[] | null;
  edges?: WireGraphEdge[] | null;
}

export interface WireUncertainty {
  state?: TruthState | string | null;
  reason?: string | null;
  confidence?: number | null;
}

export interface WireSourceRef {
  kind?: string | null;
  url?: string | null;
  revision?: string | null;
  immutable?: boolean | null;
}

export interface WireRecoveryInfo {
  jobId?: string | null;
  status?: TruthState | string | null;
}

export interface WireSystemRevision {
  id: string;
  systemId?: string | null;
  revision?: number | null;
  stateSummary?: string | null;
  uncertainty?: WireUncertainty | null;
  sourceRef?: WireSourceRef | null;
  recovery?: WireRecoveryInfo | null;
  graph?: WireGraph | null;
  createdAt?: string | null;
}

export interface WireSystem {
  id: string;
  workspaceId: string;
  name: string;
  mode?: string | null;
  currentRevisionId?: string | null;
  currentRevision?: WireSystemRevision | null;
  createdAt?: string | null;
}

// ---------------------------------------------------------------------------
// Vocabulary maps (frozen W3 graph enums, 1:1, display-uppercased)
// ---------------------------------------------------------------------------

const NODE_KIND_BY_WIRE: Record<string, ArchitectureNodeKind> = {
  capability: "CAPABILITY",
  service: "SERVICE",
  component: "COMPONENT",
  data_store: "DATA_STORE",
  interface: "INTERFACE",
  deployment: "DEPLOYMENT",
  trust_boundary: "TRUST_BOUNDARY",
  policy: "POLICY",
  model: "MODEL",
  adapter: "ADAPTER",
  external_dependency: "EXTERNAL_DEPENDENCY",
};

const EDGE_KIND_BY_WIRE: Record<string, ArchitectureEdgeKind> = {
  call: "CALLS",
  "data-flow": "DATA_FLOW",
  dependency: "DEPENDS_ON",
  trust: "TRUSTS",
  deployment: "DEPLOYS",
  "runtime-interaction": "RUNTIME_INTERACTION",
  realizes: "REALIZES",
  observes: "OBSERVES",
  influences: "INFLUENCES",
  owns: "OWNS",
  constrains: "CONSTRAINS",
};

// ---------------------------------------------------------------------------
// Mappers
// ---------------------------------------------------------------------------

function asTruthState(value: unknown): TruthState {
  const allowed: readonly TruthState[] = [
    "SUCCESS",
    "EMPTY",
    "FAILED",
    "UNKNOWN",
    "UNSUPPORTED",
    "UNAVAILABLE",
  ];
  return typeof value === "string" && (allowed as readonly string[]).includes(value)
    ? (value as TruthState)
    : "UNKNOWN";
}

function attrString(attributes: Record<string, unknown> | null | undefined, key: string): string {
  const value = attributes?.[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function stringifyMeta(meta: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!meta) return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(meta)) {
    out[key] =
      typeof value === "string"
        ? value
        : typeof value === "number" || typeof value === "boolean"
          ? String(value)
          : JSON.stringify(value);
  }
  return out;
}

/** Map a wire audit event to the Activity presentation type (ts → timestamp). */
export function mapWireAuditEvent(event: WireAuditEvent): ActivityEvent {
  return {
    id: event.id,
    actor: event.actor,
    action: event.action,
    target: event.target,
    timestamp: event.ts,
    meta: stringifyMeta(event.meta),
  };
}

/** Map the frozen wire graph vocabulary to the display vocabulary (1:1). */
export function mapWireGraph(graph: WireGraph | null | undefined): ArchitectureGraph {
  const nodes: ArchitectureNode[] = (graph?.nodes ?? []).map((node) => ({
    id: node.id,
    label: node.name,
    kind: NODE_KIND_BY_WIRE[node.type] ?? "COMPONENT", // forward-compat display fallback
    notes: attrString(node.attributes, "notes"),
  }));
  const edges: ArchitectureEdge[] = (graph?.edges ?? []).map((edge) => ({
    id: edge.id,
    source: edge.sourceId,
    target: edge.targetId,
    kind: EDGE_KIND_BY_WIRE[edge.type] ?? "DEPENDS_ON", // forward-compat display fallback
    label: attrString(edge.attributes, "label"),
  }));
  return { nodes, edges };
}

/**
 * Map a wire `SystemRevisionDTO` into the presentation type. Aggregates the
 * wire does not carry degrade truthfully:
 *  - `stateSummary.health` / `drift` → UNKNOWN (no wire aggregate yet);
 *  - topology counts derive ONLY from the provided graph (none observed =
 *    0 — the UNKNOWN health signals the partial view; PUB-09 deepens this);
 *  - `recovery.note` is a fixture-only presentation extra (absent here).
 */
export function mapWireSystemRevision(
  wire: WireSystemRevision,
  fallbackSystemId?: string,
): SystemRevision {
  const graph = mapWireGraph(wire.graph);
  const services = graph.nodes.filter((n) => n.kind === "SERVICE").length;
  const dataStores = graph.nodes.filter((n) => n.kind === "DATA_STORE").length;
  const integrations = graph.nodes.filter(
    (n) => n.kind === "INTERFACE" || n.kind === "EXTERNAL_DEPENDENCY",
  ).length;
  return {
    id: wire.id,
    systemId: wire.systemId ?? fallbackSystemId ?? "",
    revision: wire.revision ?? 0,
    stateSummary: {
      summary: wire.stateSummary ?? "",
      health: "UNKNOWN",
      drift: "UNKNOWN",
      services,
      dataStores,
      integrations,
    },
    uncertainty: {
      state: asTruthState(wire.uncertainty?.state),
      reason: wire.uncertainty?.reason ?? "",
      confidence:
        typeof wire.uncertainty?.confidence === "number" ? wire.uncertainty.confidence : null,
    },
    sourceRef: {
      kind: wire.sourceRef?.kind ?? "",
      url: wire.sourceRef?.url ?? "",
      revision: wire.sourceRef?.revision ?? "",
      immutable: wire.sourceRef?.immutable ?? false,
    },
    recovery: {
      jobId: wire.recovery?.jobId ?? "",
      status: asTruthState(wire.recovery?.status),
    },
  };
}

/** Extract + map the current revision of a wire `SystemDTO`. */
export function mapWireSystemCurrentRevision(
  system: WireSystem,
): { revision: SystemRevision; graph: ArchitectureGraph } | null {
  const current = system.currentRevision;
  if (!current) return null;
  const revision = mapWireSystemRevision(current, system.id);
  const graph = mapWireGraph(current.graph);
  return { revision, graph };
}
