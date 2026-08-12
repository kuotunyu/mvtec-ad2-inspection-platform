import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DecisionBar } from "./DecisionBar";

describe("DecisionBar", () => {
  it("asks for visible confirmation before a decision mutation", async () => {
    const user = userEvent.setup();
    const onChoose = vi.fn();
    render(<DecisionBar onChoose={onChoose} disabled={false} />);
    await user.click(screen.getByRole("button", { name: "拒絕" }));
    expect(onChoose).toHaveBeenCalledWith("REJECT");
  });
});
