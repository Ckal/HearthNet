"""M01 - Node identity: Ed25519 key management.

Spec: docs/M01-identity.md §3.1
Impl-ref: impl_ref.md §5

Keys stored in keys_dir (default ~/.hearthnet/keys/).
Sign/verify via PyNaCl Ed25519. canonical_json() for deterministic signing.
"""

from __future__ import annotations

import base64
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import nacl.exceptions
    import nacl.signing

    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NACL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

NodeID = str  # "ed25519:XXXX-XXXX-XXXX-XXXX" (short) or "ed25519:<b64url>" (full)
Signature = str  # "ed25519:<b64url>"


class IdentityError(Exception):
    """Raised for all identity-layer failures."""

    def __init__(self, code: str, reason: str = "") -> None:
        super().__init__(reason or code)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class KeyPair:
    signing_key: Any  # nacl.signing.SigningKey
    verify_key: Any  # nacl.signing.VerifyKey
    node_id_short: str
    node_id_full: str


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------


def short_node_id(verify_key_bytes: bytes) -> str:
    """First 8 bytes base32, grouped in 4-char segments: 'ed25519:XXXX-XXXX-XXXX-XXXX'."""
    raw = base64.b32encode(verify_key_bytes[:8]).decode("ascii")
    grouped = "-".join(raw[i : i + 4] for i in range(0, len(raw), 4))
    return f"ed25519:{grouped}"


def full_node_id(verify_key_bytes: bytes) -> str:
    """All 32 bytes base64url no-pad: 'ed25519:<b64>'."""
    b64 = base64.urlsafe_b64encode(verify_key_bytes).rstrip(b"=").decode("ascii")
    return f"ed25519:{b64}"


def parse_node_id(node_id: str) -> bytes:
    """Decode a full node_id to 32 bytes. Short form raises ValueError."""
    import re

    if not node_id.startswith("ed25519:"):
        raise ValueError(f"node_id must start with 'ed25519:': {node_id!r}")
    payload = node_id[len("ed25519:") :]
    # Short form is b32-with-dashes: groups of [A-Z2-7=]{1,4} separated by '-'
    # e.g. "SQ2J-OH7E-LCMU-Y===" â€” always shorter than 30 chars and matches this pattern.
    # Full form is 43-char base64url (no '=' padding).
    if re.fullmatch(r"[A-Z2-7=]{1,4}(-[A-Z2-7=]{1,4}){1,}", payload):
        raise ValueError("Short node IDs cannot be decoded to raw bytes; use full form.")
    # Add padding back for base64url decoding
    padded = payload + "=" * (4 - len(payload) % 4 if len(payload) % 4 != 0 else 0)
    raw = base64.urlsafe_b64decode(padded)
    if len(raw) != 32:
        raise ValueError(f"Expected 32 bytes, got {len(raw)}")
    return raw


# ---------------------------------------------------------------------------
# Canonical JSON
# ---------------------------------------------------------------------------


def canonical_json(obj: Any) -> bytes:
    """Canonical JSON: sorted keys, no whitespace, numbers stripped of trailing zeros, UTF-8."""
    serialised = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # Strip trailing zeros from numbers: 1.0 -> 1, 1.10 -> 1.1
    # We post-process the JSON string carefully without breaking string contents.
    result = _strip_trailing_zeros(serialised)
    return result.encode("utf-8")


def _strip_trailing_zeros(s: str) -> str:
    """Remove trailing zeros from JSON numbers without touching string values."""
    import re

    # Match JSON numbers (integers, floats, exponent forms) that appear outside strings
    # We parse character-by-character to skip string literals.
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '"':
            # Scan to end of string, respecting escapes
            out.append(c)
            i += 1
            while i < n:
                ch = s[i]
                out.append(ch)
                if ch == "\\":
                    i += 1
                    if i < n:
                        out.append(s[i])
                elif ch == '"':
                    i += 1
                    break
                i += 1
        else:
            # Look for a number token
            m = re.match(r"-?(?:0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?", s[i:])
            if m and (m.group(1) or m.group(2)):
                num_str = m.group(0)
                # Parse and reformat
                try:
                    val = float(num_str)
                    # If it represents an integer value, emit as integer
                    if val == int(val) and "e" not in num_str.lower():
                        out.append(str(int(val)))
                    else:
                        # Strip trailing zeros from decimal part
                        formatted = f"{val:g}"
                        out.append(formatted)
                except (ValueError, OverflowError):
                    out.append(num_str)
                i += len(num_str)
            else:
                out.append(c)
                i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Signing / Verification
# ---------------------------------------------------------------------------


def sign_payload(payload: dict, kp: KeyPair) -> dict:
    """Return a copy of payload with 'signature' field added (signs over payload without signature)."""
    if not _NACL_AVAILABLE:
        raise IdentityError("keys_invalid", reason="PyNaCl not installed")
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    raw = canonical_json(unsigned)
    try:
        signed = kp.signing_key.sign(raw)
        sig_bytes = signed.signature
    except Exception as exc:
        raise IdentityError("sign_failed", reason=str(exc)) from exc
    sig_b64 = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode("ascii")
    result = dict(unsigned)
    result["signature"] = f"ed25519:{sig_b64}"
    return result


def verify_payload(payload: dict, vk: Any) -> bool:  # vk: nacl.signing.VerifyKey
    """Verify the 'signature' field of payload against vk. Returns True or raises IdentityError."""
    if not _NACL_AVAILABLE:
        raise IdentityError("keys_invalid", reason="PyNaCl not installed")
    raw_sig = payload.get("signature", "")
    if not raw_sig.startswith("ed25519:"):
        raise IdentityError("verify_failed", reason="signature field missing or malformed")
    sig_b64 = raw_sig[len("ed25519:") :]
    padding = 4 - len(sig_b64) % 4
    if padding != 4:
        sig_b64 += "=" * padding
    try:
        sig_bytes = base64.urlsafe_b64decode(sig_b64)
    except Exception as exc:
        raise IdentityError("verify_failed", reason=f"bad signature encoding: {exc}") from exc
    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    raw = canonical_json(unsigned)
    try:
        vk.verify(raw, sig_bytes)
    except nacl.exceptions.BadSignatureError as exc:
        raise IdentityError("verify_failed", reason="signature verification failed") from exc
    except Exception as exc:
        raise IdentityError("verify_failed", reason=str(exc)) from exc
    return True


def verify_payload_with_node_id(payload: dict, expected_node_id_full: str) -> bool:
    """Verify payload signature using the public key encoded in expected_node_id_full."""
    if not _NACL_AVAILABLE:
        raise IdentityError("keys_invalid", reason="PyNaCl not installed")
    try:
        vk_bytes = parse_node_id(expected_node_id_full)
    except ValueError as exc:
        raise IdentityError("bad_node_id", reason=str(exc)) from exc
    try:
        vk = nacl.signing.VerifyKey(vk_bytes)
    except Exception as exc:
        raise IdentityError("keys_invalid", reason=str(exc)) from exc
    return verify_payload(payload, vk)


# ---------------------------------------------------------------------------
# Key I/O
# ---------------------------------------------------------------------------


def generate() -> KeyPair:
    """Generate a fresh Ed25519 keypair using os.urandom."""
    if not _NACL_AVAILABLE:
        raise IdentityError("keys_invalid", reason="PyNaCl not installed")
    seed = os.urandom(32)
    sk = nacl.signing.SigningKey(seed)
    vk = sk.verify_key
    vk_bytes = bytes(vk)
    return KeyPair(
        signing_key=sk,
        verify_key=vk,
        node_id_short=short_node_id(vk_bytes),
        node_id_full=full_node_id(vk_bytes),
    )


def save(kp: KeyPair, keys_dir: Path) -> None:
    """Save signing key (chmod 0600) and verify key to keys_dir."""
    keys_dir.mkdir(parents=True, exist_ok=True)
    priv_path = keys_dir / "device.ed25519"
    pub_path = keys_dir / "device.pub"
    # Write private key (raw 32-byte seed, base64url encoded)
    sk_bytes = bytes(kp.signing_key)
    priv_path.write_bytes(base64.urlsafe_b64encode(sk_bytes).rstrip(b"=") + b"\n")
    # Restrict permissions on POSIX
    try:
        os.chmod(priv_path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except AttributeError:
        pass  # Windows: chmod semantics differ; best-effort
    # Write public key
    vk_bytes = bytes(kp.verify_key)
    pub_path.write_bytes(base64.urlsafe_b64encode(vk_bytes).rstrip(b"=") + b"\n")


def load(keys_dir: Path) -> KeyPair:
    """Load KeyPair from device.ed25519 + device.pub in keys_dir."""
    if not _NACL_AVAILABLE:
        raise IdentityError("keys_invalid", reason="PyNaCl not installed")
    priv_path = keys_dir / "device.ed25519"
    pub_path = keys_dir / "device.pub"
    if not priv_path.exists() or not pub_path.exists():
        raise IdentityError("keys_missing", reason=f"Key files not found in {keys_dir}")
    # Check permissions on POSIX
    try:
        mode = oct(stat.S_IMODE(priv_path.stat().st_mode))
        if not mode.endswith("600") and not mode.endswith("400"):
            raise IdentityError(
                "keys_permissions",
                reason=f"Private key {priv_path} has unsafe permissions {mode}",
            )
    except AttributeError:
        pass  # Windows
    try:
        sk_b64 = priv_path.read_text().strip()
        padding = 4 - len(sk_b64) % 4
        if padding != 4:
            sk_b64 += "=" * padding
        sk_bytes = base64.urlsafe_b64decode(sk_b64)
        sk = nacl.signing.SigningKey(sk_bytes)
    except IdentityError:
        raise
    except Exception as exc:
        raise IdentityError("keys_invalid", reason=str(exc)) from exc
    vk = sk.verify_key
    vk_bytes = bytes(vk)
    return KeyPair(
        signing_key=sk,
        verify_key=vk,
        node_id_short=short_node_id(vk_bytes),
        node_id_full=full_node_id(vk_bytes),
    )


def load_or_generate(keys_dir: Path) -> KeyPair:
    """Load keys if present, otherwise generate and persist."""
    priv_path = keys_dir / "device.ed25519"
    if priv_path.exists():
        return load(keys_dir)
    kp = generate()
    save(kp, keys_dir)
    return kp
