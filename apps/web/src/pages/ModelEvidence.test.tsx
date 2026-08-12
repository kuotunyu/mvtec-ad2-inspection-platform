import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test/render";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ModelEvidence", () => {
  it("presents an official NO-GO as a blocked private gate", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes("models") ? { items: [{ category: "can", family: "patchcore", artifact_size_bytes: 1000, gpu_p95_latency_ms: 105.3, peak_vram_mib: 2146.3, image_auroc: 0.5108, pixel_au_pro: 0.3081, selection_reason: "significant_higher_au_pro" }], champion_matrix_sha256: "abc123" } : { public_gate_sha256: "public123", dataset_manifest_sha256: "data123", private_evaluation: "NO-GO under lighting shift", official_submission_performed: true, limitations: ["No automatic final rejection."], metric_definitions: { image_auroc: "Image AUROC (higher is better)", pixel_au_pro: "Pixel AU-PRO (FPR ≤ 0.30, higher is better)" }, downloadable: { champions: "/champions.json" } }), { headers: { "content-type": "application/json" } })));

    renderApp("/evidence");

    expect(await screen.findByText("PRIVATE-NO-GO")).toBeVisible();
    expect(screen.getByRole("status")).toHaveAttribute("data-verdict", "no-go");
  });

  it("labels an unevaluated private gate instead of inferring success", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(String(input).includes("models") ? { items: [{ category: "can", family: "patchcore", artifact_size_bytes: 1000, gpu_p95_latency_ms: 105.3, peak_vram_mib: 2146.3, image_auroc: 0.5108, pixel_au_pro: 0.3081, selection_reason: "significant_higher_au_pro" }], champion_matrix_sha256: "abc123" } : { public_gate_sha256: "public123", dataset_manifest_sha256: "data123", private_evaluation: "not submitted", official_submission_performed: false, limitations: ["No automatic final rejection."], metric_definitions: { image_auroc: "Image AUROC (higher is better)", pixel_au_pro: "Pixel AU-PRO (FPR ≤ 0.30, higher is better)" }, downloadable: { champions: "/champions.json" } }), { headers: { "content-type": "application/json" } })));
    renderApp("/evidence");
    expect(await screen.findByText("Private evaluation：not submitted")).toBeVisible();
    expect(screen.queryByText(/production.ready/i)).not.toBeInTheDocument();
    expect(screen.getByText("No automatic final rejection.")).toBeVisible();
  });
});
