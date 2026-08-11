import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "../test/render";

describe("App", () => {
  it("provides workstation navigation and a truthful status indicator", async () => {
    renderApp("/");
    expect(screen.getByRole("link", { name: "Skip to workspace" })).toBeVisible();
    const navigation = screen.getByRole("navigation", { name: "Workstation" });
    expect(navigation).toBeVisible();
    expect(within(navigation).getByRole("link", { name: /new inspection/i })).toHaveAttribute("href", "/inspect");
    await waitFor(() =>
      expect(document.querySelector(".pulse")).toHaveClass(
        screen.queryByText("Backend unavailable") ? "pulse--error" : "pulse--current",
      ),
    );
  });
});
