"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-teal-700 text-white hover:bg-teal-800 border border-teal-700",
  secondary: "bg-white text-slate-700 hover:bg-slate-50 border border-slate-300",
  ghost: "bg-transparent text-slate-600 hover:bg-slate-100 border border-transparent",
  danger: "bg-rose-700 text-white hover:bg-rose-800 border border-rose-700",
};

const SIZES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}) {
  return (
    <button
      className={`inline-flex min-h-[36px] cursor-pointer items-center justify-center gap-2 rounded-lg font-medium transition-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
