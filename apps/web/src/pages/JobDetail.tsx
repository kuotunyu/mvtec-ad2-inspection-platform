import { useLocation, useParams } from "react-router-dom";
import { useJob } from "../api/queries";
import { ErrorPanel } from "../components/ErrorPanel";
import { ImageResultGrid } from "../components/ImageResultGrid";
import { JobProgress } from "../components/JobProgress";

export function JobDetail() {
  const { jobId = "" } = useParams();
  const location = useLocation();
  const queuedCount = (location.state as { queuedCount?: number } | null)?.queuedCount;
  const job = useJob(jobId);
  if (job.isLoading) return <div className="page"><p role="status">{queuedCount ? `${queuedCount} 張影像已加入佇列` : "正在載入檢測證據…"}</p></div>;
  if (job.isError || !job.data) return <div className="page"><ErrorPanel message="無法載入這筆檢測作業。" onRetry={() => job.refetch()} /></div>;
  const isTerminal = ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED"].includes(job.data.status);
  return <div className="page">{queuedCount && !isTerminal && <p className="review-message" role="status">{queuedCount} 張影像已加入佇列</p>}<header className="page-header"><div><h1>檢測證據</h1><p className="lede"><span className="mono-label">Job {job.data.id.slice(0, 12)}</span> · {job.data.category.replaceAll("_", " ")} · {job.data.image_count} 張影像 · Revision {job.data.revision}</p></div><div className="report-actions" aria-label="下載報告"><a href={`/api/v1/jobs/${job.data.id}/report.json`}>JSON</a><a href={`/api/v1/jobs/${job.data.id}/report.csv`}>CSV</a><a href={`/api/v1/jobs/${job.data.id}/report.html`}>HTML</a></div></header><JobProgress job={job.data} /><section className="evidence-section"><header className="section-header"><div><h2>影像證據</h2></div><button className="button button--secondary" type="button" onClick={() => job.refetch()}>重新整理</button></header><ImageResultGrid images={job.data.images} /></section></div>;
}
