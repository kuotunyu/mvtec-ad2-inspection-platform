import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Dashboard", () => {
  it("separates queue, review, and failure summaries", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const payload = path.includes("/api/v1/system/status")
        ? { backend_status: "ready", worker_status: "stale", worker_heartbeat_at: "2026-08-09T00:00:00Z", active_queue: 1, review_backlog: 3, image_errors: 1 }
        : {
            items: [
              { id: "job-queued", category: "can", image_count: 2, status: "QUEUED", created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 0 },
              { id: "job-partial", category: "vial", image_count: 3, status: "COMPLETED_WITH_ERRORS", created_at: "2026-08-09T00:00:00Z", completed_count: 2, error_count: 1 },
            ], total: 2,
          };
      return new Response(JSON.stringify(payload), { headers: { "content-type": "application/json" } });
    }));
    renderApp("/");
    expect(await screen.findByText("2 筆近期檢測")).toBeVisible();
    expect(screen.getByText("1 張影像處理失敗")).toBeVisible();
    const summary = screen.getByRole("region", { name: "作業摘要" });
    expect(within(summary).getByText("待人工覆核")).toBeVisible();
    expect(await within(summary).findByText("03")).toBeVisible();
    expect(await screen.findByText("Worker heartbeat：過期")).toBeVisible();
  });

  it("does not present partial recent-job counts as authoritative system health", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes("/api/v1/system/status")) {
        return new Response(JSON.stringify({ code: "unavailable" }), { status: 503, headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({
        items: [
          { id: "job-queued", category: "can", image_count: 2, status: "QUEUED", created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 1 },
        ],
        total: 1,
      }), { headers: { "content-type": "application/json" } });
    }));

    renderApp("/");
    expect(await screen.findByText("1 筆近期檢測")).toBeVisible();
    const summary = screen.getByRole("region", { name: "作業摘要" });
    expect(within(summary).getAllByText("—")).toHaveLength(3);
    expect(within(summary).getByText("狀態無法取得")).toBeVisible();
  });
});
