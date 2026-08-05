from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Iterable

from emotivus_forge.core import secret_screening

TEMPLATE_MARKERS = (".example", ".sample", ".template", ".dist", "example.", "sample.", "template.")
SENSITIVE_PATH_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_dsa",
    "id_ecdsa", "id_ed25519", "credentials.json", "service-account*.json", "secrets.*",
    "*backup*.sql", "*dump*.sql", "*database*.sql", "*.sqlite", "*.sqlite3",
)
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^\s*(?:export\s+)?(?P<name>[A-Z0-9_.-]*(?:API[_-]?KEY|SECRET|PASSWORD|PASSWD|TOKEN|AUTH[_-]?TOKEN|CLIENT[_-]?SECRET)[A-Z0-9_.-]*)"
    r"\s*(?:=>|=|:)\s*(?P<value>[^\r\n#]+)"
)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")


def looks_like_placeholder(value: str) -> bool:
    clean = value.strip().strip("'\"").strip()
    lowered = clean.lower()
    placeholders = (
        "example", "changeme", "change-me", "your_", "your-", "placeholder", "dummy",
        "test-only", "synthetic", "not-a-real", "fake-", "${", "{{", "}}", "<", ">",
        "getenv", "env(", "process.env", "replace_me", "replace-me", "todo",
    )
    return (
        not clean
        or any(item in lowered for item in placeholders)
        or set(clean) <= {"x", "X", "*", "-", "_", "."}
    )


def _is_template_path(relative: str) -> bool:
    lowered = relative.lower()
    return any(marker in lowered for marker in TEMPLATE_MARKERS)


def _sensitive_path(relative: str) -> bool:
    lowered = relative.lower()
    name = Path(lowered).name
    return any(fnmatch.fnmatch(lowered, pattern.lower()) or fnmatch.fnmatch(name, pattern.lower()) for pattern in SENSITIVE_PATH_PATTERNS)


def classify_confidentiality_boundaries(
    project_root: Path,
    relative_paths: Iterable[str],
    *,
    max_files: int = 80,
    max_file_bytes: int = 256_000,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    private_paths: list[str] = []
    placeholder_paths: list[str] = []
    secret_metadata: list[dict[str, Any]] = []
    tiered: list[dict[str, Any]] = []
    examined = 0
    for relative in relative_paths:
        if examined >= max_files:
            break
        if not _sensitive_path(relative):
            continue
        examined += 1
        template = _is_template_path(relative)
        path = project_root / relative
        real_assignments = 0
        placeholder_assignments = 0
        private_key = False
        try:
            if path.is_file() and path.stat().st_size <= max_file_bytes:
                text = path.read_text(encoding="utf-8")
                tiered.extend(secret_screening.screen_text(relative, text, policy))
                private_key = bool(PRIVATE_KEY_RE.search(text))
                for match in SECRET_ASSIGNMENT_RE.finditer(text):
                    if looks_like_placeholder(match.group("value")):
                        placeholder_assignments += 1
                    else:
                        real_assignments += 1
        except (OSError, UnicodeDecodeError):
            pass
        if real_assignments or private_key:
            private_paths.append(relative)
            secret_metadata.append({
                "path": relative,
                "kind": "private-key" if private_key else "secret-assignment",
                "count": real_assignments + (1 if private_key else 0),
                "values_retained": False,
            })
        elif template:
            placeholder_paths.append(relative)
        else:
            # A sensitive live filename remains a boundary even when its current values look empty or placeholder-like.
            private_paths.append(relative)
            if placeholder_assignments:
                secret_metadata.append({
                    "path": relative,
                    "kind": "placeholder-in-live-sensitive-file",
                    "count": placeholder_assignments,
                    "values_retained": False,
                })
    tiered.extend(secret_screening.screen_paths(sorted(set(private_paths + placeholder_paths)), policy))
    screening = secret_screening.summarize(tiered)
    return {
        "tiered_screening": screening,
        "highest_confidentiality_level": screening["highest_level"],
        "private_boundary_candidates": sorted(set(private_paths))[:40],
        "placeholder_template_candidates": sorted(set(placeholder_paths))[:40],
        "secret_material_candidates": secret_metadata[:40],
        "files_examined": examined,
        "status": "observed" if private_paths or placeholder_paths else "unknown",
        "mode": "metadata-only",
    }
