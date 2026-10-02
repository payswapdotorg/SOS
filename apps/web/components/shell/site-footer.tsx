import Link from "next/link";

/**
 * Site footer — sticks to the bottom of the viewport on short pages and is
 * pushed down naturally when content is longer (root layout uses
 * min-h-screen flex-col; this footer carries mt-auto).
 */
export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-slate-200 bg-slate-50">
      <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          <span className="font-semibold text-slate-700">SOS</span> — Mission-governed software
          evolution.
        </p>
        <p className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-bold tracking-wide text-amber-900">
            DEMO DATA
          </span>
          <span>
            Demo mode: no backend configured — fixtures labeled honestly. Candidate comparison is
            multi-objective (no single AI score).
          </span>
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
