from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def _symlink_or_skip(link: Path, target: Path) -> None:
    if os.name == "nt" and target.is_dir():
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        pytest.skip(f"directory junctions are unavailable: {result.stderr.strip()}")
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable in this environment: {exc}")


def test_verifier_rejects_link_target_that_resolves_outside_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "repo"
    docs = root / "docs"
    outside = tmp_path / "outside"
    docs.mkdir(parents=True)
    outside.mkdir()
    (outside / "secret.md").write_text("# Secret\n", encoding="utf-8")
    _symlink_or_skip(docs / "external", outside)
    (root / "README.md").write_text(
        "[External](docs/external/secret.md)\n",
        encoding="utf-8",
    )
    original_is_dir = Path.is_dir

    def reject_external_access(path: Path) -> bool:
        resolved = path.resolve()
        if resolved == outside or resolved.is_relative_to(outside):
            raise AssertionError("verifier traversed an external directory")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", reject_external_access)

    assert verify_links(root, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            1,
            "docs/external/secret.md",
            "local target escapes repository root",
        ),
    )


def test_verifier_rejects_source_document_that_resolves_outside_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "source.md").write_text("# Outside\n", encoding="utf-8")
    _symlink_or_skip(root / "linked", outside)

    assert verify_links(root, (Path("linked/source.md"),)) == (
        LinkFinding(
            Path("linked/source.md"),
            1,
            "linked/source.md",
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


def test_verifier_allocates_anchor_suffixes_across_slug_collisions(
    tmp_path: Path,
) -> None:
    (tmp_path / "guide.md").write_text(
        """# Foo
## Foo
## Foo-1
""",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        """[First](guide.md#foo)
[Repeated](guide.md#foo-1)
[Colliding](guide.md#foo-1-1)
[Absent](guide.md#foo-1-2)
""",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            4,
            "guide.md#foo-1-2",
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


def test_cli_requires_default_readme_and_changelog(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    result = _run_verifier(tmp_path)

    assert result.returncode == 1
    assert result.stderr == ""
    assert result.stdout == ("CHANGELOG.md:1: CHANGELOG.md: Markdown document does not exist\n")


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


def test_verifier_masks_blockquoted_fenced_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """# Examples

> ```markdown
> [Quoted fence](missing-quoted.md)
> ```

> [Live link](missing-live.md)
""",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            7,
            "missing-live.md",
            "local target does not exist",
        ),
    )


def test_verifier_checks_indented_link_syntax_conservatively(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "    [Example](missing-indented.md)\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            1,
            "missing-indented.md",
            "local target does not exist",
        ),
    )


def test_verifier_checks_link_syntax_in_unsupported_list_contained_fence(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "- Item\n\n  ~~~\n  [Broken](missing-list-fence.md)\n  ~~~\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            4,
            "missing-list-fence.md",
            "local target does not exist",
        ),
    )


def test_longer_backtick_run_does_not_close_inline_code_partially(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        "`[Broken](missing-after-backtick.md)``\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            1,
            "missing-after-backtick.md",
            "local target does not exist",
        ),
    )


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


def test_verifier_checks_shortcut_references_and_linked_reference_badges(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text(
        """[Guide]
![Logo]
[![Status][badge]][target]

[Guide]: missing-guide.md
[Logo]: missing-logo.svg
[badge]: missing-badge.svg
[target]: missing-target.md
""",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == (
        LinkFinding(
            Path("README.md"),
            1,
            "missing-guide.md",
            "local target does not exist",
        ),
        LinkFinding(
            Path("README.md"),
            2,
            "missing-logo.svg",
            "local target does not exist",
        ),
        LinkFinding(
            Path("README.md"),
            3,
            "missing-badge.svg",
            "local target does not exist",
        ),
        LinkFinding(
            Path("README.md"),
            3,
            "missing-target.md",
            "local target does not exist",
        ),
    )


def test_shortcut_reference_scanner_does_not_recheck_inline_link_labels(
    tmp_path: Path,
) -> None:
    (tmp_path / "present.md").write_text("# Present\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        """[Guide](present.md)

[Guide]: missing.md
""",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == ()


def test_verifier_ignores_any_url_with_an_external_scheme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[Archive](ftp://example.com/releases/demo.zip)\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == ()


def test_verifier_does_not_crash_on_malformed_external_url(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "[Malformed external](https://[broken)\n",
        encoding="utf-8",
    )

    assert verify_links(tmp_path, (Path("README.md"),)) == ()
