export type ReviewDecision = "ACCEPT" | "REJECT" | "UNCERTAIN";

export function DecisionBar({ onChoose, disabled }: { onChoose: (decision: ReviewDecision) => void; disabled: boolean }) {
  return <div className="decision-bar" aria-label="Human decision actions"><button type="button" disabled={disabled} onClick={() => onChoose("ACCEPT")}><span aria-hidden="true">A</span>Accept</button><button type="button" disabled={disabled} onClick={() => onChoose("UNCERTAIN")}><span aria-hidden="true">U</span>Uncertain</button><button type="button" disabled={disabled} className="decision-reject" onClick={() => onChoose("REJECT")}><span aria-hidden="true">R</span>Reject</button></div>;
}
