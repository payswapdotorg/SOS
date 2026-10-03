"use client";

import { Suspense } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronsUpDown } from "lucide-react";
import { WorkspaceHeader } from "./workspace-header";
import { AccountMenu } from "./account-menu";
import { useWorkspaceSelection } from "@/hooks/use-workspace-selection";
import { getSosClient } from "@/lib/api/client";

/**
 * The tenant-aware header bar (PUB-04): the selected workspace name, a
 * workspace switcher restricted to the SERVER-visible (tenant-scoped)
 * workspaces, and the account menu. Suspense wraps the search-params read
 * (prerender-safe).
 */
export function WorkspaceHeaderBar() {
  return (
    <Suspense
      fallback={
        <WorkspaceHeader
          workspaceName="…"
          demoMode={false}
          apiBase={null}
        />
      }
    >
      <HeaderBarInner />
    </Suspense>
  );
}

function HeaderBarInner() {
  const client = getSosClient();
  const isDemo = client.runtime.mode === "fixtures";
  const selection = useWorkspaceSelection();
  const router = useRouter();
  const pathname = usePathname() ?? "/workspace";

  return (
    <WorkspaceHeader
      workspaceName={selection.selected?.name ?? (isDemo ? "Aurora Fulfillment (Demo)" : "Workspace")}
      demoMode={isDemo}
      apiBase={isDemo ? null : client.runtime.apiBase}
      accountSlot={<AccountMenu />}
    >
      {selection.workspaces.length > 0 ? (
        <label className="relative inline-flex items-center">
          <span className="sr-only">Select workspace</span>
          <ChevronsUpDown
            aria-hidden="true"
            className="pointer-events-none absolute right-2 h-3.5 w-3.5 text-slate-400"
          />
          <select
            value={selection.selected?.id ?? ""}
            onChange={(event) => {
              const id = event.target.value;
              const target = selection.workspaces.find((w) => w.id === id);
              if (!target) return; // only server-visible workspaces
              router.push(`${pathname}?ws=${encodeURIComponent(id)}`);
            }}
            disabled={selection.isLoading}
            className="min-h-[36px] max-w-[11rem] appearance-none rounded-lg border border-slate-300 bg-white py-1.5 pl-2.5 pr-7 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50 disabled:opacity-60 sm:max-w-[14rem]"
          >
            {selection.workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </WorkspaceHeader>
  );
}
