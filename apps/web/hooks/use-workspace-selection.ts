"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useResource } from "@/hooks/use-resource";
import type { Workspace } from "@/lib/api/types";

/**
 * Tenant-aware workspace selection (PUB-04).
 *
 * The selection is a URL concern (`?ws=<id>`) so it is shareable and the
 * back button works. The CANDIDATE list always comes from the server —
 * `GET /workspaces` is tenant-scoped by the session (the browser never
 * supplies the tenant identifier), so a `?ws=` value that is not in the
 * server-visible list is ignored, never trusted.
 */
export interface WorkspaceSelection {
  workspaces: Workspace[];
  selected: Workspace | null;
  isLoading: boolean;
  error: Error | null;
  select: (workspaceId: string) => void;
  refetch: () => void;
}

export function useWorkspaceSelection(): WorkspaceSelection {
  const router = useRouter();
  const pathname = usePathname() ?? "/workspace";
  const searchParams = useSearchParams();
  const wsParam = searchParams.get("ws");

  const listing = useResource<Workspace[]>(
    (c) => c.listWorkspaces().then((r) => r.items),
    [],
  );

  const workspaces = useMemo(() => listing.data ?? [], [listing.data]);
  // Only a server-visible workspace can be selected (tenant truth).
  const selected = useMemo(
    () => workspaces.find((w) => w.id === wsParam) ?? workspaces[0] ?? null,
    [workspaces, wsParam],
  );

  const select = useCallback(
    (workspaceId: string) => {
      const target = workspaces.find((w) => w.id === workspaceId);
      if (!target) return; // never trust an unlisted id
      router.push(`${pathname}?ws=${encodeURIComponent(workspaceId)}`);
    },
    [workspaces, pathname, router],
  );

  return {
    workspaces,
    selected,
    isLoading: listing.isLoading,
    error: listing.error,
    select,
    refetch: listing.refetch,
  };
}
