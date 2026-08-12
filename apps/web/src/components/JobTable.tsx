import { Link } from "react-router-dom";
import type { JobResponse } from "../api/client";
import { StatusBadge } from "./StatusBadge";

export function JobTable({ jobs }: { jobs: readonly JobResponse[] }) {
  return <div className="table-wrap"><table><caption className="sr-only">近期檢測作業</caption><thead><tr><th>工作 ID</th><th>Category</th><th>影像</th><th>狀態</th><th>建立時間</th></tr></thead><tbody>{jobs.map((job) => <tr key={job.id}><td><Link to={`/jobs/${job.id}`} className="job-link">{job.id.slice(0, 10)}</Link></td><td>{job.category.replaceAll("_", " ")}</td><td className="numeric">{job.image_count}</td><td><StatusBadge kind="job" value={job.status === "COMPLETED_WITH_ERRORS" || job.status === "COMPLETED" ? "COMPLETE" : job.status} /></td><td>{job.created_at ? new Date(job.created_at).toLocaleString("zh-TW") : "—"}</td></tr>)}</tbody></table></div>;
}
