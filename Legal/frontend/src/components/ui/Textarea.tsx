import type { TextareaHTMLAttributes } from "react";

import { classNames } from "@/lib/utils";

interface Props extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export function Textarea({ label, hint, error, className, id, ...rest }: Props) {
  const inputId = id || (label ? label.replace(/\s+/g, "-").toLowerCase() : undefined);
  return (
    <label className="block w-full" htmlFor={inputId}>
      {label && (
        <span className="block text-subheadline font-medium text-label mb-1.5">{label}</span>
      )}
      <textarea
        id={inputId}
        className={classNames(
          "block w-full min-h-[88px] rounded-md border border-separator/55 px-4 py-2.5",
          "text-body text-label bg-paper resize-y",
          "placeholder:text-label-tertiary",
          "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/25",
          error && "border-error focus:border-error focus:ring-error/20",
          className,
        )}
        aria-invalid={error ? true : undefined}
        {...rest}
      />
      {error && (
        <span className="block text-footnote text-error mt-1.5" role="alert">
          {error}
        </span>
      )}
      {hint && !error && (
        <span className="block text-footnote text-label-tertiary mt-1.5">{hint}</span>
      )}
    </label>
  );
}
