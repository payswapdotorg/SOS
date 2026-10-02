import type { ReactNode } from "react";

/** Vertical timeline for experiment events and activity entries. */
export function Timeline({ children }: { children: ReactNode }) {
  return <ol className="relative space-y-0">{children}</ol>;
}

export function TimelineItem({
  at,
  title,
  badge,
  children,
}: {
  at: string;
  title: string;
  badge?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <li className="relative border-l border-slate-200 pb-5 pl-5 last:pb-0">
      <span
        aria-hidden="true"
        className="absolute top-1 -left-[5px] h-2.5 w-2.5 rounded-full border-2 border-white bg-teal-600"
      />
      <div className="flex flex-wrap items-center gap-2">
        <time className="font-mono text-xs text-slate-500">{at}</time>
        {badge}
      </div>
      <p className="mt-1 text-sm font-semibold text-slate-800">{title}</p>
      {children ? <div className="mt-1 text-sm text-slate-600">{children}</div> : null}
    </li>
  );
}
