import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => vi.restoreAllMocks());

describe("NewInspection", () => {
  it("creates a job once and navigates to its progress", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(JSON.stringify(init?.method === "POST" ? { id: "job-new", category: "can", image_count: 2, status: "QUEUED", completed_count: 0, error_count: 0 } : { id: "job-new", category: "can", image_count: 2, status: "QUEUED", completed_count: 0, error_count: 0, revision: 0, model_bundle_id: null, images: [] }), { status: init?.method === "POST" ? 201 : 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/inspect");
    await user.selectOptions(screen.getByLabelText("Component category"), "can");
    const files = [new File(["one"], "a.png", { type: "image/png" }), new File(["two"], "b.png", { type: "image/png" })];
    await user.upload(screen.getByLabelText("檢測影像檔案"), files);
    await user.click(screen.getByRole("button", { name: "開始檢測" }));
    expect(await screen.findByText("2 張影像已加入佇列")).toBeVisible();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
});
