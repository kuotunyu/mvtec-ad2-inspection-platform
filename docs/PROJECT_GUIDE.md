# 專案導覽

這份文件收錄原本放在 README 前段的導覽表、版本狀態、公開內容範圍，以及產品流程與部署的完整說明。精簡版請見 [README](../README.md)。

## 專案重點

| Signal | What is demonstrated | Start here |
|---|---|---|
| **Reproducible CV research** | 8 category-specific champions <!-- claim:8|reports/champions.json|/champions|len --> selected from 56 formal public runs <!-- claim:56|reports/public_benchmark.json|/runs|len --> across PatchCore, EfficientAD, and Dinomaly, with every published number linked to committed evidence | [Model selection](MODEL_SELECTION.md) · [Benchmark](../reports/benchmark.md) |
| **Production-shaped ML systems** | FastAPI, SQLite, a leased worker, verified model registry, idempotent recovery, and content-addressed evidence publication | [Architecture](ARCHITECTURE.md) · [`tests/system/`](../tests/system) |
| **Human-centered AI product** | React batch inspection, anomaly-map comparison, explicit human disposition, and JSON/CSV/HTML audit exports | [產品流程](#產品流程) · [`apps/web/e2e/`](../apps/web/e2e) |
| **Engineering trust** | CI, Docker, security and release gates, versioned evidence contracts, an explicit `PRIVATE-NO-GO` verdict instead of private-result retuning, and a pre-registered serving gate that refused this project's own largest quality gain | [被自己門檻否決的改進](RESOLUTION_STUDY.md) · [Release checklist](RELEASE_CHECKLIST.md) |

## 依職務方向的閱讀路線

| Role signal | Code path | Evidence path |
|---|---|---|
| **Computer Vision / ML** | [`experiments/`](../experiments) · [`reports/`](../reports) | [Selection methodology](MODEL_SELECTION.md) · [768 x 768 study](RESOLUTION_STUDY.md) |
| **ML systems / MLOps** | [`src/inspection_platform/`](../src/inspection_platform) · [`experiments/drift/`](../experiments/drift) | [Architecture](ARCHITECTURE.md) · [Drift contract](DRIFT.md) |
| **AI product engineering** | [`apps/api/`](../apps/api) · [`apps/web/src/`](../apps/web/src) | [System tests](../tests/system) · [Browser workflow](../apps/web/e2e) |
| **Reliability / security** | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) · [`scripts/`](../scripts) | [Security](SECURITY.md) · [Reproducibility](REPRODUCIBILITY.md) |

## 版本狀態

`v0.1.2` is the latest source-only maintenance release for the stable workstation contract, not a production deployment. It adds the completed 768 x 768 study evidence and the hosted-GPU research tooling. The independent official verdict remains `PRIVATE-NO-GO`; the repository contains no MVTec data, weights, raw private predictions, or private-result retuning. The [`v0.1.2` tag and GitHub Release](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.2) are the authoritative software publication record. No new exact-candidate GPU gate or model-quality claim is attached to this maintenance release; [`v0.1.0`](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.0) remains the last release with recorded 8/8 exact-candidate GPU serving evidence, and [`v0.1.0-rc.1`](https://github.com/kuotunyu/mvtec-ad2-inspection-platform/releases/tag/v0.1.0-rc.1) remains historical.

## 公開內容與證據邊界

| 範圍 | Repository 中的內容 | 可以解讀成什麼 |
|---|---|---|
| Synthetic public demo | 專案自行生成的影像、mock bundles、screenshots 與 CPU/Docker 測試 | 產品流程、恢復能力、安全邊界與 UI 可實際執行；不代表真實模型品質 |
| 使用者自行取得的 MVTec AD 2 | 下載、manifest 與外部路徑操作程式；不含原始影像或 masks | 可在接受官方授權後重現研究；Repository 本身不提供資料 |
| 已完成研究 | Sanitized public aggregates、champion matrix、資源限制與 serving evidence | 可追溯比較、選模、效能與工程取捨 |
| 未公開或未宣稱 | 不含 weights、checkpoints、raw private predictions 或第二次 submission | 不宣稱 production readiness、商用授權或有效的官方 thresholded F1 |

## 產品流程

![從 batch submission 到人工覆核的 synthetic workflow](assets/workflow.svg)

操作人員選擇 category 並送出 batch；job、audit 與 images 在同一 transaction 公開，其中一張影像損壞時，其餘有效影像仍會繼續。獨占 lease 的 worker 在 inference 前驗證指定 model bundle，以獨立 heartbeat 續租，並用 worker、attempt generation、state 與到期時間做 database fence，才把 source、PNG anomaly-map、overlay 與 hashes 分別保存；租約失效後能 idempotent resume。模型證據只記為 `PASS` 或 `REVIEW`，最終處置由人員決定，所有報告分開保留模型判定與人工決策。

本 Repository 的 screenshots 全由 `fixtures/public-demo` 產生，不含 MVTec pixels，也不代表已部署於 production。

## 架構與部署

![由 React、FastAPI、SQLite、worker、artifact store 與 verified registry 組成的 local architecture](assets/architecture.svg)

API startup 不會 import training orchestration。Runtime databases、uploads、artifacts、datasets、checkpoints 與 real model bundles 全部位於 Git 之外。Docker 使用 digest-pinned multi-stage images、read-only root filesystem、unprivileged user、persistent runtime volumes 與 read-only model mount；multipart parser 與 validated-upload staging 共用獨立 disk-backed spool volume，啟動時會檢查其容量。預設 `compose.yaml` 是 CPU synthetic profile；formal NVIDIA worker 使用 `docker compose -f compose.yaml -f compose.gpu.yaml up --build`，且仍需外部 verified registry 與 NVIDIA Container Toolkit。

更完整的元件說明見 [Architecture](ARCHITECTURE.md)。

## 判定語意

`PASS` 表示 frozen model score 低於其記錄 threshold；`REVIEW` 表示證據應由人員檢閱。兩者都不是 defect type、root cause 或 automatic reject decision。
