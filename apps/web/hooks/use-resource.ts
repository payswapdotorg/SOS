"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import type { SosClient } from "@/lib/api/client";
import { getSosClient } from "@/lib/api/client";

export interface ResourceState<T> {
  data: T | null;
  error: ApiError | Error | null;
  isLoading: boolean;
}

interface Snapshot<T> {
  key: string;
  data: T | null;
  error: ApiError | Error | null;
}

/**
 * The light data layer: loads a resource through the typed client with
 * honest loading / error / data states (no fake success, no swallowed
 * failures). `loader` receives the singleton client.
 *
 * Loading is DERIVED (no snapshot matches the requested key yet) rather
 * than set synchronously in the effect — a refetch shows the loading state
 * again because the old snapshot no longer matches the requested key, and
 * changed deps (e.g. another system id) load afresh.
 */
export function useResource<T>(
  loader: (client: SosClient) => Promise<T>,
  deps: readonly unknown[],
): ResourceState<T> & { refetch: () => void } {
  const client = getSosClient();
  const [tick, setTick] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot<T> | null>(null);

  const depsKey = JSON.stringify(deps);
  const key = `${depsKey}#${tick}`;

  useEffect(() => {
    let cancelled = false;
    const requestKey = `${depsKey}#${tick}`;
    loader(client)
      .then((data) => {
        if (!cancelled) setSnapshot({ key: requestKey, data, error: null });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const normalized =
          error instanceof ApiError || error instanceof Error ? error : new Error(String(error));
        setSnapshot({ key: requestKey, data: null, error: normalized });
      });
    return () => {
      cancelled = true;
    };
    // The loader identity is intentionally excluded: the effect re-runs when
    // the resource key changes, capturing that render's loader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, key]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);

  const resolved = snapshot !== null && snapshot.key === key ? snapshot : null;
  return {
    data: resolved?.data ?? null,
    error: resolved?.error ?? null,
    isLoading: resolved === null,
    refetch,
  };
}
