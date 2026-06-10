"""X25519 key agreement + X3DH for HearthNet E2E encryption (M23)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hearthnet.crypto import CryptoError

if TYPE_CHECKING:
    from hearthnet.identity.keys import KeyPair

try:
    import nacl.bindings
    import nacl.public
    import nacl.signing

    _NACL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _NACL_AVAILABLE = False


def _require_nacl() -> None:
    if not _NACL_AVAILABLE:
        raise ImportError(
            "PyNaCl is required for E2E encryption. Install it with: pip install pynacl"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _hkdf_sha256(ikm: bytes, salt: bytes, info: bytes, length: int) -> bytes:
    """HKDF-SHA256 (RFC 5869)."""
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
# X25519 key types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class X25519KeyPair:
    """An X25519 Diffie-Hellman key pair."""

    private: bytes  # 32 bytes
    public: bytes  # 32 bytes


# ---------------------------------------------------------------------------
# X25519 primitives
# ---------------------------------------------------------------------------


def x25519_generate() -> X25519KeyPair:
    """Generate a random X25519 key pair using PyNaCl."""
    _require_nacl()
    priv_key = nacl.public.PrivateKey.generate()
    return X25519KeyPair(
        private=bytes(priv_key),
        public=bytes(priv_key.public_key),
    )


def x25519_dh(our_priv: bytes, their_pub: bytes) -> bytes:
    """Compute the X25519 Diffie-Hellman shared secret (32 bytes)."""
    _require_nacl()
    if len(our_priv) != 32:
        raise CryptoError(f"Expected 32-byte private key, got {len(our_priv)}")
    if len(their_pub) != 32:
        raise CryptoError(f"Expected 32-byte public key, got {len(their_pub)}")
    try:
        return nacl.bindings.crypto_scalarmult(our_priv, their_pub)
    except Exception as exc:
        raise CryptoError(f"X25519 DH failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Ed25519 → X25519 conversion
# ---------------------------------------------------------------------------


def derive_identity_x25519_from_ed25519(ed_kp: KeyPair) -> X25519KeyPair:
    """Convert an Ed25519 signing key to X25519 using the standard nacl Elligator conversion."""
    _require_nacl()
    # Reconstruct the 64-byte Ed25519 secret key (seed || verify_key) via re-deriving
    seed = bytes(ed_kp.signing_key)  # 32-byte seed
    _vk_bytes, sk_64 = nacl.bindings.crypto_sign_seed_keypair(seed)
    x25519_priv = nacl.bindings.crypto_sign_ed25519_sk_to_curve25519(sk_64)
    x25519_pub = nacl.bindings.crypto_sign_ed25519_pk_to_curve25519(bytes(ed_kp.verify_key))
    return X25519KeyPair(private=x25519_priv, public=x25519_pub)


# ---------------------------------------------------------------------------
# Prekey bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrekeyBundle:
    """What a recipient publishes so senders can establish a session without them online."""

    identity_key_pub: bytes  # 32 bytes (X25519 public key derived from Ed25519 identity)
    signed_prekey_pub: bytes  # 32 bytes
    signed_prekey_sig: bytes  # 64 bytes (Ed25519 signature over signed_prekey_pub)
    one_time_prekeys: list[str]  # base64url-encoded 32-byte X25519 public keys
    published_at: int  # unix seconds


def build_prekey_bundle(
    ed_kp: KeyPair,
    num_one_time: int = 10,
) -> tuple[PrekeyBundle, X25519KeyPair, list[X25519KeyPair]]:
    """Build a prekey bundle from an Ed25519 identity key pair.

    Returns (bundle, signed_prekey_full, one_time_prekeys_full).
    Caller persists the private halves; publishes only the bundle.
    """
    _require_nacl()

    # Identity X25519 key (derived from Ed25519)
    identity_x = derive_identity_x25519_from_ed25519(ed_kp)

    # Signed prekey
    signed_prekey_kp = x25519_generate()

    # Sign the signed_prekey_pub with the Ed25519 identity key
    try:
        signed_msg = ed_kp.signing_key.sign(signed_prekey_kp.public)
        signed_prekey_sig = signed_msg.signature  # 64 bytes
    except Exception as exc:
        raise CryptoError(f"Failed to sign prekey: {exc}") from exc

    # One-time prekeys
    otp_kps: list[X25519KeyPair] = [x25519_generate() for _ in range(num_one_time)]
    otp_pubs = [_b64url_encode(kp.public) for kp in otp_kps]

    bundle = PrekeyBundle(
        identity_key_pub=identity_x.public,
        signed_prekey_pub=signed_prekey_kp.public,
        signed_prekey_sig=bytes(signed_prekey_sig),
        one_time_prekeys=otp_pubs,
        published_at=int(time.time()),
    )
    return bundle, signed_prekey_kp, otp_kps


# ---------------------------------------------------------------------------
# X3DH key agreement
# ---------------------------------------------------------------------------

_X3DH_F = b"\xff" * 32  # Fixed padding as per Signal spec


def _x3dh_kdf(*dh_outputs: bytes) -> bytes:
    """KDF over concatenated DH outputs → 32-byte shared secret."""
    ikm = _X3DH_F + b"".join(dh_outputs)
    return _hkdf_sha256(ikm, salt=b"HearthNet_X3DH_v1", info=b"HearthNet_X3DH_v1", length=32)


def x3dh_initiator(
    our_identity_x: X25519KeyPair,
    our_ephemeral_kp: X25519KeyPair,
    their_bundle: PrekeyBundle,
) -> tuple[bytes, dict]:
    """X3DH from the initiator's side.

    Returns (shared_secret_32bytes, session_init_message).
    session_init_message carries public material needed for the responder.
    """
    _require_nacl()

    # DH1 = DH(IK_a, SPK_b)
    dh1 = x25519_dh(our_identity_x.private, their_bundle.signed_prekey_pub)
    # DH2 = DH(EK_a, IK_b)
    dh2 = x25519_dh(our_ephemeral_kp.private, their_bundle.identity_key_pub)
    # DH3 = DH(EK_a, SPK_b)
    dh3 = x25519_dh(our_ephemeral_kp.private, their_bundle.signed_prekey_pub)

    # Optional: DH4 = DH(EK_a, OTP_b)
    used_otp_index: int | None = None
    dh_outputs = [dh1, dh2, dh3]
    if their_bundle.one_time_prekeys:
        used_otp_index = 0
        otp_pub_bytes = _b64url_decode(their_bundle.one_time_prekeys[0])
        dh4 = x25519_dh(our_ephemeral_kp.private, otp_pub_bytes)
        dh_outputs.append(dh4)

    shared_secret = _x3dh_kdf(*dh_outputs)

    session_init_message = {
        "identity_pub": _b64url_encode(our_identity_x.public),
        "ephemeral_pub": _b64url_encode(our_ephemeral_kp.public),
        "signed_prekey_pub": _b64url_encode(their_bundle.signed_prekey_pub),
        "used_otp_index": used_otp_index,
        "used_otp_pub": (
            their_bundle.one_time_prekeys[0] if used_otp_index is not None else None
        ),
    }
    return shared_secret, session_init_message


def x3dh_responder(
    our_identity_x: X25519KeyPair,
    our_signed_prekey: X25519KeyPair,
    used_one_time_prekey: X25519KeyPair | None,
    their_ephemeral_pub: bytes,
    their_identity_pub: bytes,
) -> bytes:
    """X3DH from the responder's side. Returns the shared secret (32 bytes)."""
    _require_nacl()

    # DH1 = DH(SPK_b, IK_a)
    dh1 = x25519_dh(our_signed_prekey.private, their_identity_pub)
    # DH2 = DH(IK_b, EK_a)
    dh2 = x25519_dh(our_identity_x.private, their_ephemeral_pub)
    # DH3 = DH(SPK_b, EK_a)
    dh3 = x25519_dh(our_signed_prekey.private, their_ephemeral_pub)

    # Optional: DH4 = DH(OTP_b, EK_a)
    dh_outputs = [dh1, dh2, dh3]
    if used_one_time_prekey is not None:
        dh4 = x25519_dh(used_one_time_prekey.private, their_ephemeral_pub)
        dh_outputs.append(dh4)

    return _x3dh_kdf(*dh_outputs)
