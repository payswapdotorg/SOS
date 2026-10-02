"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  Beaker,
  Boxes,
  Compass,
  FileSearch,
  Gauge,
  History,
  ScrollText,
} from "lucide-react";

const NAV = [
  { href: "/workspace", label: "Mission", icon: Compass, exact: true },
  { href: "/workspace/systems", label: "Systems", icon: Boxes, exact: false },
  { href: "/workspace/evidence", label: "Evidence", icon: FileSearch, exact: false },
  { href: "/workspace/candidates", label: "Candidates", icon: Gauge, exact: false },
  { href: "/workspace/experiments", label: "Experiments", icon: Beaker, exact: false },
  { href: "/workspace/decisions", label: "Decisions", icon: ScrollText, exact: false },
  { href: "/workspace/memory", label: "Memory", icon: History, exact: false },
  { href: "/workspace/activity", label: "Activity", icon: Activity, exact: false },
] as const;

function isActive(pathname: string, href: string, exact: boolean): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * Static variant (no router hooks) — unit-testable; the interactive
 * `WorkspaceNav` renders it with the live pathname.
 */
export function WorkspaceNavStatic({ currentPath = "/workspace" }: { currentPath?: string }) {
  return (
    <nav aria-label="Workspace sections">
      <ul className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
        {NAV.map(({ href, label, icon: Icon, exact }) => {
          const active = isActive(currentPath, href, exact);
          return (
            <li key={href} className="shrink-0 lg:shrink">
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-[40px] items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-surface ${
                  active
                    ? "bg-teal-50 text-teal-800 ring-1 ring-teal-200"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <Icon aria-hidden="true" className="h-4 w-4" />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function WorkspaceNav({ ariaLabelledBy }: { ariaLabelledBy?: string }) {
  const pathname = usePathname() ?? "/workspace";
  return (
    <div aria-labelledby={ariaLabelledBy}>
      <WorkspaceNavStatic currentPath={pathname} />
    </div>
  );
}
