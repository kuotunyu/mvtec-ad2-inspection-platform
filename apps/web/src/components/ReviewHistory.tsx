import { StatusBadge } from "./StatusBadge";
import type { ReviewDecision } from "./DecisionBar";

export interface HistoryEntry { revision: number; decision: ReviewDecision; createdAt: string; }

export function ReviewHistory({ entries }: { entries: HistoryEntry[] }) {
  return <section className="review-history"><header><h3>Human decision audit</h3></header>{entries.length ? <ol>{entries.map((entry) => <li key={entry.revision}><StatusBadge kind="human" value={entry.decision} /><span>Revision {entry.revision}</span><time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString("zh-TW")}</time></li>)}</ol> : <p>此項目尚未記錄人工處置。</p>}</section>;
}
