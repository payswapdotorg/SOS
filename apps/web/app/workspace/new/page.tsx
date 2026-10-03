"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, FolderPlus } from "lucide-react";
import { DemoBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/states";
import { getSosClient } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";

const SLUG_RE = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;

/**
 * Workspace creation (PUB-04): a signed-in owner action. The slug mirrors
 * the API's validation exactly (client-side pre-check; the server remains
 * the authority). In fixture/demo mode the page explains honestly that
 * creation needs a configured API — it does not fake a workspace.
 */
export default function NewWorkspacePage() {
  const client = getSosClient();
  const demoMode = client.runtime.mode === "fixtures";
  const router = useRouter();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);

  const slugCandidate =
    slug || name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const slugValid = SLUG_RE.test(slugCandidate);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const workspace = await client.createWorkspace({
        name: name.trim(),
        slug: slugCandidate,
      });
      // Land in the fresh workspace (tenant-aware selection via ?ws=).
      router.push(`/workspace?ws=${encodeURIComponent(workspace.id)}`);
    } catch (cause) {
      setError(cause);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <Link
        href="/workspace"
        className="mb-5 inline-flex items-center gap-1.5 text-sm text-slate-500 transition-surface hover:text-teal-700"
      >
        <ArrowLeft aria-hidden="true" className="h-4 w-4" />
        Back to workspace
      </Link>
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <FolderPlus aria-hidden="true" className="h-4 w-4 text-teal-700" />
                New workspace
              </span>
            }
            description="A workspace is your tenant: missions, systems, evidence and decisions live inside it. You become its owner; membership roles are owner | member."
          />
          <CardBody>
            {demoMode ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4" role="note">
                <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
                  <DemoBadge label="DEMO DATA" />
                  Creation needs a real API session
                </p>
                <p className="mt-2 text-sm leading-relaxed text-amber-800">
                  This cockpit runs on fixture data with no backend, so there is no server to
                  create a workspace on — and no session to authorize it. The form below shows
                  the real flow disabled. Configure an API
                  (<code className="mx-1 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-xs">NEXT_PUBLIC_API_BASE</code>)
                  and sign in with GitHub to create workspaces for real.
                </p>
                <form className="mt-4 space-y-4 opacity-60" aria-label="Demo preview — workspace creation form (disabled)">
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">Workspace name</span>
                    <input
                      type="text"
                      disabled
                      placeholder="e.g. Newco Lab"
                      className="mt-1 min-h-[40px] w-full cursor-not-allowed rounded-lg border border-slate-300 bg-slate-100 px-3 text-sm text-slate-500"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">Slug</span>
                    <input
                      type="text"
                      disabled
                      placeholder="newco-lab"
                      className="mt-1 min-h-[40px] w-full cursor-not-allowed rounded-lg border border-slate-300 bg-slate-100 px-3 font-mono text-sm text-slate-500"
                    />
                  </label>
                  <button
                    type="button"
                    disabled
                    className="inline-flex min-h-[40px] cursor-not-allowed items-center rounded-lg border border-slate-300 bg-slate-100 px-4 text-sm font-medium text-slate-400"
                  >
                    Create workspace (disabled in demo mode)
                  </button>
                </form>
              </div>
            ) : (
              <form
                className="space-y-4"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (name.trim() && slugValid && !submitting) void submit();
                }}
              >
                <label className="block">
                  <span className="text-sm font-medium text-slate-700">Workspace name</span>
                  <input
                    type="text"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    required
                    maxLength={120}
                    placeholder="e.g. Newco Lab"
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 shadow-xs transition-surface focus:border-teal-600 focus:ring-2 focus:ring-teal-100 focus:outline-none"
                  />
                </label>
                <label className="block">
                  <span className="text-sm font-medium text-slate-700">Slug</span>
                  <input
                    type="text"
                    value={slug || slugCandidate}
                    onChange={(event) => setSlug(event.target.value.toLowerCase())}
                    required
                    maxLength={64}
                    placeholder="newco-lab"
                    aria-describedby="slug-help"
                    className="mt-1 min-h-[44px] w-full rounded-lg border border-slate-300 bg-white px-3 font-mono text-sm text-slate-900 shadow-xs transition-surface focus:border-teal-600 focus:ring-2 focus:ring-teal-100 focus:outline-none"
                  />
                  <span id="slug-help" className="mt-1 block text-xs text-slate-500">
                    Lowercase letters, digits and single dashes; 3–64 chars. The server validates
                    the same rule — the slug must be globally unique.
                  </span>
                </label>
                {!slugValid && (name || slug) ? (
                  <p className="text-xs text-rose-600" role="alert">
                    The slug must match <code className="font-mono">^[a-z0-9][a-z0-9-]&#123;1,62&#125;[a-z0-9]$</code>.
                  </p>
                ) : null}
                {error ? (
                  <ErrorState error={error} />
                ) : null}
                {error instanceof ApiError && error.status === 401 ? (
                  <p className="text-sm text-slate-600">
                    You are not signed in.{" "}
                    <Link href="/signin" className="font-medium text-teal-700 underline">
                      Sign in with GitHub
                    </Link>{" "}
                    to create a workspace.
                  </p>
                ) : null}
                <div className="flex items-center gap-3 pt-1">
                  <Button
                    type="submit"
                    disabled={!name.trim() || !slugValid || submitting}
                  >
                    {submitting ? "Creating…" : "Create workspace"}
                  </Button>
                  <span className="text-xs text-slate-500">
                    You become the owner; the creation is audited.
                  </span>
                </div>
              </form>
            )}
          </CardBody>
        </Card>
    </div>
  );
}
