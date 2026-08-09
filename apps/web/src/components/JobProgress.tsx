import type { JobDetailResponse } from "../api/client";

export function JobProgress({ job }: { job: JobDetailResponse }) {
  const complete = job.completed_count + job.error_count;
  const percent = job.image_count ? Math.round((complete / job.image_count) * 100) : 0;
  const summary = job.status === "COMPLETED_WITH_ERRORS" ? `Completed with ${job.error_count} image error${job.error_count === 1 ? "" : "s"}` : job.status === "COMPLETED" ? "Inspection completed" : job.status === "CANCELLED" ? "Inspection cancelled" : job.status === "FAILED" ? "Inspection failed" : `${complete} of ${job.image_count} processed`;
  return <section className="progress-panel" aria-live="polite"><header><div><span className="eyebrow">Batch progress</span><strong>{summary}</strong></div><span className="numeric">{percent}%</span></header><div className="progress-track" role="progressbar" aria-label="Images processed" aria-valuemin={0} aria-valuemax={job.image_count} aria-valuenow={complete}><span style={{ width: `${percent}%` }} /></div><footer><span>{job.completed_count} successful</span><span>{job.error_count} errors</span><span>{job.image_count - complete} remaining</span></footer></section>;
}
