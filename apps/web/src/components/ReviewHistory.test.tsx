import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReviewHistory } from "./ReviewHistory";

describe("ReviewHistory", () => {
  it("labels entries as human decisions", () => {
    render(<ReviewHistory entries={[{ revision: 2, decision: "UNCERTAIN", createdAt: "2026-08-09T01:00:00Z" }]} />);
    expect(screen.getByText("Human：不確定")).toBeVisible();
    expect(screen.getByText("Revision 2")).toBeVisible();
  });
});
