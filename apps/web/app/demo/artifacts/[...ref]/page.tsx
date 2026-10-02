import Link from "next/link";
import { ArrowLeft, FileWarning } from "lucide-react";
import { DemoBadge } from "@/components/ui/badge";
import { SiteFooter } from "@/components/shell/site-footer";

/**
 * Demo artifact landing route. Fixture signed URLs (relative
 * `/demo/artifacts/…?sig=…`) resolve here so artifact links in the demo are
 * honest: they clearly explain that real deployments resolve signed R2
 * objects, rather than 404ing or pretending to serve a file.
 */
export default async function DemoArtifactPage({
  params,
}: {
  params: Promise<{ ref: string[] }>;
}) {
  const { ref } = await params;
  const name = ref.length > 0 ? ref[ref.length - 1] : "artifact";
  return (
    <div className="flex min-h-screen flex-col">
      <main
        id="main"
        className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 py-12 sm:px-6"
      >
        <Link
          href="/workspace/evidence"
          className="mb-6 inline-flex items-center gap-1.5 text-sm text-slate-500 transition-surface hover:text-teal-700"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          Back to Evidence
        </Link>
        <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6 sm:p-10">
          <div className="flex items-center gap-3">
            <FileWarning aria-hidden="true" className="h-6 w-6 text-amber-700" />
            <h1 className="text-xl font-bold tracking-tight text-amber-900">Demo artifact</h1>
            <DemoBadge />
          </div>
          <p className="mt-3 break-all font-mono text-xs text-amber-800">{name}</p>
          <p className="mt-4 text-sm leading-relaxed text-amber-900">
            This is a fixture artifact reference from the demo dataset. In a real deployment,
            evidence artifacts resolve to <strong>signed R2 object URLs</strong> (private bucket,
            time-limited signature) fetched through the API — never embedded in database rows. The
            demo does not serve a real object, and it does not pretend to.
          </p>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
