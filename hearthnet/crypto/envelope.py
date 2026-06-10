"""File-chunk envelope encryption for HearthNet blobs (M23 / M07 extension)."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from hearthnet.crypto import CryptoError

try:
    import nacl.secret
    import nacl.utils

    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NACL_AVAILABLE = False


def _require_nacl() -> None:
    if not _NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for envelope encryption. Install it with: pip install pynacl"
        )


# ---------------------------------------------------------------------------
# HKDF helper (local copy to keep this module self-contained)
# ---------------------------------------------------------------------------


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    if not salt:
        salt = b"\x00" * 32
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    t = b""
    okm = b""
    i = 0
    while len(okm) < length:
        i += 1
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
    return okm[:length]


# ---------------------------------------------------------------------------
# EncryptedEnvelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EncryptedEnvelope:
    """An encrypted blob chunk with metadata."""

    ciphertext: bytes
    nonce: bytes  # 24 bytes (XSalsa20 nonce)
    key_id: str   # identifies which key was used (e.g., recipient node_id or blob CID)


# ---------------------------------------------------------------------------
# Envelope encrypt / decrypt
# ---------------------------------------------------------------------------


def envelope_encrypt(plaintext: bytes, key: bytes) -> EncryptedEnvelope:
    """Encrypt plaintext with XSalsa20-Poly1305 using the given 32-byte key."""
    _require_nacl()
    if len(key) != nacl.secret.SecretBox.KEY_SIZE:
        raise CryptoError(
            f"Key must be {nacl.secret.SecretBox.KEY_SIZE} bytes, got {len(key)}"
        )
    box = nacl.secret.SecretBox(key)
    nonce = nacl.utils.random(nacl.secret.SecretBox.NONCE_SIZE)
    ciphertext = bytes(box.encrypt(plaintext, nonce).ciphertext)
    return EncryptedEnvelope(ciphertext=ciphertext, nonce=nonce, key_id="")


def envelope_decrypt(envelope: EncryptedEnvelope, key: bytes) -> bytes:
    """Decrypt an EncryptedEnvelope using the given 32-byte key."""
    _require_nacl()
    if len(key) != nacl.secret.SecretBox.KEY_SIZE:
        raise CryptoError(
            f"Key must be {nacl.secret.SecretBox.KEY_SIZE} bytes, got {len(key)}"
        )
    box = nacl.secret.SecretBox(key)
    try:
        return bytes(box.decrypt(envelope.ciphertext, envelope.nonce))
    except Exception as exc:
        raise CryptoError(f"Envelope decryption failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Per-recipient key derivation
# ---------------------------------------------------------------------------


def per_recipient_key(shared_secret: bytes, recipient_id: str, blob_cid: str) -> bytes:
    """Derive a 32-byte per-recipient encryption key via HKDF-SHA256.

    Binds the key to the recipient identity and the specific blob CID so that
    a key derived for one blob cannot decrypt another.
    """
    info = f"HearthNet_BlobKey_v1:{recipient_id}:{blob_cid}".encode()
    return _hkdf_sha256(shared_secret, salt=b"HearthNet_envelope", info=info, length=32)
