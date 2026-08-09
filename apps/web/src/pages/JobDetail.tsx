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
  if (job.isLoading) return <div className="page"><p role="status">{queuedCount ? `${queuedCount} images queued` : "Loading inspection evidence…"}</p></div>;
  if (job.isError || !job.data) return <div className="page"><ErrorPanel message="This inspection could not be loaded." onRetry={() => job.refetch()} /></div>;
  return <div className="page"><header className="page-header"><div><span className="eyebrow">Job {job.data.id.slice(0, 12)}</span><h1>Inspection evidence</h1><p className="lede">{job.data.category.replaceAll("_", " ")} · {job.data.image_count} images · revision {job.data.revision}</p></div><div className="report-actions" aria-label="Report downloads"><a href={`/api/v1/jobs/${job.data.id}/report.json`}>JSON</a><a href={`/api/v1/jobs/${job.data.id}/report.csv`}>CSV</a><a href={`/api/v1/jobs/${job.data.id}/report.html`}>HTML</a></div></header><JobProgress job={job.data} /><section className="evidence-section"><header className="section-header"><div><span className="eyebrow">Per-image records</span><h2>Evidence gallery</h2></div><button className="button button--secondary" type="button" onClick={() => job.refetch()}>Refresh</button></header><ImageResultGrid images={job.data.images} /></section></div>;
}
