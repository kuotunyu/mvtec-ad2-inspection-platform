export function LimitationsPanel({ limitations }: { limitations: readonly string[] }) {
  return <aside className="limitations-panel"><h2>使用限制</h2><p>以下為 committed evidence 原文，請在使用前閱讀。</p><ul>{limitations.map((limitation) => <li key={limitation}><span className="limitation-marker" aria-hidden="true" />{limitation}</li>)}</ul></aside>;
}
