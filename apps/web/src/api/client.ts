import type { components } from "./generated";

export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type JobResponse = components["schemas"]["JobResponse"];
export type JobDetailResponse = components["schemas"]["JobDetailResponse"];
export type ImageResponse = components["schemas"]["ImageResponse"];
export type JobListResponse = components["schemas"]["JobListResponse"];
export type ReviewQueueResponse = components["schemas"]["ReviewQueueResponse"];
export type ReviewRequest = components["schemas"]["ReviewRequest"];
export type ReviewResponse = components["schemas"]["ReviewResponse"];
export type ModelListResponse = components["schemas"]["ModelListResponse"];
export type ModelSummary = components["schemas"]["ModelSummary"];
export type EvidenceResponse = components["schemas"]["EvidenceResponse"];

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}, retries = 0): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { accept: "application/json", ...init.headers },
    });
  } catch (error) {
    if (retries > 0 && !(init.signal?.aborted)) {
      await new Promise((resolve) => setTimeout(resolve, 100));
      return request<T>(path, init, retries - 1);
    }
    throw error;
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new ApiError("invalid_content_type", "Expected JSON response", "unknown", response.status);
  }
  const payload: unknown = await response.json();
  if (!response.ok) {
    const error = payload as ErrorResponse;
    throw new ApiError(error.code, error.message, error.request_id, response.status);
  }
  return payload as T;
}

export const api = {
  createJob: (category: string, files: File[], signal?: AbortSignal) => {
    const body = new FormData();
    body.set("category", category);
    for (const file of files) body.append("files", file, file.name);
    return request<JobResponse>("/api/v1/jobs", {
      method: "POST",
      body,
      signal,
    });
  },
  listJobs: (signal?: AbortSignal) => request<JobListResponse>("/api/v1/jobs", { signal }, 2),
  getJob: (id: string, signal?: AbortSignal) =>
    request<JobDetailResponse>(`/api/v1/jobs/${encodeURIComponent(id)}`, { signal }, 2),
  cancelJob: (id: string, signal?: AbortSignal) =>
    request<JobResponse>(`/api/v1/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST", signal }),
  listReviews: (signal?: AbortSignal) => request<ReviewQueueResponse>("/api/v1/reviews", { signal }, 2),
  recordReview: (imageId: string, body: ReviewRequest, signal?: AbortSignal) =>
    request<ReviewResponse>(`/api/v1/reviews/${encodeURIComponent(imageId)}`, {
      method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json" }, signal,
    }),
  listModels: (signal?: AbortSignal) => request<ModelListResponse>("/api/v1/models", { signal }, 2),
  getEvidence: (signal?: AbortSignal) => request<EvidenceResponse>("/api/v1/evidence", { signal }, 2),
};
