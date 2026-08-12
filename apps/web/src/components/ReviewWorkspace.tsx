import type { ImageResponse } from "../api/client";
import { HeatmapCompare } from "./HeatmapCompare";
import { ScoreGauge } from "./ScoreGauge";
import { StatusBadge } from "./StatusBadge";
import { DecisionBar, type ReviewDecision } from "./DecisionBar";

export function ReviewWorkspace({ image, note, onNote, onChoose, disabled }: { image: ImageResponse; note: string; onNote: (note: string) => void; onChoose: (decision: ReviewDecision) => void; disabled: boolean }) {
  function shortcut(event: React.KeyboardEvent<HTMLElement>) {
    if (event.target !== event.currentTarget || event.ctrlKey || event.metaKey || event.altKey) return;
    const decision = event.key.toLowerCase() === "a" ? "ACCEPT" : event.key.toLowerCase() === "r" ? "REJECT" : event.key.toLowerCase() === "u" ? "UNCERTAIN" : null;
    if (decision) { event.preventDefault(); onChoose(decision); }
  }
  return <section className="review-workspace" role="region" aria-label="人工覆核工作區" tabIndex={0} onKeyDown={shortcut}><div className="review-evidence"><HeatmapCompare filename={image.filename} sourceUrl={image.source_url} overlayUrl={image.overlay_url ?? image.source_url} /></div><aside className="review-controls"><div className="review-ident"><h2>{image.filename}</h2><p>Item {image.id.slice(0, 12)}</p></div><section className="decision-separation"><div><small>Model outcome</small>{image.model_outcome && <StatusBadge kind="model" value={image.model_outcome} />}</div><div><small>Human decision</small><StatusBadge kind="human" value="UNRESOLVED" /></div></section>{image.anomaly_score != null && image.threshold != null && <ScoreGauge score={image.anomaly_score} threshold={image.threshold} />}<label className="note-field"><span>覆核備註 <small>選填，純文字</small></span><textarea name="review-note" autoComplete="off" value={note} maxLength={2000} onChange={(event) => onNote(event.target.value)} rows={4} placeholder="例如：邊緣出現非預期高回應區…" /><small>{note.length}/2000</small></label><DecisionBar onChoose={onChoose} disabled={disabled} /><p className="shortcut-help">先聚焦此工作區，再按 A、U 或 R；每次都會要求確認。</p></aside></section>;
}
