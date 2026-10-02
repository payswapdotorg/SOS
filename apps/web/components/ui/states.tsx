"use client";

import { Button as HeadlessButton } from "./button";
import { ApiError } from "@/lib/api/errors";

/**
 * Honest loading / error / empty states (work-order acceptance: "honest
 * loading/error/empty states everywhere"). A loading spinner never stands in
 * for data; an error names the failure; an empty state says what is empty.
 */

export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 px-4 py-8 text-sm text-slate-500" role="status" aria-live="polite">
      <span
        aria-hidden="true"
        className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-teal-600"
      />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  const code = error instanceof ApiError ? error.code : null;
  return (
    <div
      className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4 text-sm text-rose-900"
      role="alert"
    >
      <p className="font-semibold">Could not load this section</p>
      <p className="mt-1 font-mono text-xs break-all text-rose-700">
        {code ? `[${code}] ` : ""}
        {message}
      </p>
      {onRetry ? (
        <div className="mt-3">
          <HeadlessButton variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </HeadlessButton>
        </div>
      ) : null}
      <p className="mt-2 text-xs text-rose-600">
        This is a real error, not an empty result — no data was invented to fill the gap.
      </p>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-8 text-center" role="status">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
      <p className="mt-2 text-xs text-slate-400">
        EMPTY — observed and none present. (Distinct from UNKNOWN.)
      </p>
    </div>
  );
}
