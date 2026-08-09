import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => vi.restoreAllMocks());

describe("NewInspection", () => {
  it("creates a job once and navigates to its progress", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ id: "job-new", category: "can", image_count: 2, status: "QUEUED", completed_count: 0, error_count: 0 }), { status: 201, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderApp("/inspect");
    await user.selectOptions(screen.getByLabelText("Component category"), "can");
    const files = [new File(["one"], "a.png", { type: "image/png" }), new File(["two"], "b.png", { type: "image/png" })];
    await user.upload(screen.getByLabelText("Inspection files"), files);
    await user.click(screen.getByRole("button", { name: "Start inspection" }));
    expect(await screen.findByText("2 images queued")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
