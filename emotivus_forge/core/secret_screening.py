"""Tiered confidentiality and secret screening.

Forge classifies every confidentiality finding into exactly one level:

``BLOCK``
    Material that must never leave a private boundary. A distribution build stops.

``REVIEW``
    Material that is secret-shaped but not proven live. A human decides. Packaging
    continues unless the caller opts into strict mode.

``INFORMATIONAL``
    Placeholders, templates, and declared synthetic detector fixtures. Recorded so a
    later reader can see the scanner examined them and did not simply miss them.

Two rules are absolute:

1. Forge never records a matched secret value. Findings carry a path, a rule identity,
   and a redaction-safe descriptor only.
2. Forge never edits a file to remove a finding. Screening reports; it does not redact.
   Certified package and evidence bytes are immutable.
"""
from __future__ import annotations

import fnmatch
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

BLOCK = "BLOCK"
REVIEW = "REVIEW"
INFORMATIONAL = "INFORMATIONAL"

LEVEL_ORDER = {INFORMATIONAL: 0, REVIEW: 1, BLOCK: 2}

TEXT_SUFFIXES = {
    ".py", ".json", ".md", ".txt", ".html", ".css", ".js", ".ts", ".tsx",
    ".php", ".xml", ".yaml", ".yml", ".toml", ".sh", ".cmd", ".csv", ".svg",
    ".env", ".ini", ".cfg", ".conf", ".properties",
}

PLACEHOLDER_MARKERS = (
    "example", "changeme", "change-me", "your_", "your-", "placeholder", "dummy",
    "test-only", "synthetic", "not-a-real", "not_a_real", "fake-", "fake_", "${",
    "{{", "}}", "getenv", "env(", "process.env", "replace_me", "replace-me",
    "todo", "xxxxx", "redacted", "sample",
)

# Selected provider-key and regression shapes below are adapted from YesMem 2.3.5
# `internal/sanitize/secrets.go` and `secrets_test.go` under Apache-2.0. Forge
# deliberately changes the behavior: it reports tiered findings, retains no matched
# value, never redacts or mutates scanned bytes, and rejects noisy upstream defaults
# for email, phone, public IPv4, and arbitrary long hex strings.
#
# Each rule: id, level, compiled pattern, redaction-safe descriptor.
_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "gpg-private-key-block",
        BLOCK,
        re.compile(r"-----BEGIN PGP PRIVATE KEY " r"BLOCK-----"),
        "PGP private key block header",
    ),
    (
        "private-key-block",
        BLOCK,
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "PEM private key block header",
    ),
    (
        "anthropic-api-key",
        BLOCK,
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{50,}\b"),
        "Anthropic API key shape",
    ),
    (
        "openai-api-key",
        BLOCK,
        re.compile(r"\bsk-(?!ant-)(?:(?:proj|svcacct|admin)-)?[A-Za-z0-9_-]{20,}\b"),
        "OpenAI API key shape",
    ),
    (
        "aws-access-key-id",
        BLOCK,
        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "AWS access key identifier shape",
    ),
    (
        "github-personal-access-token",
        BLOCK,
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        "GitHub access token shape",
    ),
    (
        "putty-private-key",
        BLOCK,
        re.compile(r"PuTTY-User-Key-File-\d"),
        "PuTTY private key file header",
    ),
    (
        "bearer-token-literal",
        REVIEW,
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{16,}"),
        "hardcoded bearer token shape",
    ),
    (
        "inline-url-credentials",
        REVIEW,
        re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^:/@\s]+:[^@\s]+@[^/\s]+"),
        "URL containing inline user credentials",
    ),
    (
        "jwt-literal",
        REVIEW,
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "JSON Web Token shape",
    ),
    (
        "slack-access-token",
        REVIEW,
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
        "Slack access token shape",
    ),
)

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)^\s*(?:export\s+)?(?P<name>[A-Za-z0-9_.-]+)\s*(?:=>|=|:)\s*(?P<value>[^\r\n#]+)"
)

AWS_SECRET_ACCESS_KEY_RE = re.compile(
    r"(?i)(?:aws[_-]?secret[_-]?access[_-]?key)[\"']?\s*[:=]\s*[\"']?"
    r"(?P<value>[A-Za-z0-9/+]{40})(?:[\"']|\b)"
)

# A credential-bearing name ends in one of these *exact* segments. The plural forms are
# deliberately excluded: `provider_input_tokens` is a usage count, `api_token` is a
# credential. Screening that fires on every metric counter gets ignored by reviewers,
# and an ignored screen is worse than no screen.
# Bare "key" is deliberately absent: `key = ...` is overwhelmingly a dict key in real
# code. Credential names qualify themselves — api_key, secret_key, access_key.
SECRET_NAME_SEGMENTS = frozenset({
    "apikey", "api_key", "secret", "password", "passwd", "pwd", "token",
    "auth_token", "authtoken", "client_secret", "clientsecret", "private_key",
    "privatekey", "access_key", "accesskey", "secret_key", "secretkey",
})

# Values that are structurally incapable of being a credential.
NON_CREDENTIAL_VALUE_RE = re.compile(
    r"^(?:None|True|False|null|nil|undefined|self|cls|\d+(?:\.\d+)?|"
    r"object\b|str\b|int\b|bool\b|bytes\b|dict\b|list\b|Any\b|Optional\b)"
)
# A code symbol reference, not a literal: dotted attribute access, a call, or a plain
# lowercase snake_case name. An unquoted env-style secret is mixed-case with digits and
# must NOT be caught here.
IDENTIFIER_REFERENCE_RE = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+(?:\(.*\))?"
    r"|[A-Za-z_][A-Za-z0-9_]*\(.*\)"
    r"|[a-z_][a-z0-9_]*)[,)]?$"
)


def _credential_named(name: str) -> bool:
    """True when the assigned name ends in an exact credential segment."""
    lowered = name.strip().lower().strip(":")
    parts = [p for p in re.split(r"[_.\-]", lowered) if p]
    if not parts:
        return False
    if parts[-1] in SECRET_NAME_SEGMENTS:
        return True
    for size in (2, 3):
        if len(parts) >= size and "_".join(parts[-size:]) in SECRET_NAME_SEGMENTS:
            return True
    return False


def _plausible_credential_value(value: str) -> bool:
    """Reject type annotations, literals, and bare identifier references."""
    stripped = value.strip().rstrip(",").strip()
    if "|" in stripped or stripped.endswith(("{", "[")):
        return False
    # An interpolated or formatted value is computed at runtime and cannot be a
    # hardcoded credential: f"{os.getpid()}-{time.time_ns()}" is a uniqueness token.
    if stripped[:2].lower() in ("f'", 'f"') or ("{" in stripped and "}" in stripped):
        return False
    if ".format(" in stripped or stripped.startswith("%"):
        return False
    if NON_CREDENTIAL_VALUE_RE.match(stripped):
        return False
    quoted = stripped.startswith(("'", '"')) and len(stripped) > 2
    body = stripped.strip("'\"").strip()
    if not quoted and IDENTIFIER_REFERENCE_RE.match(stripped):
        return False
    if len(body) < 8:
        return False
    return shannon_entropy(body) >= 2.5

SENSITIVE_PATH_PATTERNS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa", "id_dsa",
    "id_ecdsa", "id_ed25519", "credentials.json", "service-account*.json",
    "secrets.*", "*backup*.sql", "*dump*.sql", "*.sqlite", "*.sqlite3",
)

TEMPLATE_MARKERS = (".example", ".sample", ".template", ".dist", "example.", "sample.", "template.")


def shannon_entropy(value: str) -> float:
    """Return Shannon entropy in bits per character. Empty input scores zero."""
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def looks_like_placeholder(value: str) -> bool:
    clean = value.strip().strip("'\"").strip()
    lowered = clean.lower()
    return (
        not clean
        or any(marker in lowered for marker in PLACEHOLDER_MARKERS)
        or set(clean) <= {"x", "X", "*", "-", "_", ".", "0"}
    )


def is_template_path(relative: str) -> bool:
    lowered = relative.lower()
    return any(marker in lowered for marker in TEMPLATE_MARKERS)


def is_sensitive_path(relative: str) -> bool:
    lowered = relative.lower()
    name = Path(lowered).name
    return any(
        fnmatch.fnmatch(lowered, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in SENSITIVE_PATH_PATTERNS
    )


def _matches_any(relative: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        cleaned = str(pattern).strip()
        if not cleaned:
            continue
        if fnmatch.fnmatch(relative, cleaned) or relative.startswith(cleaned.rstrip("/") + "/"):
            return True
    return False


def normalize_policy(policy: dict[str, Any] | None) -> dict[str, list[str]]:
    """Accept schema 1 and schema 2 policies and return one normalized shape.

    Schema 1 supplies a single ``forbidden_terms`` list, which is treated as BLOCK.
    Schema 2 additionally supplies ``review_terms`` and ``informational_terms``.
    """
    source = policy or {}
    normalized = {
        "block_terms": [],
        "review_terms": [],
        "informational_terms": [],
        "block_path_patterns": [],
        "review_path_patterns": [],
        "synthetic_fixture_paths": [],
        "allow_paths": [],
    }
    aliases = {
        "block_terms": ("forbidden_terms", "block_terms"),
        "review_terms": ("review_terms",),
        "informational_terms": ("informational_terms",),
        "block_path_patterns": ("forbidden_path_patterns", "block_path_patterns"),
        "review_path_patterns": ("review_path_patterns",),
        "synthetic_fixture_paths": ("synthetic_fixture_paths",),
        "allow_paths": ("allow_paths",),
    }
    for key, names in aliases.items():
        for name in names:
            for value in source.get(name, []) or []:
                text = str(value).strip()
                if text and text not in normalized[key]:
                    normalized[key].append(text)
    return normalized


def _finding(
    relative: str,
    rule_id: str,
    level: str,
    descriptor: str,
    *,
    downgraded_from: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "path": relative,
        "rule": rule_id,
        "level": level,
        "descriptor": descriptor,
        "value_retained": False,
    }
    if downgraded_from:
        finding["downgraded_from"] = downgraded_from
    if reason:
        finding["reason"] = reason
    return finding


def screen_text(
    relative: str,
    text: str,
    policy: dict[str, list[str]] | None = None,
    *,
    entropy_threshold: float = 4.0,
) -> list[dict[str, Any]]:
    """Screen one text body. Returns findings sorted by path, then rule identity.

    A path declared under ``synthetic_fixture_paths`` never produces BLOCK or REVIEW.
    Its findings are downgraded to INFORMATIONAL and carry ``downgraded_from`` so the
    downgrade is visible rather than silent.
    """
    rules = normalize_policy(policy) if policy is not None else normalize_policy(None)
    if _matches_any(relative, rules["allow_paths"]):
        return []
    synthetic = _matches_any(relative, rules["synthetic_fixture_paths"])
    template = is_template_path(relative)
    findings: list[dict[str, Any]] = []

    def record(rule_id: str, level: str, descriptor: str) -> None:
        if synthetic and level in (BLOCK, REVIEW):
            findings.append(_finding(
                relative, rule_id, INFORMATIONAL, descriptor,
                downgraded_from=level, reason="declared synthetic detector fixture",
            ))
            return
        findings.append(_finding(relative, rule_id, level, descriptor))

    for rule_id, level, pattern, descriptor in _RULES:
        if pattern.search(text):
            record(rule_id, level, descriptor)

    lowered = text.casefold()
    for term in rules["block_terms"]:
        if term.casefold() in lowered:
            record("policy-block-term", BLOCK, "policy block term present")
            break
    for term in rules["review_terms"]:
        if term.casefold() in lowered:
            record("policy-review-term", REVIEW, "policy review term present")
            break
    for term in rules["informational_terms"]:
        if term.casefold() in lowered:
            findings.append(_finding(
                relative, "policy-informational-term", INFORMATIONAL,
                "policy informational term present",
            ))
            break

    for match in AWS_SECRET_ACCESS_KEY_RE.finditer(text):
        value = match.group("value")
        if looks_like_placeholder(value):
            findings.append(_finding(
                relative, "aws-secret-access-key-placeholder", INFORMATIONAL,
                "AWS secret access key label holding a placeholder",
            ))
        elif template:
            findings.append(_finding(
                relative, "aws-secret-access-key-template", INFORMATIONAL,
                "AWS secret access key shape inside a template file",
            ))
        elif is_sensitive_path(relative):
            record("aws-secret-access-key-live", BLOCK,
                   "AWS secret access key shape in a live sensitive file")
        else:
            record("aws-secret-access-key-literal", REVIEW,
                   "AWS secret access key shape outside a declared template")

    for match in SECRET_ASSIGNMENT_RE.finditer(text):
        if not _credential_named(match.group("name")):
            continue
        value = match.group("value")
        if not looks_like_placeholder(value) and not _plausible_credential_value(value):
            continue
        if looks_like_placeholder(value):
            findings.append(_finding(
                relative, "secret-assignment-placeholder", INFORMATIONAL,
                "secret-named assignment holding a placeholder",
            ))
            continue
        if template:
            findings.append(_finding(
                relative, "secret-assignment-template", INFORMATIONAL,
                "secret-named assignment inside a template file",
            ))
            continue
        stripped = value.strip().strip("'\"")
        entropy = shannon_entropy(stripped)
        if is_sensitive_path(relative) and entropy >= entropy_threshold:
            record("secret-assignment-live-high-entropy", BLOCK,
                   "high-entropy secret assignment in a live sensitive file")
        else:
            record("secret-assignment-literal", REVIEW,
                   "secret-named assignment holding a non-placeholder literal")

    return sorted(findings, key=lambda f: (f["path"], f["rule"], f["level"]))


def screen_paths(relative_paths: Iterable[str], policy: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Screen path names alone. Used where file bodies are unavailable."""
    rules = normalize_policy(policy)
    findings: list[dict[str, Any]] = []
    for relative in relative_paths:
        if _matches_any(relative, rules["allow_paths"]):
            continue
        synthetic = _matches_any(relative, rules["synthetic_fixture_paths"])
        level_for = lambda lvl: INFORMATIONAL if synthetic else lvl  # noqa: E731
        if _matches_any(relative, rules["block_path_patterns"]):
            findings.append(_finding(
                relative, "policy-block-path", level_for(BLOCK), "policy block path pattern",
                downgraded_from=BLOCK if synthetic else None,
                reason="declared synthetic detector fixture" if synthetic else None,
            ))
        if _matches_any(relative, rules["review_path_patterns"]):
            findings.append(_finding(
                relative, "policy-review-path", level_for(REVIEW), "policy review path pattern",
                downgraded_from=REVIEW if synthetic else None,
                reason="declared synthetic detector fixture" if synthetic else None,
            ))
        if is_sensitive_path(relative) and not is_template_path(relative):
            findings.append(_finding(
                relative, "sensitive-filename", level_for(REVIEW),
                "sensitive filename shape",
                downgraded_from=REVIEW if synthetic else None,
                reason="declared synthetic detector fixture" if synthetic else None,
            ))
    return sorted(findings, key=lambda f: (f["path"], f["rule"], f["level"]))


def highest_level(findings: Iterable[dict[str, Any]]) -> str | None:
    levels = [f.get("level") for f in findings if f.get("level") in LEVEL_ORDER]
    if not levels:
        return None
    return max(levels, key=lambda level: LEVEL_ORDER[level])


def summarize(findings: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(findings)
    counts = {BLOCK: 0, REVIEW: 0, INFORMATIONAL: 0}
    for finding in items:
        level = finding.get("level")
        if level in counts:
            counts[level] += 1
    return {
        "schema": "forge-secret-screening/1",
        "counts": counts,
        "highest_level": highest_level(items),
        "blocked": counts[BLOCK] > 0,
        "findings": items,
        "values_retained": False,
        "mutates_scanned_bytes": False,
        "truth_boundary": (
            "Shape-based screening over declared patterns and policy terms. A PASS means "
            "no configured rule matched. It does not prove a distribution is free of "
            "private information, and no finding is proof that a matched value is live."
        ),
    }
