import { Link } from "react-router-dom";
import { useJobs } from "../api/queries";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { JobTable } from "../components/JobTable";

export function Dashboard() {
  const jobs = useJobs();
  const items = jobs.data?.items ?? [];
  const active = items.filter((job) => job.status === "QUEUED" || job.status === "RUNNING").length;
  const errors = items.reduce((sum, job) => sum + job.error_count, 0);
  return <div className="page"><header className="page-header"><div><span className="eyebrow">Queue and review health</span><h1>Operations overview</h1><p className="lede">Monitor throughput, exceptions, and evidence that still requires a human decision.</p></div><Link className="button" to="/inspect">＋ New inspection</Link></header>
    <section className="stat-grid" aria-label="Operations summary"><article><span>Active queue</span><strong className="numeric">{active.toString().padStart(2, "0")}</strong><small>Queued or processing</small></article><article><span>Model review backlog</span><strong className="numeric">00</strong><small>Not confirmed defects</small></article><article><span>Image errors</span><strong className="numeric">{errors.toString().padStart(2, "0")}</strong><small>{errors === 1 ? "1 image error" : `${errors} image errors`}</small></article><article><span>Champion coverage</span><strong className="numeric">8/8</strong><small>Category-specific models</small></article></section>
    <section className="panel"><header className="section-header"><div><span className="eyebrow">Recent activity</span><h2>{jobs.data ? `${jobs.data.total} recent jobs` : "Inspection jobs"}</h2></div>{jobs.isFetching && <span className="quiet" role="status">Refreshing…</span>}</header>
      {jobs.isError ? <ErrorPanel message="The inspection API did not respond." onRetry={() => jobs.refetch()} /> : jobs.isLoading ? <p role="status">Loading jobs…</p> : items.length ? <JobTable jobs={items} /> : <EmptyState title="No inspections yet">Start a secure batch to populate the evidence queue.</EmptyState>}
    </section></div>;
}
