from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

PEM_BLOCK_RE = re.compile(
    r"(?ms)^[ \t]*-----BEGIN (?P<label>(?:RSA |OPENSSH |EC )?PRIVATE KEY)-----[ \t]*\r?\n"
    r"(?P<body>.{20,}?)"
    r"^[ \t]*-----END (?P=label)-----[ \t]*$"
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)\b(?:api[_-]?key|secret|password|passwd|token|auth[_-]?token|client[_-]?secret)\b"
    r"\s*(?:=>|=|:)\s*['\"]([^'\"\r\n]{8,})['\"]"
)
SYNTHETIC_SECRET_TAG = "forge: synthetic-secret"
SYNTHETIC_KEY_TAG = "forge: synthetic-private-key"


def path_matches_fixture(relative: str, fixture_paths: Iterable[str]) -> bool:
    rel = relative.replace("\\", "/").strip("/")
    for raw in fixture_paths:
        candidate = str(raw).replace("\\", "/").strip("/")
        if candidate and (rel == candidate or rel.startswith(candidate + "/")):
            return True
    return False


def looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    placeholders = (
        "example", "changeme", "change-me", "your_", "your-", "placeholder",
        "dummy", "test-only", "synthetic", "not-a-real", "fake-", "${", "getenv", "env(",
    )
    return any(item in lowered for item in placeholders) or set(value) <= {"x", "X", "*", "-", "_"}


def _line_has_tag(text: str, offset: int, tag: str) -> bool:
    line_start = text.rfind("\n", 0, offset) + 1
    previous_end = max(0, line_start - 1)
    previous_start = text.rfind("\n", 0, previous_end) + 1
    context = text[previous_start:text.find("\n", offset) if text.find("\n", offset) != -1 else len(text)]
    return tag.lower() in context.lower()


def private_key_matches(text: str, relative: str, fixture_paths: Iterable[str] = ()) -> list[re.Match[str]]:
    if path_matches_fixture(relative, fixture_paths):
        return []
    matches: list[re.Match[str]] = []
    for match in PEM_BLOCK_RE.finditer(text):
        if _line_has_tag(text, match.start(), SYNTHETIC_KEY_TAG):
            continue
        body = match.group("body")
        compact = "".join(line.strip() for line in body.splitlines() if line.strip() and ":" not in line)
        if len(compact) < 24:
            continue
        matches.append(match)
    return matches


def secret_assignment_matches(text: str, relative: str, fixture_paths: Iterable[str] = ()) -> list[re.Match[str]]:
    if path_matches_fixture(relative, fixture_paths):
        return []
    matches: list[re.Match[str]] = []
    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        value = match.group(1).strip()
        if looks_like_placeholder(value) or _line_has_tag(text, match.start(), SYNTHETIC_SECRET_TAG):
            continue
        matches.append(match)
    return matches


def has_private_key_bytes(data: bytes, relative: str, fixture_paths: Iterable[str] = ()) -> bool:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return False
    return bool(private_key_matches(text, relative, fixture_paths))


def has_secret_assignment_bytes(data: bytes, relative: str, fixture_paths: Iterable[str] = ()) -> bool:
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception:
        return False
    return bool(secret_assignment_matches(text, relative, fixture_paths))
