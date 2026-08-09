import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { App } from "./App";

describe("App", () => {
  it("provides workstation navigation and a skip link", () => {
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Skip to workspace" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Workstation" })).toBeVisible();
    expect(screen.getByRole("link", { name: /new inspection/i })).toHaveAttribute("href", "/inspect");
  });
});
