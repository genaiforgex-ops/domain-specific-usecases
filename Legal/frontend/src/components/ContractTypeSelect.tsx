import { useEffect, useState } from "react";

import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

const PRESETS = ["MSA", "NDA", "Others"] as const;
export type ContractTypePreset = (typeof PRESETS)[number];

function presetForValue(value: string): ContractTypePreset {
  if (value === "MSA" || value === "NDA") return value;
  return "Others";
}

export function resolveContractType(preset: ContractTypePreset, customType: string): string {
  if (preset === "Others") return customType.trim().slice(0, 32);
  return preset;
}

interface Props {
  value: string;
  onChange: (contractType: string) => void;
  label?: string;
  className?: string;
}

export function ContractTypeSelect({ value, onChange, label = "Contract type", className }: Props) {
  const [preset, setPreset] = useState<ContractTypePreset>(() => presetForValue(value));
  const [customType, setCustomType] = useState(() =>
    presetForValue(value) === "Others" ? value : "",
  );

  useEffect(() => {
    const nextPreset = presetForValue(value);
    setPreset(nextPreset);
    if (nextPreset === "Others") setCustomType(value);
  }, [value]);

  function update(nextPreset: ContractTypePreset, nextCustom: string) {
    setPreset(nextPreset);
    setCustomType(nextCustom);
    onChange(resolveContractType(nextPreset, nextCustom));
  }

  return (
    <div className={className}>
      <Select
        label={label}
        value={preset}
        onChange={(e) => {
          const next = e.target.value as ContractTypePreset;
          update(next, customType);
        }}
      >
        {PRESETS.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </Select>
      {preset === "Others" && (
        <div className="mt-3">
          <Input
            label="Document type"
            value={customType}
            onChange={(e) => update("Others", e.target.value)}
            placeholder="e.g. SOW, DPA, Vendor Agreement"
            maxLength={32}
            required
          />
        </div>
      )}
    </div>
  );
}
