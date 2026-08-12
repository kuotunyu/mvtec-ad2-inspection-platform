import { ChampionMatrix } from "../components/ChampionMatrix";
import { ErrorPanel } from "../components/ErrorPanel";
import { LimitationsPanel } from "../components/LimitationsPanel";
import { MetricDefinition } from "../components/MetricDefinition";
import { ProvenancePanel } from "../components/ProvenancePanel";
import { useEvidence, useModels } from "../api/queries";

export function ModelEvidence() {
  const models = useModels();
  const evidence = useEvidence();
  if (models.isError || evidence.isError) return <div className="page"><ErrorPanel message="無法載入已驗證的 model evidence。" onRetry={() => { models.refetch(); evidence.refetch(); }} /></div>;
  if (!models.data || !evidence.data) return <div className="page"><p role="status">正在載入 model provenance…</p></div>;
  const privateNoGo = evidence.data.official_submission_performed && /NO-GO/i.test(evidence.data.private_evaluation);
  const verdict = privateNoGo ? "no-go" : evidence.data.official_submission_performed ? "complete" : "pending";
  return <div className="page"><header className="page-header"><div><h1>Model 與證據</h1><p className="lede">每個 category 的 frozen Champion 都來自可追溯的 public evidence；benchmark 分數不等於生產環境保證。</p></div><div className={`private-gate private-gate--${verdict}`} role="status" data-verdict={verdict}><span className="private-gate-label">{privateNoGo ? "PRIVATE-NO-GO" : evidence.data.official_submission_performed ? "COMPLETE" : "未提交"}</span><strong>Private evaluation：{evidence.data.private_evaluation}</strong></div></header><section className="evidence-metrics" aria-label="Metric contract"><MetricDefinition label="Champion categories" value={`${models.data.items.length}/8`} detail="每個 category 一個 frozen selection" /><MetricDefinition label="Official private submission" value={privateNoGo ? "NO-GO" : evidence.data.official_submission_performed ? "已完成" : "未進行"} detail="絕不從本機驗證推論" /><MetricDefinition label="Decision semantics" value="PASS / REVIEW" detail="Human disposition 與 Model 分離" /></section><section className="panel"><ChampionMatrix models={models.data.items} /></section><div className="evidence-bottom"><ProvenancePanel publicHash={evidence.data.public_gate_sha256} datasetHash={evidence.data.dataset_manifest_sha256} championHash={models.data.champion_matrix_sha256} downloads={evidence.data.downloadable} /><LimitationsPanel limitations={evidence.data.limitations} /></div></div>;
}
