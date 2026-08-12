export function ScoreGauge({ score, threshold }: { score: number; threshold: number }) {
  const maximum = Math.max(1, score, threshold);
  return <div className="score-gauge" aria-label={`Anomaly score ${score.toFixed(4)}；threshold ${threshold.toFixed(4)}`}><div><span style={{ left: `${Math.min(100, (threshold / maximum) * 100)}%` }} className="threshold-marker" /><span style={{ width: `${Math.min(100, (score / maximum) * 100)}%` }} className="score-fill" /></div><footer><span>Score <strong className="numeric">{score.toFixed(4)}</strong></span><span>Threshold <strong className="numeric">{threshold.toFixed(4)}</strong></span></footer></div>;
}
