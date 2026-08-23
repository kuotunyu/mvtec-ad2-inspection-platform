import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function response(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function runtimeStatus(maxArchiveFiles: number, maxUploadBytes: number) {
  return {
    backend_status: "ready",
    worker_status: "current",
    worker_heartbeat_at: "2026-08-09T01:05:00Z",
    active_queue: 0,
    review_backlog: 0,
    image_errors: 0,
    ingestion_limits: {
      max_archive_files: maxArchiveFiles,
      max_upload_bytes: maxUploadBytes,
    },
  };
}

describe("NewInspection", () => {
  it("creates a job once and navigates to its progress", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("/api/v1/system/status")) return response(runtimeStatus(2, 3));
      if (init?.method === "POST") return response({ id: "job-new", category: "can", image_count: 2, status: "QUEUED", completed_count: 0, error_count: 0 }, 201);
      return response({ id: "job-new", category: "can", image_count: 2, status: "QUEUED", completed_count: 0, error_count: 0, revision: 0, model_bundle_id: null, images: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/inspect");
    expect(await screen.findByText("PNG、JPEG 或 WebP · 單檔上限 3 B")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Component category"), "can");
    const files = [new File(["one"], "a.png", { type: "image/png" }), new File(["two"], "b.png", { type: "image/png" })];
    await user.upload(screen.getByLabelText("檢測影像檔案"), files);
    await user.click(screen.getByRole("button", { name: "開始檢測" }));
    expect(await screen.findByText("2 張影像已加入佇列")).toBeVisible();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("uses the backend runtime file-count limit", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response(runtimeStatus(2, 10))));
    const user = userEvent.setup();
    renderApp("/inspect");
    expect(await screen.findByText("PNG、JPEG 或 WebP · 單檔上限 10 B")).toBeVisible();

    await user.upload(screen.getByLabelText("檢測影像檔案"), [
      new File(["a"], "a.png", { type: "image/png" }),
      new File(["b"], "b.png", { type: "image/png" }),
      new File(["c"], "c.png", { type: "image/png" }),
    ]);

    expect(screen.getByRole("alert")).toHaveTextContent("每個檔案不得超過 10 B，單批最多 2 張影像。");
    expect(screen.getByRole("button", { name: "開始檢測" })).toBeDisabled();
  });

  it("uses the backend runtime per-file byte limit", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response(runtimeStatus(2, 3))));
    const user = userEvent.setup();
    renderApp("/inspect");
    expect(await screen.findByText("PNG、JPEG 或 WebP · 單檔上限 3 B")).toBeVisible();

    await user.upload(
      screen.getByLabelText("檢測影像檔案"),
      new File(["four"], "too-large.png", { type: "image/png" }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent("每個檔案不得超過 3 B，單批最多 2 張影像。");
    expect(screen.getByRole("button", { name: "開始檢測" })).toBeDisabled();
  });

  it("fails closed when runtime ingestion limits are unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/api/v1/system/status")) {
        return response({ code: "service_unavailable", message: "Unavailable", request_id: "test" }, 503);
      }
      return response({});
    }));
    const user = userEvent.setup();
    renderApp("/inspect");

    await user.upload(
      screen.getByLabelText("檢測影像檔案"),
      new File(["one"], "a.png", { type: "image/png" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("無法取得 Backend 上傳限制；請重試連線後再建立檢測。");
    expect(screen.getByRole("button", { name: "開始檢測" })).toBeDisabled();
  });
});
