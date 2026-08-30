from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.verify_docs_links import LinkFinding, verify_links

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIER = REPO_ROOT / "scripts" / "verify_docs_links.py"


def _run_verifier(root: Path, *documents: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), "--root", str(root), *documents],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_reports_only_missing_local_links(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "preview.png").write_bytes(b"synthetic-image")
    (tmp_path / "README.md").write_text(
        """# Demo

[Inline](docs/guide.md)
[Reference][guide]
![Preview](docs/preview.png)
[Broken](docs/missing.md)
[External](https://example.com/not-checked)

[guide]: docs/guide.md
""",
        encoding="utf-8",
    )

    result = _run_verifier(tmp_path, "README.md")

    assert result.returncode == 1
    assert result.stderr == ""
    assert result.stdout == "README.md:6: docs/missing.md: local target does not exist\n"


def test_verifier_enforces_exact_case_and_repository_boundary(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "My Guide.md").write_text("# Guide\n", encoding="utf-8")
    (root / "docs" / "Guide.md").write_text("# Other\n", encoding="utf-8")
    (tmp_path / "outside.md").write_text("# Outside\n", encoding="utf-8")
    (root / "README.md").write_text(
        """# Links
[Encoded](docs/My%20Guide.md)
[Wrong case](docs/guide.md)
[Outside](../outside.md)
""",
        encoding="utf-8",
    )

    findings = verify_links(root, (Path("README.md"),))

    assert findings == (
        LinkFinding(
            Path("README.md"),
            3,
            "docs/guide.md",
            "local target casing does not match repository",
        ),
        LinkFinding(
            Path("README.md"),
            4,
            "../outside.md",
            "local target escapes repository root",
        ),
    )


def test_verifier_checks_unicode_and_duplicate_markdown_anchors(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        """# 產品流程
## Repeat
## Repeat
""",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        """# Overview
[Current](#overview)
[Unicode](docs/guide.md#%E7%94%A2%E5%93%81%E6%B5%81%E7%A8%8B)
[First duplicate](docs/guide.md#repeat)
[Second duplicate](docs/guide.md#repeat-1)
[Missing current](#missing)
[Missing cross-file](docs/guide.md#absent)
""",
        encoding="utf-8",
    )

    findings = verify_links(tmp_path, (Path("README.md"),))

    assert findings == (
        LinkFinding(
            Path("README.md"),
            6,
            "#missing",
            "local Markdown anchor does not exist",
        ),
        LinkFinding(
            Path("README.md"),
            7,
            "docs/guide.md#absent",
            "local Markdown anchor does not exist",
        ),
    )


def test_cli_discovers_public_docs_but_ignores_internal_plans(tmp_path: Path) -> None:
    (tmp_path / "docs" / "superpowers").mkdir(parents=True)
    (tmp_path / "README.md").write_text("[Guide](docs/guide.md)\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "docs" / "superpowers" / "internal.md").write_text(
        "[Ignored](missing.md)\n",
        encoding="utf-8",
    )

    result = _run_verifier(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""


def test_public_repository_docs_have_no_broken_local_links() -> None:
    result = _run_verifier(REPO_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""


def test_cli_reports_a_missing_explicit_document_without_a_traceback(tmp_path: Path) -> None:
    result = _run_verifier(tmp_path, "missing.md")

    assert result.returncode == 1
    assert result.stderr == ""
    assert result.stdout == "missing.md:1: missing.md: Markdown document does not exist\n"


def test_verifier_ignores_link_syntax_inside_code_and_comments(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """# Examples

`[Inline code](missing-inline.md)`

```markdown
[Fenced code](missing-fenced.md)
```

<!-- [Comment](missing-comment.md) -->
""",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == ()


def test_verifier_checks_outer_target_of_a_linked_badge(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[![License](missing-badge.svg)](LICENSE)\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            1,
            "LICENSE",
            "local target does not exist",
        ),
        LinkFinding(
            Path("README.md"),
            1,
            "missing-badge.svg",
            "local target does not exist",
        ),
    )


def test_verifier_ignores_any_url_with_an_external_scheme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[Archive](ftp://example.com/releases/demo.zip)\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == ()
