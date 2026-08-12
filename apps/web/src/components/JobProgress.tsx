import type { JobDetailResponse } from "../api/client";

export function JobProgress({ job }: { job: JobDetailResponse }) {
  const complete = job.completed_count + job.error_count;
  const percent = job.image_count ? Math.round((complete / job.image_count) * 100) : 0;
  const summary = job.status === "COMPLETED_WITH_ERRORS" ? `已完成，${job.error_count} 張影像處理失敗` : job.status === "COMPLETED" ? "檢測已完成" : job.status === "CANCELLED" ? "檢測已取消" : job.status === "FAILED" ? "檢測失敗" : `已處理 ${complete} / ${job.image_count}`;
  return <section className="progress-panel" aria-live="polite"><header><div><strong>{summary}</strong></div><span className="numeric">{percent}%</span></header><div className="progress-track" role="progressbar" aria-label="影像處理進度" aria-valuemin={0} aria-valuemax={job.image_count} aria-valuenow={complete}><span style={{ width: `${percent}%` }} /></div><footer><span>{job.completed_count} 張成功</span><span>{job.error_count} 張失敗</span><span>{job.image_count - complete} 張待處理</span></footer></section>;
}
