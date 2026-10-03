import Link from "next/link";
import { ArrowLeft, KeyRound, LogIn, ShieldCheck } from "lucide-react";
import { GithubMark } from "@/components/shell/github-mark";
import { SiteFooter } from "@/components/shell/site-footer";
import { githubStartUrl, getSosClient } from "@/lib/api/client";

export const metadata = {
  title: "Sign in with GitHub",
};

/**
 * Sign-in route (PUB-04: the real flow against the API). The button is a
 * plain navigation to the API's OAuth start endpoint (state + PKCE are
 * server-held; the browser never sees a token). In fixture/demo mode no
 * OAuth is performed; the page explains the flow honestly instead of
 * pretending to authenticate.
 */
export default function SignInPage() {
  const client = getSosClient();
  const demoMode = client.runtime.mode === "fixtures";
  const startUrl = githubStartUrl(client.runtime, "/workspace");

  return (
    <div className="flex min-h-screen flex-col">
      <main id="main" className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-12 sm:px-6">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1.5 text-sm text-slate-500 transition-surface hover:text-teal-700"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to landing
        </Link>
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-xs sm:p-10">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Sign in with GitHub</h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            SOS uses GitHub OAuth for identity. Your GitHub identity maps to an SOS user inside a
            tenant workspace — brownfield onboarding connects naturally from there. The browser
            never receives or stores OAuth tokens; sessions are httpOnly cookies issued by the API.
          </p>

          <ol className="mt-6 space-y-4">
            <li className="flex gap-3">
              <LogIn aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-700" />
              <div>
                <p className="text-sm font-semibold text-slate-800">1. Start the OAuth flow</p>
                <p className="mt-0.5 text-sm text-slate-600">
                  The cockpit navigates to the API&apos;s authorization start endpoint with
                  single-use CSRF state and PKCE (the verifier stays server-side).
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <KeyRound aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-700" />
              <div>
                <p className="text-sm font-semibold text-slate-800">2. Authorize on GitHub</p>
                <p className="mt-0.5 text-sm text-slate-600">
                  You approve the SOS application (read:user) on github.com; the callback lands on
                  the API, never in the browser with a token.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <ShieldCheck aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 text-teal-700" />
              <div>
                <p className="text-sm font-semibold text-slate-800">3. Session + workspace</p>
                <p className="mt-0.5 text-sm text-slate-600">
                  The API issues a session cookie; the cockpit switches from demo fixtures to your
                  real workspace (tenant-scoped, server-validated — the browser never supplies the
                  tenant id). Sign out revokes the session server-side.
                </p>
              </div>
            </li>
          </ol>

          {demoMode ? (
            <div className="mt-8 rounded-lg border border-amber-200 bg-amber-50 p-4" role="note">
              <p className="text-sm font-semibold text-amber-900">
                Demo mode — no OAuth is performed here
              </p>
              <p className="mt-1 text-sm leading-relaxed text-amber-800">
                This cockpit has no API configured (<code className="mx-1 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-xs">NEXT_PUBLIC_API_BASE</code>
                unset), so signing in has nothing to authenticate against. The button intentionally
                does nothing except explain the flow — it does not fake a login. Explore the demo
                workspace instead.
              </p>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <Link
                  href="/workspace"
                  className="inline-flex min-h-[40px] items-center justify-center rounded-lg border border-teal-700 bg-teal-700 px-4 py-2 text-sm font-semibold text-white transition-surface hover:bg-teal-800"
                >
                  Explore Demo
                </Link>
                <span
                  aria-disabled="true"
                  className="inline-flex min-h-[40px] cursor-not-allowed items-center justify-center gap-2 rounded-lg border border-slate-300 bg-slate-100 px-4 py-2 text-sm font-medium text-slate-400"
                >
                  <GithubMark className="h-4 w-4" />
                  Sign in with GitHub (needs a configured API)
                </span>
              </div>
            </div>
          ) : (
            <a
              href={startUrl}
              className="mt-8 inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg border border-slate-900 bg-slate-900 px-5 py-2.5 text-sm font-semibold text-white transition-surface hover:bg-slate-700"
            >
              <GithubMark className="h-4 w-4" />
              Continue with GitHub
            </a>
          )}
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
