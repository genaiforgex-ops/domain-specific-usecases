import { Textarea } from "@/components/ui/Textarea";

export function ReviewGuidelinesInput({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <Textarea
      label="Ground-truth guidelines (optional)"
      rows={3}
      placeholder={"One required term per line, e.g.\nJio Finance Platform and Service Limited\nDPDP Act 2023"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      hint="Exact phrases the document must contain — failures appear as high-risk findings."
    />
  );
}
