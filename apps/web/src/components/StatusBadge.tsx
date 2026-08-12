type ModelStatus = "PASS" | "REVIEW";
type HumanStatus = "ACCEPT" | "REJECT" | "UNCERTAIN" | "UNRESOLVED";
type JobStatus = "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "CANCELLED";

type Props =
  | { kind: "model"; value: ModelStatus }
  | { kind: "human"; value: HumanStatus }
  | { kind: "job"; value: JobStatus };

const labels: Record<string, string> = {
  "model:PASS": "Model：通過",
  "model:REVIEW": "Model：需要覆核",
  "human:ACCEPT": "Human：接受",
  "human:REJECT": "Human：拒絕",
  "human:UNCERTAIN": "Human：不確定",
  "human:UNRESOLVED": "Human：待處置",
  "job:QUEUED": "Job：佇列中",
  "job:RUNNING": "Job：執行中",
  "job:COMPLETE": "Job：已完成",
  "job:FAILED": "Job：失敗",
  "job:CANCELLED": "Job：已取消",
};

export function StatusBadge({ kind, value }: Props) {
  const attention = value === "REVIEW" || value === "UNCERTAIN" || value === "UNRESOLVED";
  const danger = value === "REJECT" || value === "FAILED";
  return (
    <span className={`status status--${danger ? "danger" : attention ? "attention" : "normal"}`}>
      <span className="status-marker" aria-hidden="true" data-testid="status-icon" />
      {labels[`${kind}:${value}`]}
    </span>
  );
}
