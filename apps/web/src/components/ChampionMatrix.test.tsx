import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChampionMatrix } from "./ChampionMatrix";

describe("ChampionMatrix", () => {
  it("keeps category scope and metric direction visible", () => {
    render(<ChampionMatrix models={[{ category: "can", family: "patchcore", artifact_size_bytes: 1000, gpu_p95_latency_ms: 105.3, peak_vram_mib: 2146.3, image_auroc: 0.5108, pixel_au_pro: 0.3081, selection_reason: "significant_higher_au_pro" }]} />);
    expect(screen.getByText("Pixel AU-PRO (FPR ≤ 0.30, higher is better)")).toBeVisible();
    expect(screen.getByText("can")).toBeVisible();
    expect(screen.getByText("PatchCore")).toBeVisible();
  });
});
