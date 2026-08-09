import { useEffect, useRef } from "react";
import type { ImageResponse } from "../api/client";
import { HeatmapCompare } from "./HeatmapCompare";
import { ScoreGauge } from "./ScoreGauge";
import { StatusBadge } from "./StatusBadge";

export function ImageEvidenceDialog({ image, onClose }: { image: ImageResponse | null; onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (image) close.current?.focus(); }, [image]);
  if (!image) return null;
  return <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="evidence-dialog" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}><header><div><span className="eyebrow">Per-image evidence</span><h2 id="evidence-title">{image.filename}</h2></div><button ref={close} type="button" aria-label="Close evidence" onClick={onClose}>×</button></header>{image.overlay_url ? <HeatmapCompare filename={image.filename} sourceUrl={image.source_url} overlayUrl={image.overlay_url} /> : <img className="evidence-source" src={image.source_url} alt={`Source image for ${image.filename}`} />}{image.anomaly_score != null && image.threshold != null && <ScoreGauge score={image.anomaly_score} threshold={image.threshold} />}<footer>{image.model_outcome && <StatusBadge kind="model" value={image.model_outcome} />}<a className="button button--secondary" href="/review">Open review queue</a></footer></section></div>;
}
