import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "article" | "div";
}) {
  return (
    <Tag
      className={`rounded-xl border border-slate-200 bg-white shadow-xs transition-surface hover:shadow-sm ${className}`}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  description,
  actions,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  id?: string;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3 sm:px-6">
      <div className="min-w-0">
        <h3 id={id} className="text-sm font-semibold tracking-tight text-slate-900 sm:text-base">
          {title}
        </h3>
        {description ? (
          <p className="mt-1 text-xs text-slate-500 sm:text-sm">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function CardBody({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`px-4 py-4 sm:px-6 ${className}`}>{children}</div>;
}
