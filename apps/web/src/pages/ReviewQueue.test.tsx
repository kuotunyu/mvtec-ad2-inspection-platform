import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

const item = { id: "image-1", filename: "part-01.png", source_url: "/source.png", anomaly_map_url: "/map.png", overlay_url: "/overlay.png", anomaly_score: 0.82, threshold: 0.54, model_outcome: "REVIEW", human_decision: null, revision: 0, error: null };
afterEach(() => vi.restoreAllMocks());

describe("ReviewQueue", () => {
  it("does not submit a keyboard decision before confirmation", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init: RequestInit = {}) => { requests.push(init); return new Response(JSON.stringify({ items: [item], total: 1 }), { headers: { "content-type": "application/json" } }); }));
    const user = userEvent.setup();
    renderApp("/review");
    const workspace = await screen.findByRole("region", { name: "Review workspace" });
    workspace.focus();
    await user.keyboard("r");
    expect(screen.getByRole("dialog", { name: "Confirm human rejection" })).toBeVisible();
    expect(requests.filter((request) => request.method === "POST")).toHaveLength(0);
  });

  it("retains the item and explains a revision conflict", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init: RequestInit = {}) => init.method === "POST" ? new Response(JSON.stringify({ code: "review_revision_conflict", message: "This item was reviewed elsewhere", request_id: "req-1" }), { status: 409, headers: { "content-type": "application/json" } }) : new Response(JSON.stringify({ items: [item], total: 1 }), { headers: { "content-type": "application/json" } })));
    const user = userEvent.setup();
    renderApp("/review");
    await user.click(await screen.findByRole("button", { name: "Uncertain" }));
    await user.click(screen.getByRole("button", { name: "Confirm uncertain" }));
    expect(await screen.findByText("This item was reviewed elsewhere")).toBeVisible();
  });
});
