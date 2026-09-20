# 解析度與 memory bank 研究

這份文件收錄原本放在 README 的兩段 PatchCore 後續研究全文。精簡版請見 [README](../README.md)；英文敘述見 [Case study](CASE_STUDY.md)，完整設計見 [Model selection](MODEL_SELECTION.md)。

## 解析度前沿：品質改善卻仍不 promotion

這一段是整個專案我最想被檢視的部分，因為它記錄了一個**預先訂好的門檻否決我自己最好結果**的完整過程。

假設很直觀：提高輸入解析度應該改善細小瑕疵的 localization。第一次嘗試在 24 GiB RTX 4090 上 fitting 階段就 OOM，沒有任何可比較的指標，只留下 `RESOURCE_LIMIT_EXCEEDED`。中間的 640 x 640 frontier probe 改善了 AU-PRO 卻讓 image AUROC 退步、延遲翻倍，分類為 `PROMISING` 但不 promotion。

後來這個 study 在 80 GiB A100 上以**完全相同的程式、seed 與 config** 完成，唯一改變的是硬體。訓練峰值為 **44,593 MiB** <!-- claim:44,593|reports/high_resolution_patchcore_cloud_environment.json|/training_peak_vram_mib/can|,.0f --> 與 **31,741 MiB** <!-- claim:31,741|reports/high_resolution_patchcore_cloud_environment.json|/training_peak_vram_mib/wallplugs|,.0f -->，證實 24 GiB 的機器本來就不可能容納任一個 category。

品質假設成立了，而且是這個專案從單純改變幾何得到的最大增益：

| Category | AU-PRO | pixel AUROC | image AUROC | GPU p95 | 推論 VRAM |
|---|---|---|---|---|---|
| `can` | 0.3113 → 0.4109（**+0.0995** <!-- claim:0.0995|reports/high_resolution_patchcore_cloud.json|/comparisons/0/au_pro_delta|.4f -->） | +0.0545 | −0.0123 | **708.7 ms** <!-- claim:708.7|reports/high_resolution_patchcore_cloud.json|/comparisons/0/candidate/gpu_p95_latency_ms|.1f --> | 4,669 MiB |
| `wallplugs` | 0.5286 → 0.6837（**+0.1551** <!-- claim:0.1551|reports/high_resolution_patchcore_cloud.json|/comparisons/1/au_pro_delta|.4f -->） | +0.0259 | +0.0104 | **508.5 ms** <!-- claim:508.5|reports/high_resolution_patchcore_cloud.json|/comparisons/1/candidate/gpu_p95_latency_ms|.1f --> | 3,383 MiB |

但 verdict 仍然是 `RESOURCE_LIMIT_EXCEEDED`，champion 一個都沒換。原因是 GPU p95 latency 超過了**在看到任何結果之前**就寫死在 `classify_study` 裡的 500 ms serving cap。

這是 latency 的失敗，不是 memory 的失敗。推論 VRAM 遠低於 12,288 MiB 上限，per-image failure rate 為零。而且這個延遲代價是結構性的，不是雲端硬體的假象：memory bank 約大 2.1 倍、每張查詢影像貢獻 2.25 倍的 patch，最近鄰搜尋因此約 4.8 倍的距離計算量，實測比值為 6.7 與 6.2。換回原本的 workstation 結論一樣。

**如果當初沒有把門檻寫死，我很可能會說服自己這是個該採用的改進。** 我選擇照原規則判定而不是放寬門檻，這件事本身比任何指標都更能說明我如何做工程決策。

誠實的限制：這是 single-seed 證據；A100 的 latency 與 VRAM 不可與本 Repository 其他地方記錄的 RTX 4090 數字相比，品質 delta 才與硬體無關；要 promotion 需要另一個預先註冊的 multi-seed study，以及一份 candidate 真的能滿足的 serving contract。完整設計與 sanitized 證據見 [Model selection](MODEL_SELECTION.md)、[study report](../reports/high_resolution_patchcore_cloud.json) 與[硬體 provenance](../reports/high_resolution_patchcore_cloud_environment.json)。

## Memory-bounded PatchCore 研究亮點

在固定的 640 x 640 幾何下降低 memory-bank 比例，先測 coreset 0.01，再依預先訂好的 gate 執行 0.02 rescue。

0.02 seed-42 candidate 的 AU-PRO 相對 baseline 增加 **0.0854** <!-- claim:0.0854|reports/memory_bounded_patchcore.json|/probes/1/comparison/au_pro_delta|.4f -->、GPU p95 為 **78.4 ms** <!-- claim:78.4|reports/memory_bounded_patchcore.json|/probes/1/comparison/candidate/gpu_p95_latency_ms|.1f -->，artifact 為 **330,255,411 bytes** <!-- claim:330,255,411|reports/memory_bounded_patchcore.json|/probes/1/comparison/candidate/artifact_size_bytes|,d -->。但 seeds 17 與 2026 的 image AUROC 都明顯退步，因此最終 verdict 是 `EFFICIENT_SEED42_ONLY`，不更換 frozen champion，也不推論 private performance。完整設計、重現方式與限制見 [Model selection](MODEL_SELECTION.md)、[Experiment runbook](EXPERIMENT_RUNBOOK.md) 與 [sanitized report](../reports/memory_bounded_patchcore.json)。
