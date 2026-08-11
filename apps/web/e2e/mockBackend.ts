import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";

type Candidate = {
  artifact_size_bytes: number;
  au_pro: number;
  family: string;
  gpu_p95_latency_ms: number;
  image_auroc: number;
  peak_vram_mib: number;
};

type ChampionReport = {
  canonical_sha256: string;
  decisions: Array<{
    candidates: Candidate[];
    category: string;
    decision: { reason: string; winner: string };
  }>;
};

type PublicBenchmark = {
  canonical_sha256: string;
  dataset_manifest_sha256: string;
};

type OfficialResult = {
  status: string;
  verdict: string;
};

export type MockEvidenceProfile = "public-only" | "portfolio";

function readJson<T>(relative: string): T {
  return JSON.parse(readFileSync(new URL(relative, import.meta.url), "utf8")) as T;
}

const champions = readJson<ChampionReport>("../../../reports/champions.json");
const benchmark = readJson<PublicBenchmark>("../../../reports/public_benchmark.json");
const official = readJson<OfficialResult>(
  "../../../docs/assets/evidence/official-private-result.json",
);
const servingEvidence = readFileSync(
  new URL("../../../docs/assets/evidence/serving-benchmark.json", import.meta.url),
);

if (official.status !== "DONE" || official.verdict !== "PRIVATE-NO-GO") {
  throw new Error("committed official evidence is not the expected reviewed no-go result");
}

export const image = {
  id: "synthetic-review-01",
  filename: "synthetic-gear-01.png",
  source_url: "/synthetic/source.svg",
  anomaly_map_url: "/synthetic/map.svg",
  overlay_url: "/synthetic/overlay.svg",
  anomaly_score: 0.8124,
  threshold: 0.54,
  model_outcome: "REVIEW",
  human_decision: null,
  revision: 0,
  error: null,
};

export const job = {
  id: "synthetic-job",
  category: "can",
  image_count: 1,
  status: "COMPLETED",
  created_at: "2026-08-09T01:00:00Z",
  completed_count: 1,
  error_count: 0,
  revision: 2,
  model_bundle_id: "synthetic-ci-bundle",
  images: [image],
};

const publicOnlyEvidence = {
  public_gate_sha256: benchmark.canonical_sha256,
  dataset_manifest_sha256: benchmark.dataset_manifest_sha256,
  private_evaluation: "not submitted",
  official_submission_performed: false,
  serving_benchmark_status: "not evaluated",
  serving_benchmark_sha256: null,
  limitations: [
    "Synthetic CI evidence is not production validation.",
    "No automatic final rejection.",
  ],
  metric_definitions: {
    image_auroc: "Image AUROC (higher is better)",
    pixel_au_pro: "Pixel AU-PRO (FPR ≤ 0.30, higher is better)",
  },
  downloadable: { champions: "/evidence/champions.json" },
};

const portfolioEvidence = {
  public_gate_sha256: benchmark.canonical_sha256,
  dataset_manifest_sha256: benchmark.dataset_manifest_sha256,
  private_evaluation: "NO-GO under lighting shift",
  official_submission_performed: true,
  serving_benchmark_status: "passed",
  serving_benchmark_sha256: createHash("sha256").update(servingEvidence).digest("hex"),
  limitations: [
    "MVTec AD 2 is licensed for non-commercial research use and is not redistributed.",
    "Model outcomes are PASS or REVIEW; a human owns final disposition.",
    "The official frozen private gate is PRIVATE-NO-GO; no retuning or second submission was performed.",
  ],
  metric_definitions: {
    image_auroc: "Image AUROC (higher is better)",
    pixel_au_pro: "Pixel AU-PRO (FPR ≤ 0.30, higher is better)",
  },
  downloadable: {
    champions: "/evidence/champions.json",
    public_benchmark: "/evidence/public-benchmark.json",
    serving_benchmark: "/evidence/serving-benchmark.json",
    official_private_result: "/evidence/official-private-result.json",
  },
};

const models = {
  items: champions.decisions.map((decision) => {
    const winner = decision.candidates.find(
      (candidate) => candidate.family === decision.decision.winner,
    );
    if (!winner) throw new Error(`missing champion candidate for ${decision.category}`);
    return {
      category: decision.category,
      family: winner.family,
      artifact_size_bytes: winner.artifact_size_bytes,
      gpu_p95_latency_ms: winner.gpu_p95_latency_ms,
      peak_vram_mib: winner.peak_vram_mib,
      image_auroc: winner.image_auroc,
      pixel_au_pro: winner.au_pro,
      selection_reason: decision.decision.reason,
    };
  }),
  champion_matrix_sha256: champions.canonical_sha256,
};

export async function mockBackend(
  page: Page,
  evidenceProfile: MockEvidenceProfile = "public-only",
) {
  const evidence = evidenceProfile === "portfolio" ? portfolioEvidence : publicOnlyEvidence;
  await page.route("**/synthetic/*.svg", (route) =>
    route.fulfill({
      contentType: "image/svg+xml",
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420"><rect width="100%" height="100%" fill="#18242b"/><circle cx="320" cy="210" r="120" fill="#5aa8ae"/><path d="M210 210h220" stroke="#f0ad2f" stroke-width="18"/><text x="20" y="395" fill="white">SYNTHETIC DEMO</text></svg>',
    }),
  );
  await page.route("**/api/v1/jobs", async (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(job) })
      : route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ items: [job], total: 1 }),
        }),
  );
  await page.route("**/api/v1/jobs/synthetic-job", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(job) }),
  );
  await page.route("**/api/v1/jobs/synthetic-job/report.json", (route) =>
    route.fulfill({
      contentType: "application/json",
      headers: { "content-disposition": "attachment; filename=synthetic-report.json" },
      body: JSON.stringify({ scope: "synthetic-ci-only" }),
    }),
  );
  await page.route("**/api/v1/reviews", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [image], total: 1 }),
    }),
  );
  await page.route("**/api/v1/reviews/*", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        image_id: image.id,
        decision: "UNCERTAIN",
        note: null,
        revision: 1,
        created_at: "2026-08-09T01:05:00Z",
      }),
    }),
  );
  await page.route("**/api/v1/models", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(models) }),
  );
  await page.route("**/api/v1/evidence", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(evidence) }),
  );
  await page.route("**/api/v1/system/status", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        backend_status: "ready",
        worker_status: "current",
        worker_heartbeat_at: "2026-08-09T01:05:00Z",
        active_queue: 0,
        review_backlog: 1,
        image_errors: 0,
      }),
    }),
  );
}
