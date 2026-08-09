# MVTec AD 2 Industrial Inspection Platform

![以 synthetic 資料呈現異常證據與人工覆核的工業檢測工作站](docs/assets/screenshots/job-evidence.webp)

這是一套 local-first 工業異常檢測與人工覆核平台，把 frozen benchmark evidence 轉為可續跑的 batch、視覺化檢閱與可稽核的人工作業流程。Repository 只使用 `fixtures/public-demo` 產生公開畫面，不重新散布 MVTec 資料；官方 frozen private gate 的結論為 `PRIVATE-NO-GO`。

## 專案重點

- **可追溯模型選擇：**8 個 category-specific champions <!-- claim:8|reports/champions.json|/champions|len -->，選自 56 次 formal public runs <!-- claim:56|reports/public_benchmark.json|/runs|len -->；每個公開數字都連結 committed machine-readable evidence。
- **完整產品流程：**React 工作站、FastAPI、SQLite、leased worker、model registry、人工覆核與報告匯出。
- **Fail-closed 邊界：**驗證 model identity、uploads、recovery、reports 與 deletion，並以 synthetic fixtures 完成 end-to-end 測試。
- **誠實揭露：**官方結果不支持 v1 release，因此維持 `PRIVATE-NO-GO`，不以 private 結果 retune 或重新提交。

## 產品流程

![從 batch submission 到人工覆核的 synthetic workflow](docs/assets/workflow.svg)

操作人員選擇 category 並送出 batch；其中一張影像損壞時，其餘有效影像仍會繼續。獨占 lease 的 worker 在 inference 前驗證指定 model bundle，將模型證據記為 `PASS` 或 `REVIEW`，並能在 lease 過期後 idempotent resume。最終處置由人員決定，所有報告分開保留模型判定與人工決策。

本 Repository 的 screenshots 全由 `fixtures/public-demo` 產生，不含 MVTec pixels，也不代表已部署於 production。

## 證據，而非 leaderboard 宣稱

- Frozen champion matrix 位於 [reports/champions.json](reports/champions.json)，可讀摘要位於 [reports/benchmark.md](reports/benchmark.md)。
- Public selection 依 approved metric contract 同時考量 image AUROC、pixel AU-PRO、confidence intervals、latency、VRAM 與 artifact size。
- `can`、`vial`、`wallplugs`、`walnuts` 的 winner 是 PatchCore；`fabric`、`fruit_jelly`、`rice`、`sheet_metal` 的 winner 是 Dinomaly。
- EfficientAD 是已 benchmark 的 candidate，但未被選為 champion。
- 唯一一次獲授權的 frozen archive 通過官方 local validator 並由官方 server 評測；看到結果後沒有重建或重新提交。

## 官方 private gate

官方 server 回傳的 AucPro_0.05 average：`private` 為 **31.24** <!-- claim:31.24|docs/assets/evidence/official-private-result.json|/metrics/private/auc_pro_0_05/average|.2f -->，`private_mixed` 為 **29.81** <!-- claim:29.81|docs/assets/evidence/official-private-result.json|/metrics/private_mixed/auc_pro_0_05/average|.2f -->。依預先承諾的規則，material mixed-lighting failure 必須揭露而不能事後調整，因此分類為 `PRIVATE-NO-GO`。

提交的 archive 包含全部 4,090 張 TIFF anomaly maps，但沒有 optional thresholded PNGs。官方 ClassF1 與 SegF1 因此為零，不能解讀成 thresholded-map performance 的有效量測。經審查的 per-category aggregates 與 evidence hashes 位於 [official-private-result.json](docs/assets/evidence/official-private-result.json)；raw server evidence 保留在 Git 之外。

## 已驗證的本機 serving 效能

8 個 frozen champions 都在記錄的 RTX 4090 workstation 上通過 clean-process product inference。每個 category 使用 batch size **1** <!-- claim:1|docs/assets/evidence/serving-benchmark.json|/configuration/batch_size|d -->、**3** 次 warmups <!-- claim:3|docs/assets/evidence/serving-benchmark.json|/configuration/warmup_repetitions|d --> 與 **20** 次 timed GPU repetitions <!-- claim:20|docs/assets/evidence/serving-benchmark.json|/configuration/gpu_repetitions|d -->。以下是本機量測，不是 production guarantee。

| Category | Model family | GPU p50（ms） | GPU p95（ms） | Peak reserved VRAM（MiB） | Bundle bytes |
|---|---|---:|---:|---:|---:|
| can | PatchCore | 155.2 <!-- claim:155.2|docs/assets/evidence/serving-benchmark.json|/categories/can/gpu/p50_latency_ms|.1f --> | 173.2 <!-- claim:173.2|docs/assets/evidence/serving-benchmark.json|/categories/can/gpu/p95_latency_ms|.1f --> | 4388.0 <!-- claim:4388.0|docs/assets/evidence/serving-benchmark.json|/categories/can/gpu/peak_reserved_vram_mib|.1f --> | 3,409,718,327 <!-- claim:3,409,718,327|docs/assets/evidence/serving-benchmark.json|/categories/can/artifact_size_bytes|,d --> |
| fabric | Dinomaly | 167.4 <!-- claim:167.4|docs/assets/evidence/serving-benchmark.json|/categories/fabric/gpu/p50_latency_ms|.1f --> | 184.9 <!-- claim:184.9|docs/assets/evidence/serving-benchmark.json|/categories/fabric/gpu/p95_latency_ms|.1f --> | 2408.0 <!-- claim:2408.0|docs/assets/evidence/serving-benchmark.json|/categories/fabric/gpu/peak_reserved_vram_mib|.1f --> | 1,776,166,311 <!-- claim:1,776,166,311|docs/assets/evidence/serving-benchmark.json|/categories/fabric/artifact_size_bytes|,d --> |
| fruit jelly | Dinomaly | 66.9 <!-- claim:66.9|docs/assets/evidence/serving-benchmark.json|/categories/fruit_jelly/gpu/p50_latency_ms|.1f --> | 72.1 <!-- claim:72.1|docs/assets/evidence/serving-benchmark.json|/categories/fruit_jelly/gpu/p95_latency_ms|.1f --> | 2388.0 <!-- claim:2388.0|docs/assets/evidence/serving-benchmark.json|/categories/fruit_jelly/gpu/peak_reserved_vram_mib|.1f --> | 1,776,166,311 <!-- claim:1,776,166,311|docs/assets/evidence/serving-benchmark.json|/categories/fruit_jelly/artifact_size_bytes|,d --> |
| rice | Dinomaly | 170.4 <!-- claim:170.4|docs/assets/evidence/serving-benchmark.json|/categories/rice/gpu/p50_latency_ms|.1f --> | 177.2 <!-- claim:177.2|docs/assets/evidence/serving-benchmark.json|/categories/rice/gpu/p95_latency_ms|.1f --> | 2408.0 <!-- claim:2408.0|docs/assets/evidence/serving-benchmark.json|/categories/rice/gpu/peak_reserved_vram_mib|.1f --> | 1,776,166,311 <!-- claim:1,776,166,311|docs/assets/evidence/serving-benchmark.json|/categories/rice/artifact_size_bytes|,d --> |
| sheet metal | Dinomaly | 63.2 <!-- claim:63.2|docs/assets/evidence/serving-benchmark.json|/categories/sheet_metal/gpu/p50_latency_ms|.1f --> | 65.8 <!-- claim:65.8|docs/assets/evidence/serving-benchmark.json|/categories/sheet_metal/gpu/p95_latency_ms|.1f --> | 2402.0 <!-- claim:2402.0|docs/assets/evidence/serving-benchmark.json|/categories/sheet_metal/gpu/peak_reserved_vram_mib|.1f --> | 1,776,166,311 <!-- claim:1,776,166,311|docs/assets/evidence/serving-benchmark.json|/categories/sheet_metal/artifact_size_bytes|,d --> |
| vial | PatchCore | 101.3 <!-- claim:101.3|docs/assets/evidence/serving-benchmark.json|/categories/vial/gpu/p50_latency_ms|.1f --> | 111.9 <!-- claim:111.9|docs/assets/evidence/serving-benchmark.json|/categories/vial/gpu/p95_latency_ms|.1f --> | 3232.0 <!-- claim:3232.0|docs/assets/evidence/serving-benchmark.json|/categories/vial/gpu/peak_reserved_vram_mib|.1f --> | 2,496,191,543 <!-- claim:2,496,191,543|docs/assets/evidence/serving-benchmark.json|/categories/vial/artifact_size_bytes|,d --> |
| wallplugs | PatchCore | 134.9 <!-- claim:134.9|docs/assets/evidence/serving-benchmark.json|/categories/wallplugs/gpu/p50_latency_ms|.1f --> | 144.1 <!-- claim:144.1|docs/assets/evidence/serving-benchmark.json|/categories/wallplugs/gpu/p95_latency_ms|.1f --> | 3274.0 <!-- claim:3274.0|docs/assets/evidence/serving-benchmark.json|/categories/wallplugs/gpu/peak_reserved_vram_mib|.1f --> | 2,511,287,351 <!-- claim:2,511,287,351|docs/assets/evidence/serving-benchmark.json|/categories/wallplugs/artifact_size_bytes|,d --> |
| walnuts | PatchCore | 239.7 <!-- claim:239.7|docs/assets/evidence/serving-benchmark.json|/categories/walnuts/gpu/p50_latency_ms|.1f --> | 259.8 <!-- claim:259.8|docs/assets/evidence/serving-benchmark.json|/categories/walnuts/gpu/p95_latency_ms|.1f --> | 4610.0 <!-- claim:4610.0|docs/assets/evidence/serving-benchmark.json|/categories/walnuts/gpu/peak_reserved_vram_mib|.1f --> | 3,560,713,271 <!-- claim:3,560,713,271|docs/assets/evidence/serving-benchmark.json|/categories/walnuts/artifact_size_bytes|,d --> |

完整 sanitized artifact 另記錄 cold start、mean confidence intervals、throughput、CPU fallback、RSS、software versions、bundle identities 與 evidence hash manifest。

## 架構

![由 React、FastAPI、SQLite、worker、artifact store 與 verified registry 組成的 local architecture](docs/assets/architecture.svg)

API startup 不會 import training orchestration。Runtime databases、uploads、artifacts、datasets、checkpoints 與 real model bundles 全部位於 Git 之外。Docker 使用 digest-pinned multi-stage images、read-only root filesystem、unprivileged user、persistent runtime volumes 與 read-only model mount。

詳細資料請見 [Architecture](docs/ARCHITECTURE.md)、[Case study](docs/CASE_STUDY.md)、[Model card](docs/MODEL_CARD.md)、[Data card](docs/DATA_CARD.md)、[Security](docs/SECURITY.md) 與 [Limitations](docs/LIMITATIONS.md)。

## 執行 synthetic local demo

需要 Python、`uv`、Node/npm、Docker Desktop，以及已安裝供 Playwright 使用的 Chromium browser。

```powershell
uv sync --extra ml --frozen
Push-Location apps/web
npm ci
npx playwright install chromium
Pop-Location

$env:INSPECTION_MODEL_ROOT = "D:\mvtec-ad2-demo-models"
uv run python scripts/build_demo_bundle.py --output $env:INSPECTION_MODEL_ROOT
docker compose up -d --build --wait
```

開啟 `http://127.0.0.1:8000`。以 `docker compose down` 停止服務；只有在確定要刪除該 Compose project 的 demo database 與 artifacts 時才加上 `--volumes`。

完整驗證與 real-model preparation 請依 [Reproducibility](docs/REPRODUCIBILITY.md) 和 [Remote setup](docs/REMOTE_SETUP.md) 操作。文件中的命令不會自行 push、publish、upload 或 submit。

## 判定語意

`PASS` 表示 frozen model score 低於其記錄 threshold；`REVIEW` 表示證據應由人員檢閱。兩者都不是 defect type、root cause 或 automatic reject decision。

## License 與資料邊界

Project source code 依 [MIT License](LICENSE) 提供。本 Repository 不重新散布 MVTec 原始資料；MVTec AD 2 data 另依 CC BY-NC-SA 4.0 授權。由該資料訓練的 model artifacts 僅視為 research／non-commercial portfolio artifacts，重用前請閱讀 [MODEL_CARD.md](docs/MODEL_CARD.md)。
