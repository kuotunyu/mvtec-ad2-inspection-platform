import { useState } from "react";
import type { ImageResponse } from "../api/client";
import { ImageEvidenceDialog } from "./ImageEvidenceDialog";
import { ScoreGauge } from "./ScoreGauge";
import { StatusBadge } from "./StatusBadge";

export function ImageResultGrid({ images }: { images: readonly ImageResponse[] }) {
  const [selected, setSelected] = useState<ImageResponse | null>(null);
  return <><div className="result-grid">{images.map((image) => <article key={image.id} className={`result-card ${image.error ? "result-card--error" : ""}`}>{image.error ? <div className="image-error"><span aria-hidden="true" /><strong>影像無法使用</strong><p>{image.error}</p></div> : <><button className="evidence-thumb" type="button" onClick={() => setSelected(image)} aria-label={`查看 ${image.filename} 的檢測證據`}><img src={image.overlay_url ?? image.source_url} width={1200} height={900} loading="lazy" alt={image.overlay_url ? `${image.filename.replace(/\.[^.]+$/, "")} 的 anomaly overlay` : `${image.filename} 的原始影像`} /></button><div className="result-body"><header><strong>{image.filename}</strong>{image.model_outcome && <StatusBadge kind="model" value={image.model_outcome} />}</header>{image.anomaly_score != null && image.threshold != null && <ScoreGauge score={image.anomaly_score} threshold={image.threshold} />}{image.human_decision && <StatusBadge kind="human" value={image.human_decision} />}</div></>}</article>)}</div><ImageEvidenceDialog image={selected} onClose={() => setSelected(null)} /></>;
}
