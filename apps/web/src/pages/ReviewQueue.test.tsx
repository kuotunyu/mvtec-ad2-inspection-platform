import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

const item = { id: "image-1", filename: "part-01.png", source_url: "/source.png", anomaly_map_url: "/map.png", overlay_url: "/overlay.png", anomaly_score: 0.82, threshold: 0.54, model_outcome: "REVIEW", human_decision: null, revision: 0, error: null };
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("ReviewQueue", () => {
  it("does not submit a keyboard decision before confirmation", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init: RequestInit = {}) => { requests.push(init); return new Response(JSON.stringify({ items: [item], total: 1 }), { headers: { "content-type": "application/json" } }); }));
    const user = userEvent.setup();
    renderApp("/review");
    const workspace = await screen.findByRole("region", { name: "人工覆核工作區" });
    workspace.focus();
    await user.keyboard("r");
    expect(screen.getByRole("dialog", { name: "確認人工拒絕" })).toBeVisible();
    expect(requests.filter((request) => request.method === "POST")).toHaveLength(0);
  });

  it("retains the item and explains a revision conflict", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_input: RequestInfo | URL, init: RequestInit = {}) => init.method === "POST" ? new Response(JSON.stringify({ code: "review_revision_conflict", message: "This item was reviewed elsewhere", request_id: "req-1" }), { status: 409, headers: { "content-type": "application/json" } }) : new Response(JSON.stringify({ items: [item], total: 1 }), { headers: { "content-type": "application/json" } })));
    const user = userEvent.setup();
    renderApp("/review");
    await user.click(await screen.findByRole("button", { name: "不確定" }));
    await user.click(screen.getByRole("button", { name: "確認不確定" }));
    expect(await screen.findByText("此項目已由其他操作員完成覆核")).toBeVisible();
  });

  it("traps focus, supports Escape, and restores the decision trigger", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [item], total: 1 }), { headers: { "content-type": "application/json" } })));
    const user = userEvent.setup();
    renderApp("/review");
    const reject = await screen.findByRole("button", { name: "拒絕" });
    await user.click(reject);
    const cancel = screen.getByRole("button", { name: "取消" });
    const confirm = screen.getByRole("button", { name: "確認拒絕" });
    expect(cancel).toHaveFocus();
    await user.tab({ shift: true });
    expect(confirm).toHaveFocus();
    await user.tab();
    expect(cancel).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(reject).toHaveFocus();
  });
});
