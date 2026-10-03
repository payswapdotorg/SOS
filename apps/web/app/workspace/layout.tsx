import type { ReactNode } from "react";
import { Suspense } from "react";
import { WorkspaceHeaderBar } from "@/components/shell/workspace-header-bar";
import { WorkspaceNav } from "@/components/shell/workspace-nav";
import { SiteFooter } from "@/components/shell/site-footer";

/**
 * Workspace shell — left nav (Mission / Systems / Evidence / Candidates /
 * Experiments / Decisions / Memory / Activity) + main area per section.
 * Sticky footer via the root flex column + mt-auto. PUB-04: the header is
 * the tenant-aware client bar (workspace switcher + account menu); the nav
 * preserves the `?ws=` selection (Suspense: search-params read).
 */
export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <WorkspaceHeaderBar />
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-0 sm:px-6 lg:flex-row lg:gap-8 lg:px-6">
        <aside
          aria-label="Workspace navigation"
          className="shrink-0 border-b border-slate-200 bg-white px-4 py-3 lg:w-56 lg:border-none lg:py-8"
        >
          <Suspense fallback={<nav aria-label="Workspace sections" />}>
            <WorkspaceNav />
          </Suspense>
        </aside>
        <main id="main" className="min-w-0 flex-1 px-4 py-6 sm:px-0 lg:py-8">
          {children}
        </main>
      </div>
      <SiteFooter />
    </div>
  );
}
