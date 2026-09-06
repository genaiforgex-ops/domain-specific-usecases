import type { InputHTMLAttributes } from "react";

import { classNames } from "@/lib/utils";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({ label, error, className, id, ...rest }: Props) {
  const inputId = id || (label ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  return (
    <label className="block w-full" htmlFor={inputId}>
      {label && (
        <span className="block text-subheadline font-medium text-label mb-1.5">{label}</span>
      )}
      <input
        id={inputId}
        className={classNames(
          "block w-full min-h-tap rounded-md border border-separator/55 px-4 py-2.5",
          "text-body text-label bg-paper",
          "placeholder:text-label-tertiary",
          "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25",
          error && "border-error focus:border-error focus:ring-error/20",
          className,
        )}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${inputId}-error` : undefined}
        {...rest}
      />
      {error && (
        <span id={`${inputId}-error`} className="block text-footnote text-error mt-1.5" role="alert">
          {error}
        </span>
      )}
    </label>
  );
}
