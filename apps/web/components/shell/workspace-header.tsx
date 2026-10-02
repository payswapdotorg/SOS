import Link from "next/link";
import { DemoBadge } from "@/components/ui/badge";
import { GithubMark } from "./github-mark";

/**
 * Workspace top bar. The demo banner states the truth about fixture mode
 * (which API mode would be active otherwise) — never a fake "connected".
 */
export function WorkspaceHeader({
  workspaceName,
  demoMode,
  apiBase,
}: {
  workspaceName: string;
  demoMode: boolean;
  apiBase: string | null;
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
        <div className="flex shrink-0 items-center gap-3">
          {demoMode ? (
            <DemoBadge label="DEMO DATA" />
          ) : (
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-800">
              API: {apiBase}
            </span>
          )}
          <Link
            href="/signin"
            className="inline-flex min-h-[36px] items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50"
          >
            <GithubMark className="h-4 w-4" />
            <span className="hidden sm:inline">Sign in with GitHub</span>
            <span className="sm:hidden">Sign in</span>
          </Link>
        </div>
      </div>
    </header>
  );
}
