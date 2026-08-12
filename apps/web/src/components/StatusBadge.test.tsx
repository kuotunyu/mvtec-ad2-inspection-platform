import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("does not communicate review state by color alone", () => {
    render(<StatusBadge kind="model" value="REVIEW" />);
    expect(screen.getByText("Model：需要覆核")).toBeVisible();
    expect(screen.getByTestId("status-icon")).toHaveAttribute("aria-hidden", "true");
  });

  it("keeps model and human terminology separate", () => {
    const { rerender } = render(<StatusBadge kind="model" value="PASS" />);
    expect(screen.getByText("Model：通過")).toBeVisible();
    rerender(<StatusBadge kind="human" value="REJECT" />);
    expect(screen.getByText("Human：拒絕")).toBeVisible();
  });
});
