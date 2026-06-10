"""Double Ratchet session for HearthNet E2E encryption (M23)."""
from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass, field

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
            "PyNaCl is required for the Double Ratchet. Install it with: pip install pynacl"
        )


# ---------------------------------------------------------------------------
# Internal KDF helpers
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


def _kdf_chain(chain_key: bytes) -> tuple[bytes, bytes]:
    """Advance the symmetric chain. Returns (message_key, next_chain_key)."""
    msg_key = hmac.new(chain_key, b"\x01", hashlib.sha256).digest()
    next_ck = hmac.new(chain_key, b"\x02", hashlib.sha256).digest()
    return msg_key, next_ck


def _kdf_root_key(root_key: bytes, dh_out: bytes) -> tuple[bytes, bytes]:
    """KDF_RK: returns (new_root_key, new_chain_key) from root_key + DH output."""
    kdf_out = _hkdf_sha256(dh_out, salt=root_key, info=b"HearthNet_RK_v1", length=64)
    return kdf_out[:32], kdf_out[32:]


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _secretbox_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """Encrypt plaintext with XSalsa20-Poly1305. Returns nonce+ciphertext."""
    box = nacl.secret.SecretBox(key)
    return bytes(box.encrypt(plaintext))


def _secretbox_decrypt(key: bytes, data: bytes) -> bytes:
    """Decrypt nonce+ciphertext with XSalsa20-Poly1305."""
    box = nacl.secret.SecretBox(key)
    try:
        return bytes(box.decrypt(data))
    except Exception as exc:
        raise CryptoError(f"Ratchet decryption failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Ratchet session state
# ---------------------------------------------------------------------------

_MAX_SKIP = 100  # Safety cap on how many messages can be skipped


@dataclass
class RatchetSession:
    """Bidirectional Double Ratchet session between two nodes."""

    peer_node_id_full: str
    root_key: bytes
    chain_key: bytes  # send chain key
    recv_chain_key: bytes  # receive chain key
    message_keys: dict[tuple[int, int], bytes] = field(default_factory=dict)
    send_counter: int = 0
    recv_counter: int = 0
    epoch: int = 0  # DH ratchet step index

    # X25519 ratchet keys (stored as raw bytes)
    ratchet_priv: bytes | None = None  # our current DH ratchet private key
    ratchet_pub: bytes | None = None  # our current DH ratchet public key
    remote_ratchet_pub: bytes | None = None  # peer's current DH ratchet public key

    # Set to True for the responder (Bob): the first receive must NOT trigger a
    # DH ratchet step because the initial recv_chain_key is already established
    # from X3DH. The DH ratchet only fires when epoch in the header advances.
    is_initiator: bool = True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_from_shared_secret(
    shared_secret: bytes,
    is_initiator: bool,
    peer_node_id_full: str = "",
) -> RatchetSession:
    """Initialise a new ratchet session from an X3DH shared secret."""
    _require_nacl()

    from hearthnet.crypto.kem import x25519_generate

    root_key = _hkdf_sha256(
        shared_secret,
        salt=b"HearthNet_X3DH",
        info=b"RootKey_v1",
        length=32,
    )
    info_send = b"InitiatorChain_v1" if is_initiator else b"ResponderChain_v1"
    info_recv = b"ResponderChain_v1" if is_initiator else b"InitiatorChain_v1"
    chain_key = _hkdf_sha256(root_key, salt=b"", info=info_send, length=32)
    recv_chain_key = _hkdf_sha256(root_key, salt=b"", info=info_recv, length=32)

    ratchet_kp = x25519_generate()
    return RatchetSession(
        peer_node_id_full=peer_node_id_full,
        root_key=root_key,
        chain_key=chain_key,
        recv_chain_key=recv_chain_key,
        ratchet_priv=ratchet_kp.private,
        ratchet_pub=ratchet_kp.public,
        is_initiator=is_initiator,
    )


def _dh_ratchet_step(session: RatchetSession, new_remote_ratchet_pub: bytes) -> None:
    """Perform a DH ratchet step on receiving a new remote ratchet public key."""
    from hearthnet.crypto.kem import x25519_dh, x25519_generate

    assert session.ratchet_priv is not None

    # Step 1: derive new recv chain key from DH(our_current, their_new)
    dh1 = x25519_dh(session.ratchet_priv, new_remote_ratchet_pub)
    root_key, recv_chain_key = _kdf_root_key(session.root_key, dh1)

    # Step 2: generate new DH ratchet keypair
    new_kp = x25519_generate()

    # Step 3: derive new send chain key from DH(our_new, their_new)
    dh2 = x25519_dh(new_kp.private, new_remote_ratchet_pub)
    root_key2, send_chain_key = _kdf_root_key(root_key, dh2)

    # Mutate session state
    session.root_key = root_key2
    session.chain_key = send_chain_key
    session.recv_chain_key = recv_chain_key
    session.remote_ratchet_pub = new_remote_ratchet_pub
    session.ratchet_priv = new_kp.private
    session.ratchet_pub = new_kp.public
    session.epoch += 1
    session.send_counter = 0
    session.recv_counter = 0


def encrypt(session: RatchetSession, plaintext: bytes) -> tuple[bytes, dict]:
    """Encrypt a message. Returns (ciphertext, header).

    header contains: ratchet_pub (b64url), index, epoch.
    """
    _require_nacl()

    msg_key, next_ck = _kdf_chain(session.chain_key)
    session.chain_key = next_ck
    counter = session.send_counter
    session.send_counter += 1

    ciphertext = _secretbox_encrypt(msg_key, plaintext)

    header = {
        "ratchet_pub": _b64url_encode(session.ratchet_pub or b"\x00" * 32),
        "index": counter,
        "epoch": session.epoch,
    }
    return ciphertext, header


def decrypt(session: RatchetSession, ciphertext: bytes, header: dict) -> bytes:
    """Decrypt a message using ratchet state. Handles out-of-order messages (limited)."""
    _require_nacl()

    ratchet_pub = _b64url_decode(header["ratchet_pub"])
    index: int = header["index"]
    epoch: int = header["epoch"]

    # Check the skipped-message cache first
    cached_key = session.message_keys.pop((epoch, index), None)
    if cached_key is not None:
        return _secretbox_decrypt(cached_key, ciphertext)

    # DH ratchet step rules:
    # - Initiator's first decrypt: remote_ratchet_pub is None but epoch==0
    #   means the responder is starting their first reply — do the DH step.
    # - Responder's first decrypt (epoch==0): the initial recv_chain_key is
    #   already set from X3DH; just record the peer's ratchet pub, no DH step.
    # - Any subsequent epoch mismatch: always do the DH step.
    if ratchet_pub != session.remote_ratchet_pub:
        if session.remote_ratchet_pub is None and not session.is_initiator and epoch == 0:
            # Responder receiving initiator's first message — use pre-computed
            # recv_chain_key as-is; just record the initiator's ratchet pub.
            session.remote_ratchet_pub = ratchet_pub
        else:
            _dh_ratchet_step(session, ratchet_pub)

    # Advance recv chain to the target counter, caching skipped keys
    skipped = 0
    while session.recv_counter < index:
        if skipped >= _MAX_SKIP:
            raise CryptoError("Too many skipped messages in ratchet")
        msg_key, next_ck = _kdf_chain(session.recv_chain_key)
        session.recv_chain_key = next_ck
        session.message_keys[(session.epoch, session.recv_counter)] = msg_key
        session.recv_counter += 1
        skipped += 1

    msg_key, next_ck = _kdf_chain(session.recv_chain_key)
    session.recv_chain_key = next_ck
    session.recv_counter += 1

    return _secretbox_decrypt(msg_key, ciphertext)
