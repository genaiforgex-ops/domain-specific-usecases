import { useEffect, useState } from "react";

const STORAGE_KEY = "legalos-review-tour-done";

const STEPS = [
  "Upload or open a counterparty draft and select the arrangement type.",
  "Review AI findings linked to playbook clauses — accept, modify, or reject each one.",
  "Preview the combined redline in track mode before applying.",
  "Apply accepted changes — nothing is finalized without your explicit approval.",
];

export function ReviewOnboardingTour({ onDone }: { onDone?: () => void }) {
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(STORAGE_KEY)) setVisible(true);
  }, []);

  if (!visible) return null;

  function finish() {
    localStorage.setItem(STORAGE_KEY, "1");
    setVisible(false);
    onDone?.();
  }

  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 p-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-sm font-semibold text-label">UC-01 review tour · Step {step + 1}/4</p>
        <p className="text-sm text-label-secondary mt-1">{STEPS[step]}</p>
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          className="text-xs text-label-secondary hover:underline"
          onClick={finish}
        >
          Skip
        </button>
        {step < STEPS.length - 1 ? (
          <button
            type="button"
            className="text-xs font-medium text-accent hover:underline"
            onClick={() => setStep((s) => s + 1)}
          >
            Next
          </button>
        ) : (
          <button type="button" className="text-xs font-medium text-accent hover:underline" onClick={finish}>
            Done
          </button>
        )}
      </div>
    </div>
  );
}
