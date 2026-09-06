import type { ButtonHTMLAttributes, ReactNode } from "react";

import { classNames } from "@/lib/utils";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  size?: "sm" | "md";
  children: ReactNode;
}

export function Button({ variant = "primary", size = "md", className, children, ...rest }: Props) {
  const base = classNames(
    "inline-flex items-center justify-center font-medium rounded-md tracking-tight",
    "min-h-tap transition-all duration-fast ease-standard",
    "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
    "active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100",
  );
  const sz = size === "sm" ? "px-3 py-2 text-subheadline min-h-[36px]" : "px-4 py-2.5 text-body";
  const variants: Record<string, string> = {
    primary: "bg-accent text-white hover:bg-accent-bright",
    secondary:
      "bg-paper text-label border border-separator/70 hover:border-accent/30 hover:bg-bg",
    danger: "bg-error text-white hover:opacity-90",
    ghost: "text-label-secondary hover:bg-bg-secondary hover:text-label",
  };
  return (
    <button className={classNames(base, sz, variants[variant], className)} {...rest}>
      {children}
    </button>
  );
}
