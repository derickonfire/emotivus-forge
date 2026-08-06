"""Per-instance signing identity for authority/provenance events.

The dominant deeper-gate finding ("self-consistent != authentic") is that Forge's
ledger is an unkeyed hash chain that travels inside a project's ``.forge``: anyone
who can author an imported package can rebuild a self-consistent chain and spoof an
authorization. The fix is a keyed signature whose secret lives OUTSIDE any project
tree — in a per-user Forge home — so an imported package cannot reproduce it.

An authorization event carries the *signer's* ``key_id`` and an HMAC ``signature``.
A verifying instance elevates a signature to "instance-bound" only when the
``key_id`` is one it trusts — its own always (peer enrollment is a later increment).
Because a victim instance trusts only its own key, and its secret is not in the
package, a replayed or fabricated event from another signer can never rise above
"self-consistent". See ``planning/DESIGN-instance-binding.md``.

Honest boundaries: this authenticates a key/instance, not a human, not review
quality, not correctness. A stolen home secret (full machine compromise) defeats it.
When the home is unavailable (read-only environment), signing degrades to unsigned —
never silently "instance-bound".
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any, Optional


def instance_home() -> Path:
    """Per-user Forge home, outside any project tree. Overridable for isolation/tests."""
    override = os.environ.get("FORGE_HOME", "").strip()
    if override:
        return Path(override)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if home:
        return Path(home) / ".config" / "emotivus-forge"
    import tempfile

    return Path(tempfile.gettempdir()) / "emotivus-forge-home"


def _key_file() -> Path:
    return instance_home() / "keys" / "instance.json"


def load_instance_identity() -> Optional[dict[str, str]]:
    """Return {'key_id', 'secret'} if a stored identity is readable, else None."""
    path = _key_file()
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    if isinstance(data, dict) and str(data.get("key_id", "")) and str(data.get("secret", "")):
        return {"key_id": str(data["key_id"]), "secret": str(data["secret"])}
    return None


def get_or_create_instance_identity() -> Optional[dict[str, str]]:
    """Load the per-instance identity, creating one if the home is writable.

    Returns None when no identity exists and the home cannot be written (read-only
    environment) — the caller then records an unsigned event and never claims
    instance-binding.
    """
    existing = load_instance_identity()
    if existing:
        return existing
    secret = secrets.token_hex(32)
    key_id = hashlib.sha256(f"forge-instance-key:{secret}".encode("utf-8")).hexdigest()[:16]
    path = _key_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"key_id": key_id, "secret": secret}, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return {"key_id": key_id, "secret": secret}
    except OSError:
        return None


def sign_message(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def trusted_key_ids() -> set[str]:
    """Key ids whose signatures this instance will elevate to instance-bound.

    Always includes this instance's own key. Owner-enrolled collaboration peers are a
    later increment (they require an out-of-band provisioning decision).
    """
    identity = load_instance_identity()
    return {identity["key_id"]} if identity else set()


def classify_signature(message: str, key_id: str, signature: str) -> str:
    """Return 'instance-bound' when the signature verifies against a trusted key.

    Any missing/invalid signature, or a valid signature from an untrusted (e.g.
    imported/foreign) key, is NOT instance-bound.
    """
    if not key_id or not signature:
        return "unsigned"
    identity = load_instance_identity()
    if identity and key_id == identity["key_id"]:
        if hmac.compare_digest(sign_message(identity["secret"], message), signature):
            return "instance-bound"
        return "invalid-signature"
    return "untrusted-signer"
