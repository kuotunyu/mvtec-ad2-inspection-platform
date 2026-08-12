import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/render";

describe("App", () => {
  it("provides workstation navigation and a truthful status indicator", async () => {
    renderApp("/");
    expect(screen.getByRole("link", { name: "跳至主要工作區" })).toBeVisible();
    const navigation = screen.getByRole("navigation", { name: "檢測工作站" });
    expect(navigation).toBeVisible();
    expect(within(navigation).getByRole("link", { name: "建立檢測" })).toHaveAttribute("href", "/inspect");
    await waitFor(() =>
      expect(document.querySelector(".pulse")).toHaveClass(
        screen.queryByText("Backend 無法連線") ? "pulse--error" : "pulse--current",
      ),
    );
  });
});
