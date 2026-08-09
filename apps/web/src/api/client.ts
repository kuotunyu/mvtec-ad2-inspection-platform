import type { components } from "./generated";

export type CreateJobRequest = components["schemas"]["CreateJobRequest"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type JobResponse = components["schemas"]["JobResponse"];

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
  createJob: (body: CreateJobRequest, signal?: AbortSignal) =>
    request<JobResponse>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "content-type": "application/json" },
      signal,
    }),
  getJob: (id: string, signal?: AbortSignal) =>
    request<JobResponse>(`/api/jobs/${encodeURIComponent(id)}`, { signal }, 2),
};
