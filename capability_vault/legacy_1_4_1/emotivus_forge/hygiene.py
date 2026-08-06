from __future__ import annotations

import io
import re
import tokenize
import unicodedata
from pathlib import Path
from typing import Iterable

_MARKER_RE = re.compile(r"^(<<<<<<<|>>>>>>>)(?:[ \t].*)?$")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_SHELL_HOSTILE = set('"\'`|;&<>')


def _python_ignored_lines(text: str) -> set[int]:
    ignored: set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token in tokens:
            if token.type not in {tokenize.STRING, tokenize.COMMENT}:
                continue
            for line_number in range(token.start[0], token.end[0] + 1):
                ignored.add(line_number)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Tokenization can fail on the actual damaged source. Lines already
        # classified as strings/comments remain useful; exact column-zero
        # markers outside those spans are still detected below.
        pass
    return ignored


def _markdown_fenced_lines(text: str) -> set[int]:
    ignored: set[int] = set()
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else ""
        if marker:
            ignored.add(number)
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            ignored.add(number)
    return ignored


def _multiline_ignored_lines(text: str, suffix: str) -> set[int]:
    if suffix == ".py":
        return _python_ignored_lines(text)
    if suffix in {".md", ".markdown"}:
        return _markdown_fenced_lines(text)

    ignored: set[int] = set()
    block_comment = False
    quote: str | None = None
    heredoc_end: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if block_comment or quote or heredoc_end:
            ignored.add(number)
        if heredoc_end:
            if line.strip().rstrip(";") == heredoc_end:
                heredoc_end = None
            continue

        i = 0
        while i < len(line):
            if block_comment:
                end = line.find("*/", i)
                if end < 0:
                    break
                block_comment = False
                i = end + 2
                continue
            if quote:
                char = line[i]
                if char == "\\":
                    i += 2
                    continue
                if char == quote:
                    quote = None
                i += 1
                continue
            if line.startswith("/*", i):
                block_comment = True
                i += 2
                continue
            if line.startswith("//", i) or (suffix in {".php", ".inc", ".phtml", ".sh", ".bash"} and line[i] == "#"):
                break
            if suffix in {".php", ".inc", ".phtml"} and line.startswith("<<<", i):
                match = re.match(r"<<<['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line[i:])
                if match:
                    heredoc_end = match.group(1)
                    i += len(match.group(0))
                    continue
            if line[i] in {"'", '"', "`"}:
                quote = line[i]
            i += 1
    return ignored


def find_merge_markers(text: str, suffix: str = "") -> set[str]:
    """Return {'start', 'end'} for real column-zero conflict-marker lines.

    Marker-shaped examples inside comments, string literals, docstrings,
    heredocs, template literals, or Markdown fences are ignored. Leading
    whitespace is not accepted because Git writes conflict markers at column 0.
    """
    ignored = _multiline_ignored_lines(text, suffix.lower())
    found: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        if number in ignored:
            continue
        match = _MARKER_RE.fullmatch(line.rstrip("\r"))
        if not match:
            continue
        found.add("start" if match.group(1) == "<<<<<<<" else "end")
    return found


def filename_issues(relative: str) -> list[str]:
    issues: list[str] = []
    for component in Path(relative).parts:
        if any(ord(char) < 32 or ord(char) == 127 for char in component):
            issues.append("contains a control character")
        hostile = sorted({char for char in component if char in _SHELL_HOSTILE})
        if hostile:
            issues.append("contains shell-hostile character(s): " + " ".join(repr(char) for char in hostile))
        if component.startswith("-"):
            issues.append("begins with '-' and may be interpreted as a command option")
        if component.endswith(" ") or component.endswith("."):
            issues.append("ends with a space or period")
        stem = component.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED:
            issues.append(f"uses reserved cross-platform name {stem}")
    return list(dict.fromkeys(issues))


def is_allowed_zero_byte(relative: str, allowed: Iterable[str]) -> bool:
    normalized = relative.replace("\\", "/")
    name = Path(normalized).name
    for item in allowed:
        rule = str(item).replace("\\", "/").strip("/")
        if not rule:
            continue
        if normalized == rule or name == rule or (rule.endswith("/") and normalized.startswith(rule)):
            return True
    return False


def portable_path_key(relative: str) -> str:
    """Normalize a path for case-insensitive and Unicode-normalizing filesystems."""
    components = []
    for component in Path(relative.replace("\\", "/")).parts:
        normalized = unicodedata.normalize("NFC", component).rstrip(" .").casefold()
        components.append(normalized)
    return "/".join(components)
