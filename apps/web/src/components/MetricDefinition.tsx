export function MetricDefinition({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="metric-definition"><span>{label}</span><strong className="numeric">{value}</strong>{detail && <small>{detail}</small>}</div>;
}
