import { Link } from "react-router-dom";
import { useJobs, useSystemStatus } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { JobTable } from "../components/JobTable";

export function Dashboard() {
  const jobs = useJobs();
  const system = useSystemStatus();
  const items = jobs.data?.items ?? [];
  const formatCount = (value: number | undefined) => value === undefined ? "—" : value.toString().padStart(2, "0");
  const errors = system.data?.image_errors;
  const errorSummary = errors === undefined ? "狀態無法取得" : errors === 1 ? "1 張影像處理失敗" : `${errors} 張影像處理失敗`;
  const worker = system.data?.worker_status === "current" ? "正常" : system.data?.worker_status === "stale" ? "過期" : "未知";
  return <div className="page"><header className="page-header"><div><h1>檢測作業總覽</h1><p className="lede">集中監看佇列、異常證據與待人工覆核項目。</p></div><Link className="button" to="/inspect">建立檢測</Link></header>
    <section className="stat-grid" aria-label="作業摘要"><article><span>執行中</span><strong className="numeric">{formatCount(system.data?.active_queue)}</strong><small>Queued 或 processing</small></article><article className="stat-grid__review"><span>待人工覆核</span><strong className="numeric">{formatCount(system.data?.review_backlog)}</strong><small>尚未做最終處置</small></article><article className="stat-grid__error"><span>影像錯誤</span><strong className="numeric">{formatCount(errors)}</strong><small>{errorSummary}</small></article><article><span>Champion 覆蓋</span><strong className="numeric">8/8</strong><small>每個 category 已綁定</small></article></section>
    <div className="dashboard-grid"><section className="panel panel--flush"><header className="section-header"><div><h2>{jobs.data ? `${jobs.data.total} 筆近期檢測` : "近期檢測"}</h2></div>{jobs.isFetching && <span className="quiet" role="status">更新中…</span>}</header>
      {jobs.isError ? <ErrorPanel message="Inspection API 沒有回應。" onRetry={() => jobs.refetch()} /> : jobs.isLoading ? <p role="status">正在載入檢測作業…</p> : items.length ? <JobTable jobs={items} /> : <EmptyState title="尚無檢測作業">建立第一批檢測以產生 evidence queue。</EmptyState>}
    </section><aside className="operations-brief"><header><h2>需要注意</h2><span>即時作業訊號</span></header><strong className="operations-brief__count">{formatCount(system.data?.review_backlog)} 項待覆核</strong><p>Model REVIEW 不是瑕疵定論，必須由操作員做最終處置。</p><dl><div><dt>Worker</dt><dd>{worker}</dd></div><div><dt>影像錯誤</dt><dd>{errors ?? "—"}</dd></div><div><dt>Champion</dt><dd>8 / 8</dd></div></dl></aside></div></div>;
}
