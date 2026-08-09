import { ChampionMatrix } from "../components/ChampionMatrix";
import { ErrorPanel } from "../components/ErrorPanel";
import { LimitationsPanel } from "../components/LimitationsPanel";
import { MetricDefinition } from "../components/MetricDefinition";
import { ProvenancePanel } from "../components/ProvenancePanel";
import { useEvidence, useModels } from "../api/queries";

export function ModelEvidence() {
  const models = useModels();
  const evidence = useEvidence();
  if (models.isError || evidence.isError) return <div className="page"><ErrorPanel message="Verified model evidence could not be loaded." onRetry={() => { models.refetch(); evidence.refetch(); }} /></div>;
  if (!models.data || !evidence.data) return <div className="page"><p role="status">Loading model provenance…</p></div>;
  return <div className="page"><header className="page-header"><div><span className="eyebrow">Provenance and limitations</span><h1>Model & evidence</h1><p className="lede">Frozen category champions selected from public evidence. Scores are benchmark measurements, not production guarantees.</p></div><div className={`private-gate ${evidence.data.official_submission_performed ? "private-gate--complete" : ""}`}><span aria-hidden="true">{evidence.data.official_submission_performed ? "✓" : "○"}</span><strong>Private evaluation: {evidence.data.private_evaluation}</strong></div></header><section className="evidence-metrics" aria-label="Metric contract"><MetricDefinition label="Champion categories" value={`${models.data.items.length}/8`} detail="One frozen selection per category" /><MetricDefinition label="Official private submission" value={evidence.data.official_submission_performed ? "complete" : "not performed"} detail="Never inferred from local validation" /><MetricDefinition label="Decision semantics" value="PASS / REVIEW" detail="Human disposition remains separate" /></section><section className="panel"><ChampionMatrix models={models.data.items} /></section><div className="evidence-bottom"><ProvenancePanel publicHash={evidence.data.public_gate_sha256} datasetHash={evidence.data.dataset_manifest_sha256} championHash={models.data.champion_matrix_sha256} downloads={evidence.data.downloadable} /><LimitationsPanel limitations={evidence.data.limitations} /></div></div>;
}
