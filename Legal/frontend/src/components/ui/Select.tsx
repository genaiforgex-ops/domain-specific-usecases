import type { SelectHTMLAttributes } from "react";

import { classNames } from "@/lib/utils";

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

export function Select({ label, error, className, id, children, ...rest }: Props) {
  const inputId = id || (label ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  return (
    <label className="block w-full" htmlFor={inputId}>
      {label && (
        <span className="block text-subheadline font-medium text-label mb-1.5">{label}</span>
      )}
      <select
        id={inputId}
        className={classNames(
          "block w-full min-h-tap rounded-md border border-separator/55 px-4 py-2.5",
          "text-body text-label bg-paper",
          "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25",
          error && "border-error",
          className,
        )}
        {...rest}
      >
        {children}
      </select>
      {error && (
        <span className="block text-footnote text-error mt-1.5" role="alert">
          {error}
        </span>
      )}
    </label>
  );
}
