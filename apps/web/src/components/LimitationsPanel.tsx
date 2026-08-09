export function LimitationsPanel({ limitations }: { limitations: readonly string[] }) {
  return <aside className="limitations-panel"><span className="eyebrow">Read before use</span><h2>Limitations</h2><ul>{limitations.map((limitation) => <li key={limitation}><span aria-hidden="true">—</span>{limitation}</li>)}</ul></aside>;
}
