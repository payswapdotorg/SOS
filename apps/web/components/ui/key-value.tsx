import type { ReactNode } from "react";

/** Key/value display row with honest "not set" handling. */
export function KeyValue({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-1 gap-0.5 py-1.5 sm:grid-cols-[minmax(7rem,10rem)_1fr] sm:gap-3">
      <dt className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</dt>
      <dd className={`text-sm text-slate-800 ${mono ? "font-mono text-xs break-all" : ""}`}>
        {children}
      </dd>
    </div>
  );
}

export function DefinitionList({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <dl className={`divide-y divide-slate-100 ${className}`}>{children}</dl>;
}

/** Section label used across section pages. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="text-xs font-semibold tracking-widest text-teal-700 uppercase">{eyebrow}</p>
        <h1 className="mt-1 text-xl font-bold tracking-tight text-slate-900 sm:text-2xl">{title}</h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm text-slate-600">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
