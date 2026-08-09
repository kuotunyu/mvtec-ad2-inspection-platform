import { Link } from "react-router-dom";
import type { JobResponse } from "../api/client";
import { StatusBadge } from "./StatusBadge";

export function JobTable({ jobs }: { jobs: readonly JobResponse[] }) {
  return <div className="table-wrap"><table><caption className="sr-only">Recent inspection jobs</caption><thead><tr><th>Batch</th><th>Category</th><th>Images</th><th>State</th><th>Created</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><Link to={`/jobs/${job.id}`} className="job-link">{job.id.slice(0, 10)}</Link></td><td>{job.category.replaceAll("_", " ")}</td><td className="numeric">{job.image_count}</td><td><StatusBadge kind="job" value={job.status === "COMPLETED_WITH_ERRORS" || job.status === "COMPLETED" ? "COMPLETE" : job.status} /></td><td>{job.created_at ? new Date(job.created_at).toLocaleString() : "—"}</td></tr>)}</tbody></table></div>;
}
