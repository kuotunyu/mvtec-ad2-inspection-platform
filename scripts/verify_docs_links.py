from __future__ import annotations

import argparse
import html
import os
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"(`+).*?\1", re.DOTALL)
_FENCE_RE = re.compile(r"^[ ]{0,3}(?P<fence>`{3,}|~{3,})")
_REFERENCE_DEFINITION_RE = re.compile(
    r"^[ \t]{0,3}\[(?P<label>[^\]\r\n]+)\]:[ \t]*"
    r"(?:<(?P<angle>[^>\r\n]+)>|(?P<plain>\S+))",
    re.MULTILINE,
)
_IMAGE_RE = re.compile(
    r"!\[(?:\\.|[^\]\\])*\]\([ \t]*"
    r"(?:<(?P<angle>[^>\r\n]+)>|"
    r"(?P<plain>(?:\\[^\r\n]|[^()\s\\]|\([^()\r\n]*\))+))"
    r"(?:[ \t]+(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\([^()\r\n]*\)))?[ \t]*\)",
)
_INLINE_LINK_RE = re.compile(
    r"(?<!!)\[(?:\\.|[^\[\]\\]|\[(?:\\.|[^\]\\])*\]\([^\)\r\n]*\))*\]"
    r"\([ \t]*(?:<(?P<angle>[^>\r\n]+)>|"
    r"(?P<plain>(?:\\[^\r\n]|[^()\s\\]|\([^()\r\n]*\))+))"
    r"(?:[ \t]+(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|\([^()\r\n]*\)))?[ \t]*\)",
)
_REFERENCE_LINK_RE = re.compile(
    r"!?\[(?P<label>(?:\\.|[^\]\\])*)\]"
    r"\[(?P<reference>(?:\\.|[^\]\\])*)\]"
)
_ATX_HEADING_RE = re.compile(
    r"^[ ]{0,3}#{1,6}[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$",
    re.MULTILINE,
)
_SETEXT_HEADING_RE = re.compile(
    r"^[ ]{0,3}(?P<text>\S[^\r\n]*)\r?\n[ ]{0,3}(?:=+|-+)[ \t]*$",
    re.MULTILINE,
)


@dataclass(frozen=True, order=True)
class LinkFinding:
    source: Path
    line: int
    target: str
    reason: str


@dataclass(frozen=True, order=True)
class _MarkdownLink:
    line: int
    offset: int
    target: str


def _masked(value: str) -> str:
    return "".join(character if character in "\r\n" else " " for character in value)


def _mask_matches(text: str, matches: Sequence[re.Match[str]]) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in matches:
        pieces.extend((text[cursor : match.start()], _masked(match.group(0))))
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces)


def _mask_fences_and_comments(text: str) -> str:
    without_comments = _HTML_COMMENT_RE.sub(lambda match: _masked(match.group(0)), text)
    output: list[str] = []
    fence_character: str | None = None
    fence_length = 0
    for line in without_comments.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        match = _FENCE_RE.match(content)
        if fence_character is None:
            if match is None:
                output.append(line)
                continue
            fence = match.group("fence")
            fence_character = fence[0]
            fence_length = len(fence)
            output.append(_masked(line))
            continue

        output.append(_masked(line))
        if match is None:
            continue
        fence = match.group("fence")
        trailing = content[match.end() :]
        if fence[0] == fence_character and len(fence) >= fence_length and not trailing.strip():
            fence_character = None
            fence_length = 0
    return "".join(output)


def _normalize_reference(label: str) -> str:
    return " ".join(label.split()).casefold()


def _unescape_markdown(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _markdown_links(text: str) -> tuple[_MarkdownLink, ...]:
    block_text = _mask_fences_and_comments(text)
    scan_text = _INLINE_CODE_RE.sub(lambda match: _masked(match.group(0)), block_text)
    definition_matches = tuple(_REFERENCE_DEFINITION_RE.finditer(scan_text))
    references = {
        _normalize_reference(match.group("label")): _unescape_markdown(
            match.group("angle") or match.group("plain")
        )
        for match in definition_matches
    }
    scan_text = _mask_matches(scan_text, definition_matches)

    links = [
        _MarkdownLink(
            _line_number(text, match.start()),
            match.start(),
            _unescape_markdown(match.group("angle") or match.group("plain")),
        )
        for pattern in (_IMAGE_RE, _INLINE_LINK_RE)
        for match in pattern.finditer(scan_text)
    ]
    for match in _REFERENCE_LINK_RE.finditer(scan_text):
        reference = match.group("reference") or match.group("label")
        target = references.get(_normalize_reference(reference))
        if target is not None:
            links.append(_MarkdownLink(_line_number(text, match.start()), match.start(), target))
    return tuple(sorted(links))


def _local_target(root: Path, source: Path, target_path: str) -> tuple[Path | None, str | None]:
    candidate = Path(os.path.abspath(source.parent / target_path))
    if not candidate.is_relative_to(root):
        return None, "local target escapes repository root"

    relative = candidate.relative_to(root)
    current = root
    for part in relative.parts:
        if not current.is_dir():
            return None, "local target does not exist"
        entries = {entry.name: entry for entry in current.iterdir()}
        if part not in entries:
            if any(name.casefold() == part.casefold() for name in entries):
                return None, "local target casing does not match repository"
            return None, "local target does not exist"
        current = entries[part]
    return current, None


def _plain_heading_text(value: str) -> str:
    without_inline_links = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", value)
    without_reference_links = re.sub(r"!?\[([^\]]*)\]\[[^\]]*\]", r"\1", without_inline_links)
    without_html = re.sub(r"<[^>]+>", "", without_reference_links)
    return _unescape_markdown(without_html.replace("`", ""))


def _github_slug(text: str) -> str:
    lowered = html.unescape(text).strip().lower()
    allowed = "".join(
        character
        for character in lowered
        if character in {"-", "_"}
        or character.isspace()
        or unicodedata.category(character)[0] in {"L", "M", "N"}
    )
    return re.sub(r"\s", "-", allowed)


def _markdown_anchors(path: Path) -> frozenset[str]:
    text = _mask_fences_and_comments(path.read_text(encoding="utf-8"))
    headings = [
        (match.start(), _plain_heading_text(match.group("text")))
        for pattern in (_ATX_HEADING_RE, _SETEXT_HEADING_RE)
        for match in pattern.finditer(text)
    ]
    counts: dict[str, int] = {}
    anchors: set[str] = set()
    for _, heading in sorted(headings):
        base = _github_slug(heading)
        duplicate_index = counts.get(base, 0)
        anchor = base if duplicate_index == 0 else f"{base}-{duplicate_index}"
        counts[base] = duplicate_index + 1
        anchors.add(anchor)
    return frozenset(anchors)


def public_markdown_documents(root: Path) -> tuple[Path, ...]:
    resolved_root = root.resolve()
    documents = [
        relative
        for relative in (Path("README.md"), Path("CHANGELOG.md"))
        if (resolved_root / relative).is_file()
    ]
    docs_root = resolved_root / "docs"
    if docs_root.is_dir():
        documents.extend(
            path.relative_to(resolved_root)
            for path in docs_root.rglob("*.md")
            if "superpowers" not in path.relative_to(resolved_root).parts
        )
    return tuple(sorted(documents))


def verify_links(root: Path, documents: Sequence[Path]) -> tuple[LinkFinding, ...]:
    resolved_root = root.resolve()
    findings: list[LinkFinding] = []
    anchor_cache: dict[Path, frozenset[str]] = {}

    for document in documents:
        source = resolved_root / document
        if not source.is_file():
            findings.append(
                LinkFinding(document, 1, document.as_posix(), "Markdown document does not exist")
            )
            continue
        text = source.read_text(encoding="utf-8")
        for link in _markdown_links(text):
            parsed = urlsplit(link.target)
            if parsed.scheme or link.target.startswith("//"):
                continue
            target_path = unquote(parsed.path)
            candidate, reason = _local_target(
                resolved_root,
                source,
                target_path or source.name,
            )
            if reason is not None:
                findings.append(LinkFinding(document, link.line, link.target, reason))
                continue
            fragment = unquote(parsed.fragment)
            if (
                fragment
                and candidate is not None
                and candidate.suffix.lower() in {".md", ".markdown"}
            ):
                if candidate not in anchor_cache:
                    anchor_cache[candidate] = _markdown_anchors(candidate)
                if fragment not in anchor_cache[candidate]:
                    findings.append(
                        LinkFinding(
                            document,
                            link.line,
                            link.target,
                            "local Markdown anchor does not exist",
                        )
                    )

    return tuple(sorted(findings))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify repository-local links in public Markdown documents."
    )
    parser.add_argument("documents", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    documents = tuple(args.documents) or public_markdown_documents(args.root)
    findings = verify_links(args.root, documents)
    for finding in findings:
        print(f"{finding.source.as_posix()}:{finding.line}: {finding.target}: {finding.reason}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
