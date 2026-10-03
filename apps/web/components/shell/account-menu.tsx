"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogOut, Plus, UserCircle2 } from "lucide-react";
import { GithubMark } from "@/components/shell/github-mark";
import { useResource } from "@/hooks/use-resource";
import { getSosClient } from "@/lib/api/client";
import type { AccountInfo } from "@/lib/api/types";

/**
 * The account menu (PUB-04): sign-in state, the signed-in user, and the
 * sign-out action. Membership roles (owner/member) render on the workspace
 * switcher; this component owns the identity surface only. In fixture/demo
 * mode it states the demo truth instead of faking a session.
 */
export function AccountMenu() {
  const client = getSosClient();
  const demoMode = client.runtime.mode === "fixtures";
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const account = useResource<AccountInfo | null>(
    async (c) => {
      if (demoMode) return null; // no server → no session claims
      try {
        return await c.account();
      } catch {
        return null; // honest fallback: treat as signed out
      }
    },
    [demoMode],
  );

  if (demoMode) {
    return (
      <div className="flex items-center gap-2">
        <span className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 sm:inline-flex">
          <UserCircle2 aria-hidden="true" className="h-3.5 w-3.5" />
          demo viewer (no session)
        </span>
        <Link
          href="/signin"
          className="inline-flex min-h-[36px] items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50"
        >
          <GithubMark className="h-4 w-4" />
          <span className="hidden sm:inline">Sign in with GitHub</span>
          <span className="sm:hidden">Sign in</span>
        </Link>
      </div>
    );
  }

  if (account.isLoading) {
    return (
      <span className="text-xs text-slate-400" role="status">
        checking session…
      </span>
    );
  }

  const info = account.data;
  if (!info || !info.authenticated) {
    return (
      <Link
        href="/signin"
        className="inline-flex min-h-[36px] items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50"
      >
        <GithubMark className="h-4 w-4" />
        <span className="hidden sm:inline">Sign in with GitHub</span>
        <span className="sm:hidden">Sign in</span>
      </Link>
    );
  }

  const providerLabel =
    info.provider === "fake-github"
      ? "LOCAL fake-GitHub"
      : info.provider === "github"
        ? "GitHub"
        : info.stub
          ? "LOCAL stub"
          : info.provider;

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/workspace/new"
        className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg border border-teal-700 bg-white px-2.5 py-1.5 text-xs font-semibold text-teal-800 transition-surface hover:bg-teal-50"
      >
        <Plus aria-hidden="true" className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">New workspace</span>
        <span className="sm:hidden">New</span>
      </Link>
      <span
        className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700 md:inline-flex"
        title={`Session provider: ${info.provider}`}
      >
        <UserCircle2 aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
        <span className="font-semibold">{info.user?.login}</span>
        <span className="text-slate-400">· {providerLabel}</span>
      </span>
      <button
        type="button"
        onClick={async () => {
          setSigningOut(true);
          try {
            await client.logout();
          } finally {
            setSigningOut(false);
            router.replace("/");
            router.refresh();
          }
        }}
        disabled={signingOut}
        className="inline-flex min-h-[36px] items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50 disabled:opacity-60"
      >
        <LogOut aria-hidden="true" className="h-3.5 w-3.5" />
        {signingOut ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );
}
