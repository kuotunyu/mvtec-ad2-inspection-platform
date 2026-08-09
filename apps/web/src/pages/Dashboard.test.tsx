import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => vi.restoreAllMocks());

describe("Dashboard", () => {
  it("separates queue, review, and failure summaries", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      items: [
        { id: "job-queued", category: "can", image_count: 2, status: "QUEUED", created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 0 },
        { id: "job-partial", category: "vial", image_count: 3, status: "COMPLETED_WITH_ERRORS", created_at: "2026-08-09T00:00:00Z", completed_count: 2, error_count: 1 },
      ], total: 2,
    }), { headers: { "content-type": "application/json" } })));
    renderApp("/");
    expect(await screen.findByText("2 recent jobs")).toBeVisible();
    expect(screen.getByText("1 image error")).toBeVisible();
    expect(screen.getByText("Model review backlog")).toBeVisible();
  });
});
