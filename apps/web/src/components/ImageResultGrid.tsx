import { useState } from "react";
import type { ImageResponse } from "../api/client";
import { ImageEvidenceDialog } from "./ImageEvidenceDialog";
import { ScoreGauge } from "./ScoreGauge";
import { StatusBadge } from "./StatusBadge";

export function ImageResultGrid({ images }: { images: readonly ImageResponse[] }) {
  const [selected, setSelected] = useState<ImageResponse | null>(null);
  return <><div className="result-grid">{images.map((image) => <article key={image.id} className={`result-card ${image.error ? "result-card--error" : ""}`}>{image.error ? <div className="image-error"><span aria-hidden="true">!</span><strong>Image unavailable</strong><p>{image.error}</p></div> : <><button className="evidence-thumb" type="button" onClick={() => setSelected(image)} aria-label={`Inspect evidence for ${image.filename}`}><img src={image.overlay_url ?? image.source_url} alt={image.overlay_url ? `Anomaly overlay for ${image.filename.replace(/\.[^.]+$/, "")}` : `Source image for ${image.filename}`} /></button><div className="result-body"><header><strong>{image.filename}</strong>{image.model_outcome && <StatusBadge kind="model" value={image.model_outcome} />}</header>{image.anomaly_score != null && image.threshold != null && <ScoreGauge score={image.anomaly_score} threshold={image.threshold} />}{image.human_decision && <StatusBadge kind="human" value={image.human_decision} />}</div></>}</article>)}</div><ImageEvidenceDialog image={selected} onClose={() => setSelected(null)} /></>;
}
