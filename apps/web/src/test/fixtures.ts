export const syntheticImage = {
  id: "synthetic-review-01", filename: "synthetic-gear-01.png",
  source_url: "/synthetic/source.svg", anomaly_map_url: "/synthetic/map.svg",
  overlay_url: "/synthetic/overlay.svg", anomaly_score: 0.8124, threshold: 0.54,
  model_outcome: "REVIEW" as const, human_decision: null, revision: 0, error: null,
};

export const fixtures = {
  queuedJob: { id: "synthetic-job", category: "can" as const, image_count: 1, status: "QUEUED" as const, created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 0 },
  runningJob: { id: "synthetic-job", category: "can" as const, image_count: 1, status: "RUNNING" as const, created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 0 },
  completeJob: { id: "synthetic-job", category: "can" as const, image_count: 1, status: "COMPLETED" as const, created_at: "2026-08-09T01:00:00Z", completed_count: 1, error_count: 0, revision: 2, model_bundle_id: "synthetic-ci-bundle", images: [syntheticImage] },
  partialJob: { id: "synthetic-partial", category: "can" as const, image_count: 2, status: "COMPLETED_WITH_ERRORS" as const, created_at: "2026-08-09T01:00:00Z", completed_count: 1, error_count: 1, revision: 2, model_bundle_id: "synthetic-ci-bundle", images: [syntheticImage, { ...syntheticImage, id: "synthetic-error", filename: "corrupt-input.bin", overlay_url: null, anomaly_map_url: null, anomaly_score: null, threshold: null, model_outcome: null, error: "Image decoder rejected synthetic corrupt input" }] },
  failedJob: { id: "synthetic-failed", category: "can" as const, image_count: 1, status: "FAILED" as const, created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 1 },
  cancelledJob: { id: "synthetic-cancelled", category: "can" as const, image_count: 1, status: "CANCELLED" as const, created_at: "2026-08-09T01:00:00Z", completed_count: 0, error_count: 0 },
  reviewQueue: { items: [syntheticImage], total: 1 },
  resolvedReview: { image_id: syntheticImage.id, decision: "UNCERTAIN" as const, note: "Synthetic demo review", revision: 1, created_at: "2026-08-09T01:05:00Z" },
  models: { items: [{ category: "can" as const, family: "patchcore", artifact_size_bytes: 1136661491, gpu_p95_latency_ms: 105.36, peak_vram_mib: 2146.34, image_auroc: 0.5108, pixel_au_pro: 0.3081, selection_reason: "significant_higher_au_pro" }], champion_matrix_sha256: "813c9822d951a011706f8ecbcd35ea1531474be5a73039053f70270a9d7f05f2" },
  publicOnlyEvidence: { public_gate_sha256: "9cf47070c75bbf66f5e9919c32b5847b886a2f02190ea844c55273bb5ac4f751", dataset_manifest_sha256: "557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf", private_evaluation: "not submitted", official_submission_performed: false, limitations: ["Synthetic CI evidence is not a production validation.", "No defect-type classification or automatic final rejection."], metric_definitions: { image_auroc: "Image AUROC (higher is better)", pixel_au_pro: "Pixel AU-PRO (FPR ≤ 0.30, higher is better)" }, downloadable: { champions: "/evidence/champions.json" } },
  privatePassEvidence: { private_evaluation: "official private gate passed", official_submission_performed: true },
  lightingNoGoEvidence: { private_evaluation: "NO-GO under lighting shift", official_submission_performed: true },
  systemStatus: { backend_status: "ready" as const, worker_status: "current" as const, worker_heartbeat_at: "2026-08-09T01:05:00Z", active_queue: 0, review_backlog: 1, image_errors: 0 },
};
