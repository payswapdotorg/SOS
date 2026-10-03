import Link from "next/link";
import { getSosClient } from "@/lib/api/client";

/**
 * Site footer — sticks to the bottom of the viewport on short pages and is
 * pushed down naturally when content is longer (root layout uses
 * min-h-screen flex-col; this footer carries mt-auto). The mode note
 * states the truth about the active runtime (fixtures vs API) — never a
 * static claim.
 */
export function SiteFooter() {
  const client = getSosClient();
  const demoMode = client.runtime.mode === "fixtures";
  return (
    <footer className="mt-auto border-t border-slate-200 bg-slate-50">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          <span className="font-semibold text-slate-700">SOS</span> — Mission-governed software
          evolution.
        </p>
        <p className="flex flex-wrap items-center gap-2">
          {demoMode ? (
            <>
              <span className="inline-flex items-center rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-bold tracking-wide text-amber-900">
                DEMO DATA
              </span>
              <span>
                Demo mode: no backend configured — fixtures labeled honestly. Candidate
                comparison is multi-objective (no single AI score).
              </span>
            </>
          ) : (
            <span>
              Candidate comparison is multi-objective (no single AI score). Sessions are
              httpOnly cookies; the browser never holds tokens.
            </span>
          )}
        </p>
        <nav aria-label="Footer" className="flex items-center gap-4">
          <Link href="/" className="transition-surface hover:text-teal-700">
            Landing
          </Link>
          <Link href="/signin" className="transition-surface hover:text-teal-700">
            Sign in
          </Link>
        </nav>
      </div>
    </footer>
  );
}
