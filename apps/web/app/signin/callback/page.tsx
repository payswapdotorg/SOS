"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { SiteFooter } from "@/components/shell/site-footer";
import { getSosClient, isSafeRelativePath } from "@/lib/api/client";
import type { SessionInfo } from "@/lib/api/types";

export default function SignInCallbackPage() {
  return (
    <Suspense fallback={<CallbackBody status="loading" />}>
      <CallbackResolver />
    </Suspense>
  );
}

const REASONS: Record<string, string> = {
  invalid_state:
    "The sign-in link expired or was already used. Start the flow again — authorization states are single-use and valid for 10 minutes.",
  replayed_state:
    "This authorization state was already consumed (single-use, replay-protected). Start the flow again.",
  expired_state:
    "The authorization state expired before GitHub returned. Start the flow again.",
  authorization_denied:
    "The authorization was denied on GitHub. Nothing was signed in — you can try again any time.",
  provider_unconfigured:
    "The API has no GitHub OAuth credentials configured (SOS_GITHUB_CLIENT_ID / SOS_GITHUB_CLIENT_SECRET). This is an operator input — sign-in is unavailable until it is set.",
  auth_store_unavailable:
    "The API's session store is not available in this deployment mode. This is an operator-side configuration issue.",
  exchange_failed:
    "The code exchange with GitHub failed. No session was issued — no partial or fake sign-in is performed.",
  identity_failed:
    "The GitHub identity could not be resolved from the issued token. No session was issued.",
  invalid_request:
    "The OAuth callback was malformed (missing code or state). No session was issued.",
};

function CallbackResolver() {
  const params = useSearchParams();
  const status = params.get("status") ?? "loading";
  const reason = params.get("reason");
  const nextParam = params.get("next");
  return (
    <CallbackBody
      status={status}
      reason={reason ?? undefined}
      nextPath={nextParam ?? undefined}
    />
  );
}

function CallbackBody({
  status,
  reason,
  nextPath,
}: {
  status: string;
  reason?: string;
  nextPath?: string;
}) {
  const router = useRouter();
  const client = getSosClient();
  const demoMode = client.runtime.mode === "fixtures";
  const [phase, setPhase] = useState<"checking" | "done" | "no-session">(
    "checking",
  );
  const [session, setSession] = useState<SessionInfo | null>(null);

  useEffect(() => {
    if (status !== "ok") return;
    let cancelled = false;
    // Idempotent read: safe under StrictMode double-mount (each attempt
    // checks its own cancelled flag; no cross-attempt ref guard).
    client
      .session()
      .then((info) => {
        if (cancelled) return;
        setSession(info);
        setPhase(info.authenticated ? "done" : "no-session");
        if (info.authenticated) {
          const target =
            nextPath && isSafeRelativePath(nextPath) ? nextPath : "/workspace";
          router.replace(target);
        }
      })
      .catch(() => {
        if (!cancelled) setPhase("no-session");
      });
    return () => {
      cancelled = true;
    };
  }, [status, client, nextPath, router]);

  const target =
    nextPath && isSafeRelativePath(nextPath) ? nextPath : "/workspace";

  return (
    <div className="flex min-h-screen flex-col">
      <main
        id="main"
        className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center px-4 py-12 sm:px-6"
      >
        <section
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs sm:p-8"
          aria-live="polite"
        >
          {status === "ok" ? (
            phase === "checking" ? (
              <div className="flex items-center gap-3 text-slate-600">
                <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-teal-700" />
                <div>
                  <p className="text-sm font-semibold text-slate-900">
                    Completing sign-in…
                  </p>
                  <p className="mt-0.5 text-sm text-slate-600">
                    Verifying the session cookie the API just issued.
                  </p>
                </div>
              </div>
            ) : phase === "done" ? (
              <div className="flex items-start gap-3">
                <CheckCircle2 aria-hidden="true" className="mt-0.5 h-6 w-6 text-emerald-600" />
                <div>
                  <h1 className="text-lg font-bold tracking-tight text-slate-900">
                    Signed in as {session?.user?.login ?? "…"}
                  </h1>
                  <p className="mt-1 text-sm text-slate-600">
                    Redirecting to your workspace…{" "}
                    <Link href={target} className="font-medium text-teal-700 underline">
                      continue now
                    </Link>
                    .
                  </p>
                  {session?.provider === "fake-github" ? (
                    <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                      LOCAL test mode: this session came from the deterministic
                      fake-GitHub provider (clearly labeled — never enabled for
                      public deployments).
                    </p>
                  ) : null}
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <AlertCircle aria-hidden="true" className="mt-0.5 h-6 w-6 text-rose-600" />
                <div>
                  <h1 className="text-lg font-bold tracking-tight text-slate-900">
                    No session arrived
                  </h1>
                  <p className="mt-1 text-sm text-slate-600">
                    The flow reported success but the session cookie is not
                    present. This can happen when cookies are blocked or the
                    API is misconfigured — nothing was partially signed in.
                    Try again from the sign-in page.
                  </p>
                  <Link
                    href="/signin"
                    className="mt-4 inline-flex min-h-[40px] items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50"
                  >
                    Back to sign-in
                  </Link>
                </div>
              </div>
            )
          ) : status === "error" ? (
            <div className="flex items-start gap-3">
              <AlertCircle aria-hidden="true" className="mt-0.5 h-6 w-6 text-rose-600" />
              <div>
                <h1 className="text-lg font-bold tracking-tight text-slate-900">
                  Sign-in did not complete
                </h1>
                <p className="mt-1 text-sm leading-relaxed text-slate-600">
                  {reason && REASONS[reason]
                    ? REASONS[reason]
                    : "The authorization flow failed. No session was issued — no partial or fake sign-in is performed."}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Reason reported by the API:{" "}
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">{reason ?? "unknown"}</code>
                </p>
                <Link
                  href="/signin"
                  className="mt-4 inline-flex min-h-[40px] items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50"
                >
                  Try again
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 text-slate-600">
              <Loader2 aria-hidden="true" className="h-5 w-5 animate-spin text-teal-700" />
              <p className="text-sm">Waiting for the authorization result…</p>
            </div>
          )}
          {demoMode ? (
            <p className="mt-4 text-xs text-slate-500">
              Demo mode note: this page normally completes the API-issued
              session; with no API configured it can only explain itself.
            </p>
          ) : null}
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
