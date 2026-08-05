#!/usr/bin/env python3
"""
Dependency-free PHP structural preflight checker.

This is NOT a replacement for `php -l`. It detects a narrow set of structural
problems that are particularly likely after automated text replacements:

  - unterminated block comments
  - unterminated single-, double-, and backtick-quoted strings
  - unterminated heredoc and nowdoc blocks
  - mismatched or unclosed braces, parentheses, and brackets

Only content inside recognized PHP tags is checked. PHP short tags are ignored
unless --short-tags is supplied.

Usage:
    python3 tools/php_structural_check.py <root-or-file>
    python3 tools/php_structural_check.py . --exclude tests/fixtures/build-tools

Exit codes:
    0 = no structural problems found
    1 = one or more files flagged
    2 = invalid invocation or input path
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable


HEREDOC_OPEN_RE = re.compile(
    r"<<<(?P<quote>['\"]?)"
    r"(?P<label>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?P=quote)[ \t]*\r?\n"
)

OPEN_TO_CLOSE = {"(": ")", "{": "}", "[": "]"}
CLOSE_TO_OPEN = {")": "(", "}": "{", "]": "["}

DEFAULT_EXCLUDES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    "node_modules",
}


def normalize_excludes(raw: Iterable[str]) -> set[str]:
    excludes = set(DEFAULT_EXCLUDES)
    for item in raw:
        cleaned = item.strip().replace("\\", "/").strip("/")
        if cleaned:
            excludes.add(cleaned)
    return excludes


def should_exclude(relative: Path, excluded: set[str]) -> bool:
    posix = relative.as_posix()
    parts = relative.parts

    for rule in excluded:
        if "/" in rule:
            if posix == rule or posix.startswith(rule + "/"):
                return True
        elif rule in parts:
            return True
    return False


def php_open_tag_length(
    source: str,
    position: int,
    allow_short_tags: bool,
) -> int:
    if source.startswith("<?=", position):
        return 3

    if source[position : position + 5].lower() == "<?php":
        after = position + 5
        if after == len(source) or source[after].isspace():
            return 5

    if allow_short_tags:
        if source[position : position + 5].lower() != "<?xml":
            return 2

    return 0


def check_file(path: Path, allow_short_tags: bool = False) -> list[str]:
    try:
        source = path.read_text(
            encoding="utf-8",
            errors="surrogateescape",
        )
    except OSError as exc:
        return [f"READ ERROR: {exc}"]

    i = 0
    line = 1
    length = len(source)
    in_php = False
    lexical_failure = False

    problems: list[str] = []
    stack: list[tuple[str, int]] = []

    def advance(count: int = 1) -> None:
        nonlocal i, line
        end = min(i + count, length)
        line += source.count("\n", i, end)
        i = end

    while i < length:
        if not in_php:
            next_tag = source.find("<?", i)
            if next_tag == -1:
                break

            advance(next_tag - i)
            tag_length = php_open_tag_length(
                source,
                i,
                allow_short_tags,
            )

            if tag_length:
                advance(tag_length)
                in_php = True
            else:
                advance(2)
            continue

        if source.startswith("?>", i):
            advance(2)
            in_php = False
            continue

        char = source[i]
        two = source[i : i + 2]
        is_hash_comment = char == "#" and two != "#["

        if two == "//" or is_hash_comment:
            newline_position = source.find("\n", i + 1)
            close_tag_position = source.find("?>", i + 1)

            close_tag_ends_comment = (
                close_tag_position != -1
                and (
                    newline_position == -1
                    or close_tag_position < newline_position
                )
            )

            if close_tag_ends_comment:
                advance(close_tag_position + 2 - i)
                in_php = False
            elif newline_position == -1:
                advance(length - i)
            else:
                advance(newline_position + 1 - i)
            continue

        if two == "/*":
            opening_line = line
            end_position = source.find("*/", i + 2)

            if end_position == -1:
                problems.append(
                    "UNTERMINATED /* */ block comment "
                    f"starting at line {opening_line}"
                )
                lexical_failure = True
                break

            advance(end_position + 2 - i)
            continue

        heredoc_match = HEREDOC_OPEN_RE.match(source, i)
        if heredoc_match:
            opening_line = line
            label = heredoc_match.group("label")
            advance(heredoc_match.end() - i)

            end_re = re.compile(
                rf"^[ \t]*{re.escape(label)}"
                rf"(?=[^A-Za-z0-9_]|$)",
                re.MULTILINE,
            )
            end_match = end_re.search(source, i)

            if end_match is None:
                problems.append(
                    "UNTERMINATED heredoc/nowdoc "
                    f"<<<{label} starting at line {opening_line}"
                )
                lexical_failure = True
                break

            advance(end_match.end() - i)
            continue

        if char in {"'", '"', "`"}:
            quote = char
            opening_line = line
            advance()
            closed = False

            while i < length:
                if source[i] == "\\":
                    advance(2 if i + 1 < length else 1)
                    continue

                if source[i] == quote:
                    advance()
                    closed = True
                    break

                advance()

            if not closed:
                display_name = {
                    "'": "single-quoted",
                    '"': "double-quoted",
                    "`": "backtick",
                }[quote]
                problems.append(
                    f"UNTERMINATED {display_name} string "
                    f"starting at line {opening_line}"
                )
                lexical_failure = True
                break
            continue

        if char in OPEN_TO_CLOSE:
            stack.append((char, line))

        elif char in CLOSE_TO_OPEN:
            expected_open = CLOSE_TO_OPEN[char]

            if not stack:
                problems.append(
                    f"UNEXPECTED closing '{char}' at line {line}"
                )

            elif stack[-1][0] != expected_open:
                actual_open, actual_line = stack[-1]
                expected_close = OPEN_TO_CLOSE[actual_open]
                problems.append(
                    f"MISMATCHED '{char}' at line {line}; "
                    f"expected '{expected_close}' to close "
                    f"'{actual_open}' opened at line {actual_line}"
                )

            else:
                stack.pop()

        advance()

    if not lexical_failure:
        for opening_char, opening_line in reversed(stack):
            expected_close = OPEN_TO_CLOSE[opening_char]
            problems.append(
                f"UNCLOSED '{opening_char}' opened at line "
                f"{opening_line}; expected '{expected_close}'"
            )

    return problems


def collect_files(
    root: Path,
    extensions: set[str],
    excluded: set[str],
) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in extensions else []

    files: list[Path] = []

    for directory, directory_names, file_names in os.walk(root):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(root)

        kept_directories: list[str] = []
        for name in directory_names:
            candidate = relative_directory / name
            if not should_exclude(candidate, excluded):
                kept_directories.append(name)
        directory_names[:] = kept_directories

        for file_name in file_names:
            candidate = directory_path / file_name
            relative = candidate.relative_to(root)
            if (
                candidate.suffix.lower() in extensions
                and not should_exclude(relative, excluded)
            ):
                files.append(candidate)

    return sorted(files)


def parse_extensions(raw: str) -> set[str]:
    extensions: set[str] = set()

    for value in raw.split(","):
        value = value.strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = "." + value
        extensions.add(value)

    return extensions


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check PHP files for basic lexical and delimiter damage."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="PHP file or root directory to scan",
    )
    parser.add_argument(
        "--extensions",
        default=".php",
        help="Comma-separated extensions, such as .php,.phtml,.inc",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATH",
        help="Directory name or project-relative directory path to exclude",
    )
    parser.add_argument(
        "--short-tags",
        action="store_true",
        help="Recognize <? as a PHP opening tag, except <?xml",
    )

    args = parser.parse_args()
    root = Path(args.root)

    if not root.exists():
        parser.error(f"path does not exist: {root}")

    extensions = parse_extensions(args.extensions)
    if not extensions:
        parser.error("at least one extension must be supplied")

    excluded = normalize_excludes(args.exclude)
    files = collect_files(root, extensions, excluded)

    flagged_files = 0

    for path in files:
        file_problems = check_file(
            path,
            allow_short_tags=args.short_tags,
        )

        if not file_problems:
            continue

        flagged_files += 1
        print(f"[FAIL] {path}")

        for problem in file_problems:
            print(f"       - {problem}")

    print(
        f"\nScanned {len(files)} PHP file(s); "
        f"{flagged_files} flagged."
    )

    return 1 if flagged_files else 0


if __name__ == "__main__":
    sys.exit(main())
