import Link from "next/link";
import type { ReactNode } from "react";
import { DemoBadge } from "@/components/ui/badge";

/**
 * Workspace top bar. The demo banner states the truth about fixture mode
 * (which API mode would be active otherwise) — never a fake "connected".
 * PUB-04: the header accepts the workspace switcher (children) and the
 * account menu (`accountSlot`) from the client shell bar.
 */
export function WorkspaceHeader({
  workspaceName,
  demoMode,
  apiBase,
  accountSlot = null,
  children = null,
}: {
  workspaceName: string;
  demoMode: boolean;
  apiBase: string | null;
  accountSlot?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/"
            className="flex items-center gap-2 rounded-lg px-1 py-0.5 transition-surface hover:opacity-80"
            aria-label="SOS home"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-teal-700 text-sm font-bold text-white">
              SOS
            </span>
          </Link>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{workspaceName}</p>
            <p className="hidden text-xs text-slate-500 sm:block">Mission-governed software evolution</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          {children}
          {demoMode ? (
            <DemoBadge label="DEMO DATA" />
          ) : (
            apiBase !== null && (
              <span className="hidden rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800 lg:inline">
                API: {apiBase || "same-origin"}
              </span>
            )
          )}
          {accountSlot}
        </div>
      </div>
    </header>
  );
}
