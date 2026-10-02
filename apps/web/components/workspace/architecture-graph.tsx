"use client";

import type { ArchitectureGraph, ArchitectureNode } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

/**
 * Architecture graph rendering — deterministic layered layout (columns by
 * node kind, stable order within columns). Rendered as a readable diagram
 * plus the exact structured node/edge list (the list is the source of truth;
 * the diagram is a projection).
 */

const COLUMN_ORDER: ArchitectureNode["kind"][] = [
  "DEPLOYMENT",
  "INTERFACE",
  "SERVICE",
  "COMPONENT",
  "DATA_STORE",
  "CAPABILITY",
  "TRUST_BOUNDARY",
];

interface Positioned {
  node: ArchitectureNode;
  x: number;
  y: number;
  w: number;
  h: number;
}

const NODE_W = 120;
const NODE_H = 44;
const GAP_X = 70;
const GAP_Y = 26;

function layout(graph: ArchitectureGraph): Positioned[] {
  const columns: ArchitectureNode[][] = COLUMN_ORDER.map(() => []);
  for (const node of graph.nodes) {
    const col = Math.max(0, COLUMN_ORDER.indexOf(node.kind));
    columns[col].push(node);
  }
  const positioned: Positioned[] = [];
  columns.forEach((nodes, col) => {
    nodes.sort((a, b) => a.id.localeCompare(b.id));
    nodes.forEach((node, i) => {
      positioned.push({
        node,
        x: 20 + col * (NODE_W + GAP_X),
        y: 20 + i * (NODE_H + GAP_Y),
        w: NODE_W,
        h: NODE_H,
      });
    });
  });
  return positioned;
}

const KIND_TONE: Record<ArchitectureNode["kind"], string> = {
  SERVICE: "fill-teal-50 stroke-teal-400",
  COMPONENT: "fill-slate-50 stroke-slate-400",
  DATA_STORE: "fill-amber-50 stroke-amber-400",
  INTERFACE: "fill-violet-50 stroke-violet-400",
  DEPLOYMENT: "fill-orange-50 stroke-orange-400",
  TRUST_BOUNDARY: "fill-rose-50 stroke-rose-400",
  CAPABILITY: "fill-emerald-50 stroke-emerald-400",
};

export function ArchitectureGraphView({ graph }: { graph: ArchitectureGraph }) {
  if (graph.nodes.length === 0) {
    return (
      <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
        No architecture graph — the system state carries an honest non-success recovery status
        instead of an invented topology.
      </p>
    );
  }
  const positioned = layout(graph);
  const byId = new Map(positioned.map((p) => [p.node.id, p]));
  const width = Math.max(...positioned.map((p) => p.x + p.w)) + 20;
  const height = Math.max(...positioned.map((p) => p.y + p.h)) + 20;

  return (
    <div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white p-2">
        <svg
          role="img"
          aria-label={`Architecture graph: ${graph.nodes.length} nodes, ${graph.edges.length} edges`}
          viewBox={`0 0 ${width} ${height}`}
          className="min-w-[520px]"
          style={{ height: Math.min(height, 460) }}
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="fill-slate-400" />
            </marker>
          </defs>
          {graph.edges.map((edge) => {
            const from = byId.get(edge.source);
            const to = byId.get(edge.target);
            if (!from || !to) return null;
            const x1 = from.x + from.w;
            const y1 = from.y + from.h / 2;
            const x2 = to.x;
            const y2 = to.y + to.h / 2;
            const mid = (x1 + x2) / 2;
            return (
              <path
                key={edge.id}
                d={`M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`}
                fill="none"
                className="stroke-slate-400"
                strokeWidth={1.4}
                markerEnd="url(#arrow)"
              >
                <title>{`${edge.source} ${edge.kind.replaceAll("_", " ").toLowerCase()} ${edge.target} — ${edge.label}`}</title>
              </path>
            );
          })}
          {positioned.map(({ node, x, y, w, h }) => (
            <g key={node.id}>
              <rect x={x} y={y} width={w} height={h} rx={8} className={KIND_TONE[node.kind]} strokeWidth={1.5}>
                <title>{`${node.label} (${node.kind}) — ${node.notes}`}</title>
              </rect>
              <text x={x + w / 2} y={y + h / 2 + 4} textAnchor="middle" className="fill-slate-700" style={{ fontSize: 10, fontWeight: 600 }}>
                {node.label.length > 16 ? `${node.label.slice(0, 15)}…` : node.label}
              </text>
            </g>
          ))}
        </svg>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Nodes</h4>
          <ul className="scroll-area mt-2 space-y-1.5 pr-1">
            {graph.nodes.map((node) => (
              <li key={node.id} className="flex items-start gap-2 rounded-md border border-slate-100 bg-slate-50 px-2.5 py-1.5">
                <Badge tone="slate">{node.kind}</Badge>
                <div className="min-w-0">
                  <p className="font-mono text-xs font-semibold text-slate-700">{node.id}</p>
                  <p className="text-xs text-slate-600">{node.label} — {node.notes}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Edges</h4>
          <ul className="scroll-area mt-2 space-y-1.5 pr-1">
            {graph.edges.map((edge) => (
              <li key={edge.id} className="rounded-md border border-slate-100 bg-slate-50 px-2.5 py-1.5 text-xs text-slate-600">
                <span className="font-mono font-semibold text-slate-700">{edge.source}</span>
                <span className="mx-1.5 text-slate-400">—{edge.kind}→</span>
                <span className="font-mono font-semibold text-slate-700">{edge.target}</span>
                <span className="ml-1 text-slate-500">({edge.label})</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
