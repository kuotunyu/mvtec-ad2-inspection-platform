import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HeatmapCompare } from "./HeatmapCompare";

describe("HeatmapCompare", () => {
  it("supports a keyboard-controlled reveal without changing evidence semantics", () => {
    render(<HeatmapCompare filename="sample" sourceUrl="/source.png" overlayUrl="/overlay.png" />);
    const slider = screen.getByRole("slider", { name: "Overlay reveal" });
    expect(slider).toHaveValue("50");
    fireEvent.keyDown(slider, { key: "ArrowRight" });
    expect(slider).toHaveValue("55");
    expect(screen.getByText("Visualization only — not defect classification")).toBeVisible();
  });
});
