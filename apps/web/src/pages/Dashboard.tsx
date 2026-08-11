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
  const errorSummary = errors === undefined ? "Status unavailable" : errors === 1 ? "1 image error" : `${errors} image errors`;
  return <div className="page"><header className="page-header"><div><span className="eyebrow">Queue and review health</span><h1>Operations overview</h1><p className="lede">Monitor throughput, exceptions, and evidence that still requires a human decision.</p></div><Link className="button" to="/inspect">＋ New inspection</Link></header>
    <section className="stat-grid" aria-label="Operations summary"><article><span>Active queue</span><strong className="numeric">{formatCount(system.data?.active_queue)}</strong><small>Queued or processing</small></article><article><span>Model review backlog</span><strong className="numeric">{formatCount(system.data?.review_backlog)}</strong><small>Not confirmed defects</small></article><article><span>Image errors</span><strong className="numeric">{formatCount(errors)}</strong><small>{errorSummary}</small></article><article><span>Champion coverage</span><strong className="numeric">8/8</strong><small>Category-specific models</small></article></section>
    <section className="panel"><header className="section-header"><div><span className="eyebrow">Recent activity</span><h2>{jobs.data ? `${jobs.data.total} recent jobs` : "Inspection jobs"}</h2></div>{jobs.isFetching && <span className="quiet" role="status">Refreshing…</span>}</header>
      {jobs.isError ? <ErrorPanel message="The inspection API did not respond." onRetry={() => jobs.refetch()} /> : jobs.isLoading ? <p role="status">Loading jobs…</p> : items.length ? <JobTable jobs={items} /> : <EmptyState title="No inspections yet">Start a secure batch to populate the evidence queue.</EmptyState>}
    </section></div>;
}
