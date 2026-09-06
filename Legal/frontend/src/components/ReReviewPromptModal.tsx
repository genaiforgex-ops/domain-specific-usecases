import { Button } from "@/components/ui/Button";

export function ReReviewPromptModal({
  versionNumber,
  busy,
  onRun,
  onDismiss,
}: {
  versionNumber: number;
  busy?: boolean;
  onRun: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="bg-bg rounded-xl shadow-xl border border-separator/40 max-w-md w-full p-5 space-y-4"
        role="dialog"
        aria-labelledby="rereview-title"
      >
        <h2 id="rereview-title" className="text-lg font-semibold text-label">
          Re-run AI review on v{versionNumber}?
        </h2>
        <p className="text-sm text-label-secondary">
          Ground truth and playbook checks will run on the latest text. Pending suggestions are
          replaced; accept/reject decisions are kept when the original clause text is still in the
          document.
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onDismiss} disabled={busy}>
            Not now
          </Button>
          <Button onClick={onRun} disabled={busy}>
            {busy ? "Running…" : "Run review"}
          </Button>
        </div>
      </div>
    </div>
  );
}
