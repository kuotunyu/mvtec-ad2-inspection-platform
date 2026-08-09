import { StatusBadge } from "./StatusBadge";
import type { ReviewDecision } from "./DecisionBar";

export interface HistoryEntry { revision: number; decision: ReviewDecision; createdAt: string; }

export function ReviewHistory({ entries }: { entries: HistoryEntry[] }) {
  return <section className="review-history"><header><span className="eyebrow">Audit history</span><h3>Human decisions</h3></header>{entries.length ? <ol>{entries.map((entry) => <li key={entry.revision}><StatusBadge kind="human" value={entry.decision} /><span>Revision {entry.revision}</span><time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString()}</time></li>)}</ol> : <p>No human decision has been recorded for this item.</p>}</section>;
}
