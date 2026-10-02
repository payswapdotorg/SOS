import type { ReactNode } from "react";
import { WorkspaceHeader } from "@/components/shell/workspace-header";
import { WorkspaceNav } from "@/components/shell/workspace-nav";
import { SiteFooter } from "@/components/shell/site-footer";
import { getSosClient } from "@/lib/api/client";
import { demo } from "@/lib/fixtures/demo";

/**
 * Workspace shell — left nav (Mission / Systems / Evidence / Candidates /
 * Experiments / Decisions / Memory / Activity) + main area per section.
 * Sticky footer via the root flex column + mt-auto.
 */
export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const client = getSosClient();
  const isDemo = client.runtime.mode === "fixtures";
  const workspaceName = isDemo ? demo.workspace.name : "Workspace";
  return (
    <div className="flex min-h-screen flex-col">
      <WorkspaceHeader
        workspaceName={workspaceName}
        demoMode={isDemo}
        apiBase={isDemo ? null : client.runtime.apiBase}
      />
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-0 sm:px-6 lg:flex-row lg:gap-8 lg:px-6">
        <aside
          aria-label="Workspace navigation"
          className="shrink-0 border-b border-slate-200 bg-white px-4 py-3 lg:w-56 lg:border-none lg:py-8"
        >
          <WorkspaceNav />
        </aside>
        <main id="main" className="min-w-0 flex-1 px-4 py-6 sm:px-0 lg:py-8">
          {children}
        </main>
      </div>
      <SiteFooter />
    </div>
  );
}
