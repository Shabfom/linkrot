"""Pull links and heading anchors out of Markdown and HTML files."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    target: str
    line: int


_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
# [text](url "title") and ![alt](url). Allows one level of nested brackets in the text.
_INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'(].*?[\"')])?\s*\)")
_REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+.*)?$")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+)>")
_HTML_ATTR = re.compile(r"""<(?:a|img|link|script|source)\b[^>]*?\s(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)
_HTML_ID = re.compile(r"""\s(?:id|name)\s*=\s*["']([^"']+)["']""", re.I)
_ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_SETEXT_UNDERLINE = re.compile(r"^\s{0,3}(=+|-+)\s*$")


def strip_code(lines: list[str]) -> list[str]:
    """Blank out fenced code blocks and inline code, keeping line numbers intact."""
    out = []
    fence = None
    for line in lines:
        m = _FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append("")
            continue
        if m:
            fence = m.group(1)
            out.append("")
            continue
        out.append(_INLINE_CODE.sub("", line))
    return out


def links(text: str, is_html: bool = False) -> list[Link]:
    lines = text.splitlines()
    if not is_html:
        lines = strip_code(lines)
    found = []
    for n, line in enumerate(lines, 1):
        if not is_html:
            for m in _INLINE_LINK.finditer(line):
                found.append(Link(m.group(1), n))
            m = _REF_DEF.match(line)
            if m:
                found.append(Link(m.group(1), n))
            for m in _AUTOLINK.finditer(line):
                found.append(Link(m.group(1), n))
        for m in _HTML_ATTR.finditer(line):
            found.append(Link(html.unescape(m.group(1)), n))
    return found


def slugify(heading: str) -> str:
    """GitHub's anchor rules: lowercase, drop punctuation, spaces become hyphens."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", heading)  # keep link text only
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("`", "").strip().lower()
    kept = []
    for ch in text:
        if ch in " -_" or ch.isalnum() or unicodedata.category(ch).startswith("M"):
            kept.append(ch)
    return "".join(kept).replace(" ", "-")


def anchors(text: str, is_html: bool = False) -> set[str]:
    """Every fragment a link into this file could point at."""
    found = {m.group(1) for m in _HTML_ID.finditer(text)}
    if is_html:
        return found
    seen: dict[str, int] = {}

    def add(heading: str) -> None:
        slug = slugify(heading)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")

    lines = strip_code(text.splitlines())
    for i, line in enumerate(lines):
        m = _ATX_HEADING.match(line)
        if m:
            add(m.group(1))
        elif (
            i + 1 < len(lines)
            and line.strip()
            and _SETEXT_UNDERLINE.match(lines[i + 1])
            and not line.lstrip().startswith(("-", "*", "+", ">"))
        ):
            add(line)
    return found
