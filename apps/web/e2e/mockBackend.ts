import type { Page } from "@playwright/test";

export const image = { id: "synthetic-review-01", filename: "synthetic-gear-01.png", source_url: "/synthetic/source.svg", anomaly_map_url: "/synthetic/map.svg", overlay_url: "/synthetic/overlay.svg", anomaly_score: 0.8124, threshold: 0.54, model_outcome: "REVIEW", human_decision: null, revision: 0, error: null };
export const job = { id: "synthetic-job", category: "can", image_count: 1, status: "COMPLETED", created_at: "2026-08-09T01:00:00Z", completed_count: 1, error_count: 0, revision: 2, model_bundle_id: "synthetic-ci-bundle", images: [image] };
const evidence = { public_gate_sha256: "9cf47070c75bbf66f5e9919c32b5847b886a2f02190ea844c55273bb5ac4f751", dataset_manifest_sha256: "557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf", private_evaluation: "not submitted", official_submission_performed: false, limitations: ["Synthetic CI evidence is not production validation.", "No automatic final rejection."], metric_definitions: { image_auroc: "Image AUROC (higher is better)", pixel_au_pro: "Pixel AU-PRO (FPR ≤ 0.30, higher is better)" }, downloadable: { champions: "/evidence/champions.json" } };
const models = { items: [{ category: "can", family: "patchcore", artifact_size_bytes: 1000, gpu_p95_latency_ms: 105.3, peak_vram_mib: 2146.3, image_auroc: 0.5108, pixel_au_pro: 0.3081, selection_reason: "significant_higher_au_pro" }], champion_matrix_sha256: "813c9822d951a011706f8ecbcd35ea1531474be5a73039053f70270a9d7f05f2" };

export async function mockBackend(page: Page) {
  await page.route("**/synthetic/*.svg", (route) => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420"><rect width="100%" height="100%" fill="#18242b"/><circle cx="320" cy="210" r="120" fill="#5aa8ae"/><path d="M210 210h220" stroke="#f0ad2f" stroke-width="18"/><text x="20" y="395" fill="white">SYNTHETIC DEMO</text></svg>' }));
  await page.route("**/api/v1/jobs", async (route) => route.request().method() === "POST" ? route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(job) }) : route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [job], total: 1 }) }));
  await page.route("**/api/v1/jobs/synthetic-job", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(job) }));
  await page.route("**/api/v1/jobs/synthetic-job/report.json", (route) => route.fulfill({ contentType: "application/json", headers: { "content-disposition": "attachment; filename=synthetic-report.json" }, body: JSON.stringify({ scope: "synthetic-ci-only" }) }));
  await page.route("**/api/v1/reviews", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ items: [image], total: 1 }) }));
  await page.route("**/api/v1/reviews/*", (route) => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ image_id: image.id, decision: "UNCERTAIN", note: null, revision: 1, created_at: "2026-08-09T01:05:00Z" }) }));
  await page.route("**/api/v1/models", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(models) }));
  await page.route("**/api/v1/evidence", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(evidence) }));
}
