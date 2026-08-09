type ModelStatus = "PASS" | "REVIEW";
type HumanStatus = "ACCEPT" | "REJECT" | "UNCERTAIN" | "UNRESOLVED";
type JobStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";

type Props =
  | { kind: "model"; value: ModelStatus }
  | { kind: "human"; value: HumanStatus }
  | { kind: "job"; value: JobStatus };

const labels: Record<string, string> = {
  "model:PASS": "Model: pass",
  "model:REVIEW": "Model: review required",
  "human:ACCEPT": "Human: accept",
  "human:REJECT": "Human: reject",
  "human:UNCERTAIN": "Human: uncertain",
  "human:UNRESOLVED": "Human: unresolved",
  "job:QUEUED": "Job: queued",
  "job:RUNNING": "Job: running",
  "job:COMPLETE": "Job: complete",
  "job:FAILED": "Job: failed",
  "job:CANCELLED": "Job: cancelled",
};

export function StatusBadge({ kind, value }: Props) {
  const attention = value === "REVIEW" || value === "UNCERTAIN" || value === "UNRESOLVED";
  const danger = value === "REJECT" || value === "FAILED";
  const icon = danger ? "!" : attention ? "◆" : value === "RUNNING" ? "↻" : "✓";
  return (
    <span className={`status status--${danger ? "danger" : attention ? "attention" : "normal"}`}>
      <span aria-hidden="true" data-testid="status-icon">{icon}</span>
      {labels[`${kind}:${value}`]}
    </span>
  );
}
