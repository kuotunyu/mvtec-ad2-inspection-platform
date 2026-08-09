import { useState } from "react";

export function HeatmapCompare({ filename, sourceUrl, overlayUrl }: { filename: string; sourceUrl: string; overlayUrl: string }) {
  const [reveal, setReveal] = useState(50);
  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowRight" || event.key === "ArrowUp") { event.preventDefault(); setReveal((value) => Math.min(100, value + 5)); }
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") { event.preventDefault(); setReveal((value) => Math.max(0, value - 5)); }
  }
  return <figure className="heatmap-compare"><div className="compare-canvas"><img src={sourceUrl} alt={`Source image for ${filename}`} /><div className="overlay-reveal" style={{ width: `${reveal}%` }}><img src={overlayUrl} alt={`Anomaly overlay for ${filename}`} /></div><span className="reveal-line" style={{ left: `${reveal}%` }} /></div><figcaption><label htmlFor={`reveal-${filename}`}>Overlay reveal</label><input id={`reveal-${filename}`} aria-label="Overlay reveal" type="range" min="0" max="100" value={reveal} onChange={(event) => setReveal(Number(event.target.value))} onKeyDown={onKeyDown} /><small>Visualization only — not defect classification</small></figcaption></figure>;
}
