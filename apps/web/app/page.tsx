import Link from "next/link";
import { ArrowRight, Beaker, Compass, FileSearch, Gauge, GitBranch, ScrollText, ShieldCheck } from "lucide-react";
import { GithubMark } from "@/components/shell/github-mark";
import { SiteFooter } from "@/components/shell/site-footer";
import { DemoBadge } from "@/components/ui/badge";
import { getSosClient } from "@/lib/api/client";

const PILLARS = [
  {
    icon: Compass,
    title: "Mission first",
    body: "The mission — goals, outcomes, stakeholders, measures, constraints, preferences — is the authority. You approve every revision.",
  },
  {
    icon: FileSearch,
    title: "Honest evidence",
    body: "Success, empty, failed, unknown, unsupported and unavailable stay distinct. Missing data is never dressed up as success.",
  },
  {
    icon: Gauge,
    title: "Multi-objective candidates",
    body: "Trade-offs across mission effect, cost, risk, constraints, evidence and reversibility. Pareto reasoning — no fake single AI score.",
  },
  {
    icon: ScrollText,
    title: "Visible decisions",
    body: "Every consequential action shows its governing decision: why, evidence, authority, blast radius, reversibility, approvals.",
  },
  {
    icon: ShieldCheck,
    title: "Assurance before promotion",
    body: "Candidates pass checks and verdicts before any live stage. Rollback paths dominate untrusted behavior.",
  },
  {
    icon: Beaker,
    title: "Experiments with receipts",
    body: "Bounded experiments (shadow, canary) with events, executions and provider receipts — demo receipts are badged DEMO.",
  },
];

export default function LandingPage() {
  const client = getSosClient();
  const demoMode = client.runtime.mode === "fixtures";
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-200">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-teal-700 text-sm font-bold text-white">
              SOS
            </span>
            <span className="text-lg font-bold tracking-tight text-slate-900">SOS</span>
          </div>
          <nav aria-label="Landing" className="flex items-center gap-2">
            <Link
              href="/signin"
              className="inline-flex min-h-[40px] items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-surface hover:bg-slate-50"
            >
              <GithubMark className="h-4 w-4" />
              Sign in with GitHub
            </Link>
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-12 sm:px-6 sm:py-20">
        <section aria-labelledby="hero-heading" className="mx-auto max-w-3xl text-center">
          <h1 id="hero-heading" className="text-4xl font-extrabold tracking-tight text-slate-900 sm:text-6xl">
            SOS
          </h1>
          <p className="mt-4 text-lg text-slate-600 sm:text-xl">
            Mission-governed software evolution
          </p>
          <p className="mx-auto mt-6 max-w-2xl text-sm leading-relaxed text-slate-600 sm:text-base">
            SOS treats your software system as a changing system state that exists to realize a
            mission. It observes evidence, forms hypotheses, proposes candidate system states, and
            lets every consequential decision be governed, audited and reversible — with you as the
            mission authority.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/workspace"
              className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg border border-teal-700 bg-teal-700 px-6 py-2.5 text-sm font-semibold text-white transition-surface hover:bg-teal-800 sm:w-auto"
            >
              Explore Demo
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </Link>
            <Link
              href="/signin"
              className="inline-flex min-h-[44px] w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-6 py-2.5 text-sm font-semibold text-slate-700 transition-surface hover:bg-slate-50 sm:w-auto"
            >
              <GithubMark className="h-4 w-4" />
              Sign in with GitHub
            </Link>
          </div>
          {demoMode ? (
            <p className="mt-4 flex items-center justify-center gap-2 text-xs text-slate-500">
              <DemoBadge label="DEMO DATA" />
              No backend configured — the demo workspace is served from typed, honestly-labeled
              fixtures.
            </p>
          ) : null}
        </section>

        <section aria-labelledby="pillars-heading" className="mt-16 sm:mt-24">
          <h2 id="pillars-heading" className="sr-only">
            What the cockpit shows
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PILLARS.map(({ icon: Icon, title, body }) => (
              <article
                key={title}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs transition-surface hover:shadow-sm"
              >
                <Icon aria-hidden="true" className="h-5 w-5 text-teal-700" />
                <h3 className="mt-3 text-sm font-semibold text-slate-900">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{body}</p>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="journey-heading" className="mt-16 sm:mt-24">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 sm:p-10">
            <h2 id="journey-heading" className="flex items-center gap-2 text-lg font-bold tracking-tight text-slate-900">
              <GitBranch aria-hidden="true" className="h-5 w-5 text-teal-700" />
              The governing loop, visible end to end
            </h2>
            <p className="mt-2 max-w-2xl text-sm text-slate-600">
              Every consequential evolution decision is traceable through the frozen architecture
              chain — nothing is optimized in isolation:
            </p>
            <ol className="mt-6 flex flex-wrap items-center gap-2 text-xs font-medium">
              {[
                "Mission",
                "Goals",
                "Outcomes",
                "Stakeholders",
                "Measures",
                "Constraints",
                "Preferences",
                "System State",
                "Evidence",
                "Hypothesis",
                "Candidate",
                "Assurance",
                "Decision",
                "Experiment",
                "Promotion / Rollback",
                "Learning",
              ].map((step, index, all) => (
                <li key={step} className="flex items-center gap-2">
                  <span className="rounded-full border border-teal-200 bg-white px-3 py-1 text-teal-800">
                    {step}
                  </span>
                  {index < all.length - 1 ? (
                    <span aria-hidden="true" className="text-slate-400">
                      →
                    </span>
                  ) : null}
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
