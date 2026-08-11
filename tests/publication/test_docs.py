from __future__ import annotations

import re
from pathlib import Path

PUBLIC_DOCS = (
    Path("README.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/CASE_STUDY.md"),
    Path("docs/MODEL_CARD.md"),
    Path("docs/DATA_CARD.md"),
    Path("docs/SECURITY.md"),
    Path("docs/LIMITATIONS.md"),
    Path("docs/REPRODUCIBILITY.md"),
    Path("docs/EXPERIMENT_RUNBOOK.md"),
    Path("docs/MODEL_SELECTION.md"),
    Path("docs/RELEASE_CHECKLIST.md"),
    Path("docs/REMOTE_SETUP.md"),
)


def test_public_document_set_and_assets_are_complete() -> None:
    assert all(path.is_file() for path in PUBLIC_DOCS)
    for asset in (
        "docs/assets/architecture.svg",
        "docs/assets/workflow.svg",
        "docs/assets/screenshots/dashboard.webp",
        "docs/assets/screenshots/new-inspection.webp",
        "docs/assets/screenshots/job-evidence.webp",
        "docs/assets/screenshots/review.webp",
        "docs/assets/screenshots/model-evidence.webp",
        "docs/assets/manifest.json",
    ):
        assert Path(asset).is_file()
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "synthetic" in readme.lower()
    assert "private-no-go" in readme.lower()


def test_docs_never_call_review_a_defect() -> None:
    forbidden = re.compile(r"(?:detected|confirmed) defect", re.IGNORECASE)
    assert not any(forbidden.search(path.read_text(encoding="utf-8")) for path in PUBLIC_DOCS)


def test_public_readme_is_zh_tw_front_door_and_publication_is_authorized() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    for required in (
        "## 專案重點",
        "## 公開內容與證據邊界",
        "## 產品流程",
        "## Memory-bounded PatchCore 研究亮點",
        "## 官方 private gate",
        "## 已驗證的本機 serving 效能",
        "## 執行 synthetic local demo",
        "EFFICIENT_SEED42_ONLY",
        "PRIVATE-NO-GO",
        "MVTec 原始資料",
    ):
        assert required in readme

    checklist = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    assert "- [x] Publication explicitly authorized." in checklist
    assert "Publication remains outside this authorized result-import task." not in checklist


def test_public_docs_do_not_expose_windows_absolute_paths() -> None:
    windows_absolute_path = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
    for path in PUBLIC_DOCS:
        assert windows_absolute_path.search(path.read_text(encoding="utf-8")) is None, path


def test_example_environment_matches_formal_runbook_and_has_no_stale_switches() -> None:
    example = Path(".env.example").read_text(encoding="utf-8")
    for required in (
        "MVTECAD2_DATA_ROOT",
        "MVTECAD2_DATASET_MANIFEST",
        "MVTECAD2_RUNS_ROOT",
        "MVTECAD2_HIGHRES_RUNS_ROOT",
        "MVTECAD2_FRONTIER_RUNS_ROOT",
        "MVTECAD2_BALANCED_RUNS_ROOT",
        "MVTECAD2_MEMORY_BOUNDED_RUNS_ROOT",
        "MVTECAD2_PREDICTION_CACHE_ROOT",
        "MVTECAD2_SUBMISSION_OUTPUT_ROOT",
        "MVTECAD2_OFFICIAL_UTILS_ROOT",
        "MVTECAD2_GPU_LOCK",
        "INSPECTION_MODEL_ROOT",
    ):
        assert f"{required}=" in example
    for stale in ("MVTECAD2_SUBMISSION_ROOT", "INSPECTION_RUNTIME_ROOT", "INSPECTION_DEMO_MODE"):
        assert f"{stale}=" not in example


def test_gpu_scripts_require_an_explicit_lock_path() -> None:
    for path in (Path("scripts/gpu_product_smoke.py"), Path("scripts/benchmark_serving.py")):
        source = path.read_text(encoding="utf-8")
        assert 'default=Path("D:/.mvtec-ad2-gpu.lock")' not in source
        assert 'parser.add_argument("--gpu-lock", type=Path, required=True)' in source


def test_portfolio_front_door_describes_current_runtime_and_release() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "releases/tag/v0.1.0-rc.1" in readme
    assert "docs/assets/bench/champion-au-pro.svg" in readme
    assert "PNG、JPEG、WebP" in readme
    assert "compose.gpu.yaml" in readme
    architecture = Path("docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    for required in ("anomaly-map", "overlay", "heartbeat", "compose.gpu.yaml"):
        assert required in architecture
    security = Path("docs/SECURITY.md").read_text(encoding="utf-8")
    assert "scheduled" in security.lower()
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    assert "EFFICIENT_SEED42_ONLY" in changelog


def test_documented_release_report_stays_outside_the_worktree() -> None:
    reproducibility = Path("docs/REPRODUCIBILITY.md").read_text(encoding="utf-8")
    assert '"--output", "release-python.json"' not in reproducibility
    assert "GetTempPath" in reproducibility
