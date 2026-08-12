export type ReviewDecision = "ACCEPT" | "REJECT" | "UNCERTAIN";

export function DecisionBar({ onChoose, disabled }: { onChoose: (decision: ReviewDecision) => void; disabled: boolean }) {
  return <div className="decision-bar" aria-label="人工處置操作"><button type="button" disabled={disabled} onClick={() => onChoose("ACCEPT")}><span aria-hidden="true">A</span>接受</button><button type="button" disabled={disabled} onClick={() => onChoose("UNCERTAIN")}><span aria-hidden="true">U</span>不確定</button><button type="button" disabled={disabled} className="decision-reject" onClick={() => onChoose("REJECT")}><span aria-hidden="true">R</span>拒絕</button></div>;
}
