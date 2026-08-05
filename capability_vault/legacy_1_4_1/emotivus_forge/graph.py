from __future__ import annotations

import json
import hashlib
import re
import subprocess
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .utils import iter_project_files, normalize_rel, tree_fingerprint, utc_now, write_json

TEXT_SUFFIXES = {
    ".php", ".phtml", ".inc", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".py", ".html", ".htm", ".css", ".scss", ".sass", ".less", ".json", ".xml",
    ".yml", ".yaml", ".toml", ".ini", ".conf", ".sql", ".md", ".sh",
}
ENTRY_NAMES = {
    "index.php", "index.html", "index.htm", "app.php", "app.py", "main.py", "server.py",
    "app.js", "server.js", "main.js", "main.ts", "manage.py", "wsgi.py", "asgi.py",
}
CONFIG_NAMES = {
    "package.json", "composer.json", "pyproject.toml", "requirements.txt", "Dockerfile",
    "docker-compose.yml", "compose.yml", ".htaccess", "nginx.conf", "php.ini", "web.config",
}
SCRIPT_SUFFIXES = {".php", ".phtml", ".py", ".js", ".mjs", ".cjs", ".ts", ".sh"}
WEB_ROOT_DIRS = {"admin", "public", "api", "pages", "routes", "web", "www", "htdocs"}
WEBHOOK_DIRS = {"webhook", "webhooks", "hook", "hooks", "callback", "callbacks", "receiver", "receivers"}
JOB_DIRS = {"job", "jobs", "cron", "crons", "scheduler", "scheduled", "worker", "workers", "queue", "queues"}
CLI_DIRS = {"bin", "cli", "console", "command", "commands"}
CLIENT_ASSET_DIRS = {"asset", "assets", "static", "scripts", "js", "javascript", "frontend"}
PHP_SUPPORT_NAMES = {
    "autoload.php", "bootstrap.php", "common.php", "config.php", "constants.php",
    "db.php", "database.php", "functions.php", "helpers.php", "init.php",
}
ROUTE_PATTERNS = (
    re.compile(r"Route::(?:get|post|put|patch|delete|options|any)\s*\(\s*['\"]([^'\"]+)", re.I),
    re.compile(r"(?:app|router)\.(?:get|post|put|patch|delete|options|all)\s*\(\s*['\"]([^'\"]+)", re.I),
    re.compile(r"@(?:app|router)\.(?:route|get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)", re.I),
    re.compile(r"path\s*\(\s*['\"]([^'\"]+)", re.I),
)
URL_RE = re.compile(r"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+")
ENV_PATTERNS = (
    re.compile(r"getenv\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
    re.compile(r"\$_ENV\s*\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"process\.env\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"process\.env\s*\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]"),
    re.compile(r"os\.(?:environ|getenv)(?:\.get)?\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"),
)
PHP_DEP_RE = re.compile(r"(?:require|require_once|include|include_once)\s*(?:\(\s*)?['\"]([^'\"]+)['\"]", re.I)
JS_DEP_RE = re.compile(r"(?:from\s+|require\s*\(\s*|import\s*\(\s*|\bimport\s+)['\"]([^'\"]+)['\"]")
HTML_DEP_RE = re.compile(r"(?:src|href)\s*=\s*['\"]([^'\"#?]+)", re.I)
PY_IMPORT_RE = re.compile(r"(?m)^\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))")


@dataclass
class Node:
    node_id: str
    type: str
    path: str
    name: str
    subsystem: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.node_id,
            "type": self.type,
            "path": self.path,
            "name": self.name,
            "subsystem": self.subsystem,
            "evidence": self.evidence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    type: str
    evidence: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "type": self.type, "evidence": self.evidence}


def _read_text(path: Path, limit: int = 2_000_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _node_id(kind: str, value: str) -> str:
    import hashlib
    safe = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:64] or "item"
    suffix = hashlib.sha256(f"{kind}\0{value}".encode()).hexdigest()[:10]
    return f"{kind}:{safe}:{suffix}"


def _subsystem(relative: str, text: str, corrections: dict[str, str] | None = None) -> tuple[str, float, list[str]]:
    normalized = relative.replace("\\", "/")
    for pattern, target in (corrections or {}).items():
        if normalized == pattern or normalized.startswith(pattern.rstrip("/") + "/"):
            return str(target), 1.0, [f"project correction: {pattern}"]
    path_lower = f"/{normalized.lower()}/"
    text_lower = text[:100_000].lower()
    probes = (
        ("authorization", ("permission", "permissions", "role", "roles", "authorize", "authorization", "rbac", "acl", "access-control")),
        ("authentication", ("/auth", "login", "logout", "password", "session", "authenticate", "two-factor", "2fa")),
        ("payments", ("payment", "checkout", "stripe", "paypal", "braintree")),
        ("database", ("migration", "database", "pdo", "mysqli", "sequelize", "sqlalchemy", "prisma", "select ", "insert ", "update ")),
        ("integrations", ("webhook", "twilio", "smtp", "sendgrid", "mailgun", "api.")),
        ("scheduler", ("cron", "schedule", "scheduler", "queue", "worker")),
        ("uploads", ("upload", "multipart", "filetype", "move_uploaded_file", "storage")),
        ("admin", ("/admin", "dashboard", "settings", "management")),
        ("frontend", (".css/", ".html/", "component", "template", "stylesheet", "document.queryselector")),
        ("testing", ("/test", "spec.", "pytest", "unittest", "phpunit")),
        ("deployment", ("dockerfile", ".htaccess", "deploy", "release", "workflow")),
    )
    scores: list[tuple[int, str, list[str]]] = []
    for name, tokens in probes:
        path_hits = [token for token in tokens if token in path_lower]
        text_hits = [token for token in tokens if token in text_lower]
        score = len(path_hits) * 4 + min(len(text_hits), 4)
        if score:
            scores.append((score, name, path_hits + text_hits[:4]))
    if scores:
        scores.sort(reverse=True)
        score, name, hits = scores[0]
        confidence = min(0.95, 0.45 + score * 0.08)
        if score >= 4 or len(set(hits)) >= 2:
            return name, confidence, ["matched: " + ", ".join(dict.fromkeys(hits))]
    first = normalized.split("/", 1)[0]
    fallback = first if "." not in first and first else "application"
    return fallback, 0.35, ["directory fallback"]


def _file_type(path: Path, relative: str, text: str) -> str:
    lower_parts = [part.lower() for part in Path(relative).parts]
    parent_parts = lower_parts[:-1]
    name = path.name.lower()
    suffix = path.suffix.lower()
    if "test" in lower_parts or "tests" in lower_parts or name.startswith("test_") or name.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts")):
        return "test"
    if "migration" in lower_parts or "migrations" in lower_parts or suffix == ".sql":
        return "migration"
    if name in CONFIG_NAMES or name.startswith(".env"):
        return "configuration"
    if suffix in SCRIPT_SUFFIXES:
        lowered_name = f"{relative} {name}".lower()
        if any(part in WEBHOOK_DIRS for part in parent_parts) or any(token in lowered_name for token in ("webhook", "callback", "inbound", "receiver")):
            return "webhook"
        if any(part in JOB_DIRS for part in parent_parts) or any(token in name for token in ("cron", "schedule", "scheduler", "worker", "queue")):
            return "scheduled-job"
        if any(part in CLI_DIRS for part in parent_parts):
            return "cli"
    entry_name = name in ENTRY_NAMES or relative.lower() in {"public/index.php", "src/index.js", "src/index.ts"}
    client_asset = suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"} and any(part in CLIENT_ASSET_DIRS for part in parent_parts)
    if entry_name and not client_asset:
        return "entrypoint"
    if suffix == ".py" and (
        text.startswith("#!")
        or re.search(r'(?m)^\s*if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:', text)
    ):
        return "cli"
    if suffix in {".php", ".phtml"} and any(token in text for token in ("PHP_SAPI", "$argv", "STDOUT", "STDERR")):
        return "cli"
    if suffix in {".php", ".phtml"}:
        excluded = {"includes", "include", "vendor", "tests", "test", "tools", "scripts", "migrations", "migration", "docs", "fixtures", "cache", "storage", "backups"}
        runtime_tokens = ("<!doctype", "<html", "<form", "$_get", "$_post", "session_start", "http_response_code", "json_encode", "require_login", "require_permission")
        nested_support_file = len(lower_parts) > 1 and name in PHP_SUPPORT_NAMES and (not parent_parts or parent_parts[0] not in WEB_ROOT_DIRS)
        if not nested_support_file and not any(part in excluded for part in parent_parts) and (len(Path(relative).parts) == 1 or (parent_parts and parent_parts[0] in WEB_ROOT_DIRS) or any(token in text.lower() for token in runtime_tokens)):
            return "entrypoint"
    if suffix in {".html", ".htm", ".php", ".phtml"} and ("template" in lower_parts or "views" in lower_parts or "templates" in lower_parts):
        return "template"
    if suffix in {".css", ".scss", ".sass", ".less"}:
        return "style"
    if suffix in {".md", ".txt"}:
        return "documentation"
    return "source"


def _resolve_candidate(root: Path, source: Path, raw: str, files_by_path: dict[str, str]) -> str | None:
    raw = raw.strip().split("?", 1)[0].split("#", 1)[0]
    if not raw or raw.startswith(("http://", "https://", "//", "data:", "mailto:", "tel:")):
        return None
    candidates: list[Path] = []
    if raw.startswith("/"):
        candidates.append(root / raw.lstrip("/"))
    else:
        candidates.append(source.parent / raw)
    expanded: list[Path] = []
    for candidate in candidates:
        expanded.append(candidate)
        if not candidate.suffix:
            for suffix in (".php", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".html", ".css", ".json"):
                expanded.append(candidate.with_suffix(suffix))
            for index_name in ("index.php", "index.py", "index.js", "index.ts", "index.html"):
                expanded.append(candidate / index_name)
    for candidate in expanded:
        try:
            relative = candidate.resolve().relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        if relative in files_by_path:
            return files_by_path[relative]
    return None


def _git_changed(project_root: Path) -> list[str]:
    if not (project_root / ".git").exists():
        return []
    commands = (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    found: list[str] = []
    for command in commands:
        try:
            process = subprocess.run(command, cwd=project_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if process.returncode == 0:
            for line in process.stdout.splitlines():
                value = normalize_rel(line)
                if value and value not in found:
                    found.append(value)
    return found


def _tool_ecosystem_records(project_root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    registry_dir = project_root / ".forge" / "tool-ecosystems"
    for item in config.get("tool_migration", {}).get("ecosystems", []):
        if not isinstance(item, dict):
            continue
        ecosystem_id = str(item.get("id", ""))
        registry = registry_dir / f"{ecosystem_id}.json" if ecosystem_id else None
        payload: dict[str, Any] = dict(item)
        if registry and registry.is_file():
            try:
                loaded = json.loads(registry.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    payload = loaded
            except (OSError, json.JSONDecodeError):
                pass
        records.append(payload)
    return records


def _command_fingerprint(command: list[Any]) -> str:
    return hashlib.sha256(json.dumps([str(item) for item in command], separators=(",", ":")).encode("utf-8")).hexdigest()


def build_graph(project_root: Path, forge_root: Path, config: dict[str, Any], *, write: bool = True) -> dict[str, Any]:
    project_root = project_root.resolve()
    forge_root = forge_root.resolve()
    excludes = list(config.get("paths", {}).get("exclude", [])) + [".emotivus-forge.json", "FORGE-AGENT.md", ".deployignore"]
    files = list(iter_project_files(project_root, excludes, forge_root))
    nodes: list[Node] = []
    edges: set[Edge] = set()
    file_nodes: dict[str, str] = {}
    texts: dict[str, str] = {}
    facts: dict[str, set[str]] = {
        "routes": set(), "environment_variables": set(), "external_hosts": set(), "cron_jobs": set(),
        "database_artifacts": set(), "upload_flows": set(), "authentication_flows": set(), "authorization_surfaces": set(), "privilege_management": set(), "browser_surfaces": set(), "webhooks": set(),
    }

    for path in files:
        relative = path.relative_to(project_root).as_posix()
        text = _read_text(path) if path.suffix.lower() in TEXT_SUFFIXES or path.name in CONFIG_NAMES else ""
        texts[relative] = text
        kind = _file_type(path, relative, text)
        corrections = config.get("graph", {}).get("classification", {}).get("corrections", {})
        subsystem, subsystem_confidence, subsystem_evidence = _subsystem(relative, text, corrections if isinstance(corrections, dict) else {})
        evidence: list[str] = list(subsystem_evidence)
        if kind != "source":
            evidence.append(f"classified as {kind}")
        node = Node(_node_id("file", relative), kind, relative, path.name, subsystem, evidence, {"bytes": path.stat().st_size, "subsystem_confidence": round(subsystem_confidence, 3)})
        nodes.append(node)
        file_nodes[relative] = node.node_id

    nodes_by_id = {node.node_id: node for node in nodes}
    special_nodes: dict[tuple[str, str], str] = {}

    def add_special(kind: str, name: str, path: str, subsystem: str, evidence: str, metadata: dict[str, Any] | None = None) -> str:
        key = (kind, name)
        if key in special_nodes:
            node = nodes_by_id[special_nodes[key]]
            if evidence and evidence not in node.evidence:
                node.evidence.append(evidence)
            return node.node_id
        node = Node(_node_id(kind, name), kind, path, name, subsystem, [evidence] if evidence else [], metadata or {})
        nodes.append(node)
        nodes_by_id[node.node_id] = node
        special_nodes[key] = node.node_id
        return node.node_id

    for path in files:
        relative = path.relative_to(project_root).as_posix()
        source_id = file_nodes[relative]
        text = texts.get(relative, "")
        suffix = path.suffix.lower()

        dependencies: list[str] = []
        if suffix in {".php", ".phtml", ".inc"}:
            dependencies.extend(PHP_DEP_RE.findall(text))
        if suffix in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}:
            dependencies.extend(JS_DEP_RE.findall(text))
        if suffix in {".html", ".htm", ".php", ".phtml"}:
            dependencies.extend(HTML_DEP_RE.findall(text))
        if suffix == ".py":
            for first, second in PY_IMPORT_RE.findall(text):
                module = first or second
                if module:
                    dependencies.append(module.replace(".", "/"))
        for raw in dependencies:
            target = _resolve_candidate(project_root, path, raw, file_nodes)
            if target and target != source_id:
                edges.add(Edge(source_id, target, "depends-on", raw))

        for pattern in ROUTE_PATTERNS:
            for route in pattern.findall(text):
                facts["routes"].add(route)
                route_id = add_special("route", route, relative, "routing", f"declared in {relative}")
                edges.add(Edge(source_id, route_id, "declares", route))

        for pattern in ENV_PATTERNS:
            for variable in pattern.findall(text):
                facts["environment_variables"].add(variable)
                env_id = add_special("environment-variable", variable, relative, "configuration", f"referenced by {relative}")
                edges.add(Edge(source_id, env_id, "reads", variable))

        for url in URL_RE.findall(text):
            host = urlparse(url.rstrip(".,);]\"'")).hostname or ""
            if host and host not in {"localhost", "127.0.0.1", "example.com"}:
                facts["external_hosts"].add(host)
                integration_id = add_special("external-integration", host, relative, "integrations", f"URL referenced by {relative}")
                edges.add(Edge(source_id, integration_id, "calls", host))

        lowered = text.lower()
        if nodes_by_id[source_id].type == "webhook" or any(token in lowered for token in ("webhook", "x-signature", "signature_header", "callback_url")):
            facts["webhooks"].add(relative)
            if nodes_by_id[source_id].type == "webhook":
                if "webhook indicators detected" not in nodes_by_id[source_id].evidence:
                    nodes_by_id[source_id].evidence.append("webhook indicators detected")
            else:
                webhook_id = add_special("webhook", relative, relative, "integrations", "webhook indicators detected")
                edges.add(Edge(source_id, webhook_id, "implements", "webhook"))
        if any(token in lowered for token in ("move_uploaded_file", "multipart/form-data", "request.files", "multer(", "upload.single", "upload.array")):
            facts["upload_flows"].add(relative)
        if any(token in lowered for token in ("password_hash", "password_verify", "login", "logout", "authenticate", "session_start", "two-factor", "2fa")):
            facts["authentication_flows"].add(relative)
        if any(token in lowered for token in ("permission", "authorize", "authorization", "role", "rbac", "acl", "access denied", "forbidden")):
            facts["authorization_surfaces"].add(relative)
        if any(token in lowered for token in ("set_role", "setrole", "grant permission", "revoke permission", "permission override", "users.manage", "manage users", "admin_users")):
            facts["privilege_management"].add(relative)
        if suffix in {".html", ".htm", ".php", ".phtml", ".jsx", ".tsx", ".css", ".scss"} and any(token in lowered for token in ("<form", "<button", "aria-", "viewport", "@media", "document.queryselector")):
            facts["browser_surfaces"].add(relative)
        if any(token in lowered for token in ("select ", "insert ", "update ", "delete from", "create table", "alter table", "pdo", "mysqli", "sqlalchemy", "sequelize", "prisma")):
            facts["database_artifacts"].add(relative)
        if any(token in lowered for token in ("cron", "schedule(", "scheduler", "setinterval(", "celery", "queue worker")) or nodes_by_id[source_id].type == "scheduled-job":
            facts["cron_jobs"].add(relative)

    # Link tests to files by dependency edge, basename, or explicit path mention.
    source_by_stem: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        if node.path and node.type not in {"test", "documentation"}:
            source_by_stem[Path(node.path).stem.lower()].append(node.node_id)
    for node in nodes:
        if node.type != "test":
            continue
        text = texts.get(node.path, "").lower()
        test_stem = Path(node.path).stem.lower().replace("test_", "").replace("_test", "").replace(".test", "").replace(".spec", "")
        targets = set(source_by_stem.get(test_stem, []))
        for stem, ids in source_by_stem.items():
            if len(stem) >= 4 and stem in text:
                targets.update(ids)
        for target in targets:
            if target != node.node_id:
                edges.add(Edge(node.node_id, target, "tests", "name or reference match"))

    # Represent adopted host tool ecosystems as typed metadata-only architecture.
    ecosystem_facts: list[str] = []
    for ecosystem in _tool_ecosystem_records(project_root, config):
        ecosystem_id_value = str(ecosystem.get("id", "tool-ecosystem"))
        manifest_path = str(ecosystem.get("manifest", ""))
        ecosystem_node = add_special(
            "tool-ecosystem", ecosystem_id_value, manifest_path, "tooling",
            "host-authoritative adopted tool ecosystem",
            {
                "authority": str(ecosystem.get("authority", "host-authoritative")),
                "status": str(ecosystem.get("status", "")),
                "input_sha256": str(ecosystem.get("working_set", {}).get("input_fingerprint", {}).get("sha256", "")),
                "dataset_sha256": str(ecosystem.get("working_set", {}).get("dataset_fingerprint", {}).get("sha256", "")),
                "content_capture": "none",
            },
        )
        ecosystem_facts.append(ecosystem_id_value)
        input_set_name = f"{ecosystem_id_value}:inputs"
        input_set = add_special(
            "tool-input-set", input_set_name, manifest_path, "tooling",
            "declared ecosystem inputs; hashes and relative paths only",
            {
                "files": int(ecosystem.get("working_set", {}).get("input_fingerprint", {}).get("files", 0)),
                "bytes": int(ecosystem.get("working_set", {}).get("input_fingerprint", {}).get("bytes", 0)),
                "sha256": str(ecosystem.get("working_set", {}).get("input_fingerprint", {}).get("sha256", "")),
                "content_capture": "none",
            },
        )
        edges.add(Edge(ecosystem_node, input_set, "owns", "host manifest declares working set"))
        for input_path in ecosystem.get("working_set", {}).get("input_paths", []):
            relative_input = str(input_path).replace("\\", "/")
            target = file_nodes.get(relative_input)
            if target:
                edges.add(Edge(input_set, target, "contains", "declared ecosystem input"))
        for command_entry in [item for group in config.get("commands", {}).values() for item in group if isinstance(item, dict) and str(item.get("ecosystem_id", "")) == ecosystem_id_value]:
            command_id = str(command_entry.get("id", "ecosystem-command"))
            command_node = add_special(
                "tool-command", command_id, manifest_path, "tooling",
                "canonical adopted command",
                {
                    "profile": next((profile for profile, group in config.get("commands", {}).items() if command_entry in group), ""),
                    "command_sha256": _command_fingerprint(list(command_entry.get("command", []))),
                    "content_capture": "none",
                },
            )
            edges.add(Edge(ecosystem_node, command_node, "runs", "canonical profile registration"))
            edges.add(Edge(command_node, input_set, "reads", "evidence fingerprint depends on declared input set"))
            for generated in ecosystem.get("generated_state", []):
                if not isinstance(generated, dict) or not generated.get("path"):
                    continue
                state_path = str(generated.get("path"))
                state_node = add_special(
                    "generated-state", f"{ecosystem_id_value}:{state_path}", state_path, "tooling",
                    "producer-owned generated state location",
                    {"exists": bool(generated.get("exists")), "files": int(generated.get("files", 0)), "bytes": int(generated.get("bytes", 0)), "content_capture": "none"},
                )
                edges.add(Edge(command_node, state_node, "generates", "host tool retains lifecycle ownership"))
        for product in ecosystem.get("bundled_products", []):
            if not isinstance(product, dict) or not product.get("path"):
                continue
            product_path = str(product.get("path"))
            product_node = add_special(
                "bundled-product", f"{ecosystem_id_value}:{product_path}", product_path, "tooling",
                "nested product ownership boundary",
                {"name": str(product.get("name", "")), "version": str(product.get("version", "")), "managed_files": int(product.get("managed_files", 0)), "content_capture": "none"},
            )
            edges.add(Edge(ecosystem_node, product_node, "contains", "bundled product remains independently owned"))
    facts["tool_ecosystems"] = set(ecosystem_facts)

    # Join source and delivery models when an owner-facing delivery manifest exists.
    delivery_path = project_root / str(config.get("delivery_proof", {}).get("manifest_path", ".forge/delivery/delivery-manifest.json"))
    try:
        delivery_manifest = json.loads(delivery_path.read_text(encoding="utf-8")) if delivery_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        delivery_manifest = {}
    artifact_nodes: dict[str, str] = {}
    for artifact in delivery_manifest.get("artifacts", []) if isinstance(delivery_manifest, dict) else []:
        if not isinstance(artifact, dict):
            continue
        artifact_path = str(artifact.get("path", ""))
        role = str(artifact.get("role", "artifact"))
        if not artifact_path:
            continue
        artifact_id = add_special(
            "delivered-artifact", artifact_path, artifact_path, "delivery",
            f"declared delivery artifact role={role}",
            {"role": role, "sha256": str(artifact.get("sha256", "")), "status": str(artifact.get("status", "current"))},
        )
        artifact_nodes[artifact_path] = artifact_id
        for raw_input in artifact.get("inputs", []) if isinstance(artifact.get("inputs"), list) else []:
            input_value = str(raw_input).replace("\\", "/")
            if input_value in file_nodes:
                edges.add(Edge(file_nodes[input_value], artifact_id, "generates", "delivery provenance input"))
            else:
                # Directory/glob inputs are connected to all currently matched source files.
                for relative, source_id in file_nodes.items():
                    if relative == input_value or relative.startswith(input_value.rstrip("/") + "/") or Path(relative).match(input_value):
                        edges.add(Edge(source_id, artifact_id, "generates", f"delivery input {input_value}"))
    final = delivery_manifest.get("final_bundle", {}) if isinstance(delivery_manifest, dict) and isinstance(delivery_manifest.get("final_bundle"), dict) else {}
    final_path = str(final.get("path", ""))
    if final_path:
        final_id = add_special(
            "delivery-bundle", final_path, final_path, "delivery", "final owner-facing delivery bundle",
            {"sha256": str(final.get("sha256", "")), "members": list(final.get("members", [])) if isinstance(final.get("members"), list) else []},
        )
        for member in final.get("members", []) if isinstance(final.get("members"), list) else []:
            member_id = artifact_nodes.get(str(member))
            if member_id:
                edges.add(Edge(member_id, final_id, "contained-in", "final delivery membership"))

    subsystem_counts: dict[str, int] = defaultdict(int)
    type_counts: dict[str, int] = defaultdict(int)
    for node in nodes:
        subsystem_counts[node.subsystem] += 1
        type_counts[node.type] += 1

    payload = {
        "schema": 1,
        "forge": "Emotivus Forge",
        "generated_utc": utc_now(),
        "project": config.get("project", {}).get("name", project_root.name),
        "project_root": str(project_root) if bool(config.get("confidentiality", {}).get("store_absolute_paths", False)) else ".",
        "tree_fingerprint": tree_fingerprint(project_root, excludes, forge_root),
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "files": len(file_nodes),
            "subsystems": dict(sorted(subsystem_counts.items())),
            "types": dict(sorted(type_counts.items())),
            "low_confidence_subsystems": sum(1 for node in nodes if float(node.metadata.get("subsystem_confidence", 1.0)) < float(config.get("graph", {}).get("classification", {}).get("minimum_confidence", 0.55))),
        },
        "facts": {key: sorted(values) for key, values in facts.items()},
        "nodes": [node.as_dict() for node in sorted(nodes, key=lambda item: (item.type, item.path, item.name))],
        "edges": [edge.as_dict() for edge in sorted(edges, key=lambda item: (item.source, item.type, item.target))],
    }
    if write:
        graph_dir = project_root / config.get("graph", {}).get("output_dir", ".forge/graph")
        json_path = graph_dir / "project-graph.json"
        write_json(json_path, payload)
        _write_graph_markdown(graph_dir / "project-graph.md", payload)
    return payload


def _write_graph_markdown(path: Path, graph: dict[str, Any]) -> None:
    summary = graph["summary"]
    facts = graph["facts"]
    lines = [
        "# Forge Graph", "",
        f"- Project: {graph['project']}",
        f"- Generated: {graph['generated_utc']}",
        f"- Tree fingerprint: `{graph['tree_fingerprint']}`",
        f"- Nodes: {summary['nodes']}",
        f"- Edges: {summary['edges']}",
        f"- Low-confidence subsystem classifications: {summary.get('low_confidence_subsystems', 0)}", "",
        "## Subsystems", "",
    ]
    for name, count in summary["subsystems"].items():
        lines.append(f"- **{name}** — {count} node(s)")
    lines.extend(["", "## Architecture facts", ""])
    for key, values in facts.items():
        label = key.replace("_", " ").title()
        lines.append(f"### {label}")
        if values:
            lines.extend(f"- `{value}`" for value in values[:100])
        else:
            lines.append("- None detected")
        lines.append("")
    lines.extend(["## Important nodes", ""])
    important = [node for node in graph["nodes"] if node["type"] in {"entrypoint", "route", "migration", "webhook", "scheduled-job", "cli", "external-integration", "test", "tool-ecosystem", "tool-command", "generated-state", "bundled-product"}]
    for node in important[:200]:
        location = f" — `{node['path']}`" if node.get("path") else ""
        lines.append(f"- **{node['type']}**: {node['name']}{location} · {node['subsystem']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def load_graph(project_root: Path, config: dict[str, Any]) -> dict[str, Any] | None:
    path = project_root / config.get("graph", {}).get("output_dir", ".forge/graph") / "project-graph.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("schema") == 1 else None


def analyze_impact(project_root: Path, forge_root: Path, config: dict[str, Any], changed_paths: Iterable[str] | None = None, *, depth: int | None = None, write: bool = True) -> dict[str, Any]:
    graph = load_graph(project_root, config)
    graph_excludes = list(config.get("paths", {}).get("exclude", [])) + [".emotivus-forge.json", "FORGE-AGENT.md", ".deployignore"]
    current_fingerprint = tree_fingerprint(project_root, graph_excludes, forge_root)
    if graph is None or graph.get("tree_fingerprint") != current_fingerprint:
        graph = build_graph(project_root, forge_root, config, write=True)
    changed = [normalize_rel(item) for item in (changed_paths or []) if normalize_rel(item)]
    if not changed:
        changed = _git_changed(project_root)
    if not changed:
        raise RuntimeError("no changed paths were supplied and Git reported no changed files")
    depth = int(depth if depth is not None else config.get("graph", {}).get("impact_depth", 2))
    nodes = {node["id"]: node for node in graph["nodes"]}
    path_to_id = {node.get("path"): node["id"] for node in graph["nodes"] if node.get("path")}
    forward: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    edge_type: dict[tuple[str, str], str] = {}
    for edge in graph["edges"]:
        forward[edge["source"]].add(edge["target"])
        reverse[edge["target"]].add(edge["source"])
        edge_type[(edge["source"], edge["target"])] = edge["type"]

    seed_ids = {path_to_id[path] for path in changed if path in path_to_id}
    missing = sorted(path for path in changed if path not in path_to_id)
    impacted = set(seed_ids)
    queue = deque((node_id, 0) for node_id in seed_ids)
    reasons: dict[str, set[str]] = defaultdict(set)
    for node_id in seed_ids:
        reasons[node_id].add("changed directly")
    while queue:
        current, level = queue.popleft()
        if level >= depth:
            continue
        for neighbor in forward[current] | reverse[current]:
            if neighbor not in impacted:
                impacted.add(neighbor)
                queue.append((neighbor, level + 1))
            relation = edge_type.get((current, neighbor)) or edge_type.get((neighbor, current)) or "related"
            reasons[neighbor].add(f"{relation} within {level + 1} hop(s)")

    changed_subsystems = {nodes[node_id]["subsystem"] for node_id in seed_ids}
    for node_id, node in nodes.items():
        if node["subsystem"] in changed_subsystems and node["type"] in {"route", "test", "migration", "webhook", "scheduled-job", "external-integration"}:
            impacted.add(node_id)
            reasons[node_id].add("important node in changed subsystem")

    risk_weights = {
        "migration": 5, "authentication": 5, "authorization": 5, "payments": 5, "webhook": 4, "scheduled-job": 4,
        "external-integration": 4, "route": 3, "entrypoint": 3, "configuration": 3, "test": 0,
    }
    subsystem_weights = {"authentication": 4, "authorization": 5, "database": 4, "payments": 4, "integrations": 3, "scheduler": 3, "uploads": 3, "deployment": 3}
    score = 1
    for node_id in impacted:
        node = nodes[node_id]
        score += risk_weights.get(node["type"], 1)
        score += subsystem_weights.get(node["subsystem"], 0)
    score = min(100, score)
    risk = "critical" if score >= 45 else "high" if score >= 25 else "medium" if score >= 12 else "low"

    tests = sorted({node["path"] for node_id, node in nodes.items() if node_id in impacted and node["type"] == "test" and node.get("path")})
    live_checks: set[str] = set()
    for node_id in impacted:
        node = nodes[node_id]
        subsystem = node["subsystem"]
        kind = node["type"]
        if subsystem == "authentication": live_checks.add("authentication")
        if subsystem == "authorization": live_checks.add("authorization")
        if subsystem == "database" or kind == "migration": live_checks.add("database")
        if subsystem == "scheduler" or kind == "scheduled-job": live_checks.add("cron")
        if subsystem == "integrations" or kind in {"webhook", "external-integration"}: live_checks.add("api")
        if subsystem == "uploads": live_checks.add("uploads")
        if subsystem in {"frontend", "routing"} or kind in {"route", "entrypoint", "template", "style"}: live_checks.add("browser")
        if subsystem == "payments": live_checks.add("payments")

    certification_paths = set(config.get("packaging", {}).get("required_files", []))
    version_path = str(config.get("versioning", {}).get("source", {}).get("path", ""))
    certification_changed = sorted(path for path in changed if path in certification_paths or (version_path and path == version_path))
    subsystem_confidences = [float(nodes[node_id].get("metadata", {}).get("subsystem_confidence", 0.35)) for node_id in seed_ids]
    mean_confidence = round(sum(subsystem_confidences) / len(subsystem_confidences), 3) if subsystem_confidences else 0.0
    impact_axes = {
        "certification": {
            "level": "critical" if certification_changed else ("high" if risk in {"high", "critical"} else risk),
            "changed_certified_paths": certification_changed,
            "note": "Certification impact concerns release manifests and required artifacts; it is separate from runtime branch reach.",
        },
        "dependency_reach": {
            "level": risk,
            "direct_nodes": len(seed_ids),
            "impacted_nodes": len(impacted),
            "depth": depth,
        },
        "runtime_path": {
            "level": "unknown",
            "confidence": mean_confidence,
            "note": "File-level dependency evidence cannot prove which function or branch changed. Supply project-specific contracts or live journeys before treating dependency reach as runtime reach.",
        },
    }

    payload = {
        "schema": 2,
        "generated_utc": utc_now(),
        "project": graph["project"],
        "graph_fingerprint": graph["tree_fingerprint"],
        "changed_paths": changed,
        "unmapped_changed_paths": missing,
        "impact_depth": depth,
        "risk": {"level": risk, "score": score},
        "impact_axes": impact_axes,
        "changed_subsystems": sorted(changed_subsystems),
        "impacted_nodes": [
            {**nodes[node_id], "reasons": sorted(reasons[node_id])}
            for node_id in sorted(impacted, key=lambda value: (nodes[value]["type"], nodes[value].get("path", ""), nodes[value]["name"]))
        ],
        "targeted_tests": tests,
        "recommended_profiles": ["quick", "section"] + (["release"] if risk in {"high", "critical"} else []),
        "recommended_live_checks": sorted(live_checks),
    }
    if write:
        graph_dir = project_root / config.get("graph", {}).get("output_dir", ".forge/graph")
        write_json(graph_dir / "impact-report.json", payload)
        _write_impact_markdown(graph_dir / "impact-report.md", payload)
    return payload


def _write_impact_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Forge Graph Impact Report", "",
        f"- Risk: **{payload['risk']['level']}** ({payload['risk']['score']}/100)",
        f"- Certification impact: **{payload.get('impact_axes', {}).get('certification', {}).get('level', 'unknown')}**",
        f"- Dependency reach: **{payload.get('impact_axes', {}).get('dependency_reach', {}).get('level', 'unknown')}**",
        f"- Runtime path reach: **{payload.get('impact_axes', {}).get('runtime_path', {}).get('level', 'unknown')}**",
        f"- Depth: {payload['impact_depth']}",
        f"- Changed paths: {len(payload['changed_paths'])}",
        f"- Impacted nodes: {len(payload['impacted_nodes'])}", "",
        "## Changed paths", "",
    ]
    lines.extend(f"- `{path}`" for path in payload["changed_paths"])
    if payload["unmapped_changed_paths"]:
        lines.extend(["", "## Unmapped changed paths", ""])
        lines.extend(f"- `{path}`" for path in payload["unmapped_changed_paths"])
    lines.extend(["", "## Impacted systems", ""])
    for node in payload["impacted_nodes"][:250]:
        location = f" — `{node['path']}`" if node.get("path") else ""
        lines.append(f"- **{node['type']} / {node['subsystem']}**: {node['name']}{location} ({'; '.join(node['reasons'])})")
    lines.extend(["", "## Targeted tests", ""])
    lines.extend(f"- `{path}`" for path in payload["targeted_tests"]) if payload["targeted_tests"] else lines.append("- No directly linked test files were detected.")
    lines.extend(["", "## Live verification", ""])
    lines.extend(f"- [ ] {item}" for item in payload["recommended_live_checks"]) if payload["recommended_live_checks"] else lines.append("- No live checks inferred.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
