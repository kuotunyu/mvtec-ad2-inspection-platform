import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => vi.restoreAllMocks());

describe("JobDetail", () => {
  it("removes the queued announcement after a job reaches a terminal state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      id: "job-complete", category: "can", image_count: 2, status: "COMPLETED",
      created_at: "2026-08-09T01:00:00Z", completed_count: 2, error_count: 0, revision: 1,
      model_bundle_id: "bundle-123", images: [],
    }), { headers: { "content-type": "application/json" } })));

    renderApp({ pathname: "/jobs/job-complete", state: { queuedCount: 2 } });

    expect(await screen.findByText("檢測已完成")).toBeVisible();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("keeps successful results visible when one image failed", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      id: "job-partial", category: "can", image_count: 2, status: "COMPLETED_WITH_ERRORS",
      created_at: "2026-08-09T01:00:00Z", completed_count: 1, error_count: 1, revision: 3,
      model_bundle_id: "bundle-123", images: [
        { id: "part-01", filename: "part-01.png", source_url: "/source.png", anomaly_map_url: "/map.png", overlay_url: "/overlay.png", anomaly_score: 0.72, threshold: 0.51, model_outcome: "REVIEW", human_decision: null, revision: 0, error: null },
        { id: "part-02", filename: "part-02.png", source_url: "/bad.png", anomaly_map_url: null, overlay_url: null, anomaly_score: null, threshold: null, model_outcome: null, human_decision: null, revision: 0, error: "Could not decode part-02" },
      ],
    }), { headers: { "content-type": "application/json" } })));
    renderApp("/jobs/job-partial");
    expect(await screen.findByText("已完成，1 張影像處理失敗")).toBeVisible();
    expect(screen.getByRole("img", { name: "part-01 的 anomaly overlay" })).toBeVisible();
    expect(screen.getByText("Could not decode part-02")).toBeVisible();
  });
});
