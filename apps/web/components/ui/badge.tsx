import type { ReactNode } from "react";

/** Base badge chip. */
export function Badge({
  children,
  tone = "slate",
  className = "",
  title,
}: {
  children: ReactNode;
  tone?: "slate" | "teal" | "emerald" | "amber" | "rose" | "orange" | "zinc" | "violet";
  className?: string;
  title?: string;
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-100 text-slate-700 border-slate-200",
    teal: "bg-teal-50 text-teal-800 border-teal-200",
    emerald: "bg-emerald-50 text-emerald-800 border-emerald-200",
    amber: "bg-amber-50 text-amber-800 border-amber-200",
    rose: "bg-rose-50 text-rose-800 border-rose-200",
    orange: "bg-orange-50 text-orange-800 border-orange-200",
    zinc: "bg-zinc-100 text-zinc-600 border-zinc-300 border-dashed",
    violet: "bg-violet-50 text-violet-800 border-violet-200",
  };
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Explicit DEMO marker for demo data, receipts, and demo actions. */
export function DemoBadge({ label = "DEMO" }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-xs font-bold tracking-wide text-amber-900">
      {label}
    </span>
  );
}
