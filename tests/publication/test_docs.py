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
        "## 產品流程",
        "## 官方 private gate",
        "## 已驗證的本機 serving 效能",
        "## 執行 synthetic local demo",
        "PRIVATE-NO-GO",
        "MVTec 原始資料",
    ):
        assert required in readme

    checklist = Path("docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    assert "- [x] Publication explicitly authorized." in checklist
    assert "Publication remains outside this authorized result-import task." not in checklist
