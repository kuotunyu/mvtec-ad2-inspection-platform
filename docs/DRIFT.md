# 離線 anomaly-score distribution drift

這份文件收錄原本放在 README 的 drift 工具說明。精簡版請見 [README](../README.md)，適用範圍另見 [Limitations](LIMITATIONS.md)。

[`inspection_platform.drift`](../src/inspection_platform/drift) 提供 deterministic PSI 核心；[`experiments.drift`](../experiments/drift) 的 evidence generator 直接載入既有 `PredictionArtifact`，不建立另一條推論管線。它要求 baseline 與 current 具有完全相同的 category 集合、model family、config digest、bundle identity 與 prediction-record contract，任何不一致都會 fail closed。分箱會對 baseline 樣本數封頂、移除重複 quantile edges，並以明確的三桶策略處理 constant baseline。

機器可讀 report 使用 schema version `1.0.0`，按 category 記錄 baseline/current 描述統計、樣本數、histogram、PSI、sample-size adequacy、來源 artifact SHA-256 與 generator version。空桶穩定化規則固定為把每個 share floor 到 `1e-6` 後重新正規化，report 也記錄這個 policy。它不回寫 raw scores、prediction records、input paths 或資料內容。`low`（PSI < 0.1）、`moderate`（0.1 ≤ PSI < 0.25）與 `high`（PSI ≥ 0.25）只是常見 heuristic bands，**不是已校準的 production gate**。

CLI 需要使用者已獲准存取、由既有 pipeline 產生的 canonical prediction artifacts；輸出路徑不可預先存在：

```powershell
uv sync --frozen --extra ml
$baselineArtifacts = @("<standard-category-a.json>", "<standard-category-b.json>")
$currentArtifacts = @("<comparison-category-a.json>", "<comparison-category-b.json>")
$driftReport = Join-Path ([IO.Path]::GetTempPath()) "mvtec-ad2-drift-report.json"
uv run python -m experiments.drift.cli `
  --baseline-artifact $baselineArtifacts `
  --current-artifact $currentArtifacts `
  --baseline-description "approved standard-lighting artifacts" `
  --current-description "approved comparison-lighting artifacts" `
  --output $driftReport
```

目前 source tree 沒有可發布的 standard-vs-lighting per-sample `anomaly_score` distributions；被追蹤的 public artifacts 只有 aggregates 與外部 prediction digests。因此 Repository **沒有**提交 `reports/drift_report.json`，也不宣稱量到真實 lighting drift。`tests/unit/drift/` 只用 synthetic canonical artifacts 驗證 detector、report 與 CLI contract。若未來取得可發布且經授權的 per-sample artifacts，可依上列命令產生證據；這個 handoff 不授權讀取 private predictions、重跑模型、重訓或再次 submission。
