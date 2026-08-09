import type { ModelSummary } from "../api/client";

function familyName(value: string) { return value.toLowerCase() === "patchcore" ? "PatchCore" : value.toLowerCase() === "dinomaly" ? "Dinomaly" : value; }

export function ChampionMatrix({ models }: { models: readonly ModelSummary[] }) {
  return <div className="table-wrap champion-table"><table><caption><span>Category champion matrix</span><small>Selection is category-specific; there is no claimed global winner.</small></caption><thead><tr><th>Category</th><th>Champion</th><th>Image AUROC (higher is better)</th><th>Pixel AU-PRO (FPR ≤ 0.30, higher is better)</th><th>GPU p95</th><th>Peak VRAM</th></tr></thead><tbody>{models.map((model) => <tr key={model.category}><td><strong>{model.category.replaceAll("_", " ")}</strong></td><td>{familyName(model.family)}</td><td className="numeric">{model.image_auroc.toFixed(4)}</td><td className="numeric">{model.pixel_au_pro.toFixed(4)}</td><td className="numeric">{model.gpu_p95_latency_ms.toFixed(1)} ms</td><td className="numeric">{model.peak_vram_mib.toFixed(0)} MiB</td></tr>)}</tbody></table></div>;
}
