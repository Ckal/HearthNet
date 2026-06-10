"""Prekey bundle storage for HearthNet E2E encryption (M23)."""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

from hearthnet.crypto import CryptoError
from hearthnet.crypto.kem import PrekeyBundle, X25519KeyPair


def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


# ---------------------------------------------------------------------------
# PrekeyStore
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prekey_bundles (
    id INTEGER PRIMARY KEY,
    bundle_json TEXT NOT NULL,
    private_keys_json TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS one_time_prekeys (
    pub_key_b64 TEXT PRIMARY KEY,
    private_key_b64 TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);
"""


class PrekeyStore:
    """Persistent store for prekey bundles backed by SQLite."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Bundle persistence
    # ------------------------------------------------------------------

    def store_bundle(
        self,
        bundle: PrekeyBundle,
        signed_prekey_kp: X25519KeyPair,
        otp_kps: list[X25519KeyPair],
    ) -> None:
        """Persist the full bundle (public) and private key halves."""
        bundle_dict = {
            "identity_key_pub": _b64url_encode(bundle.identity_key_pub),
            "signed_prekey_pub": _b64url_encode(bundle.signed_prekey_pub),
            "signed_prekey_sig": _b64url_encode(bundle.signed_prekey_sig),
            "one_time_prekeys": bundle.one_time_prekeys,
            "published_at": bundle.published_at,
        }
        private_dict = {
            "signed_prekey_priv": _b64url_encode(signed_prekey_kp.private),
        }
        with self._conn:
            self._conn.execute(
                "DELETE FROM prekey_bundles",
            )
            self._conn.execute(
                "INSERT INTO prekey_bundles (bundle_json, private_keys_json) VALUES (?, ?)",
                (json.dumps(bundle_dict), json.dumps(private_dict)),
            )
            # Store one-time prekeys
            for kp in otp_kps:
                self._conn.execute(
                    "INSERT OR REPLACE INTO one_time_prekeys (pub_key_b64, private_key_b64) "
                    "VALUES (?, ?)",
                    (_b64url_encode(kp.public), _b64url_encode(kp.private)),
                )

    def load_bundle(self) -> tuple[PrekeyBundle, dict]:
        """Load the stored bundle and private key map.

        Returns (PrekeyBundle, private_keys_dict) where private_keys_dict has
        'signed_prekey_priv' as a base64url string.
        Raises CryptoError if no bundle is stored.
        """
        row = self._conn.execute(
            "SELECT bundle_json, private_keys_json FROM prekey_bundles ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise CryptoError("No prekey bundle stored")
        bundle_dict = json.loads(row[0])
        private_dict = json.loads(row[1])
        # Rebuild one_time_prekeys from the active (unused) OTPs stored in the DB
        otp_rows = self._conn.execute(
            "SELECT pub_key_b64 FROM one_time_prekeys WHERE used = 0"
        ).fetchall()
        active_otps = [r[0] for r in otp_rows]
        bundle = PrekeyBundle(
            identity_key_pub=_b64url_decode(bundle_dict["identity_key_pub"]),
            signed_prekey_pub=_b64url_decode(bundle_dict["signed_prekey_pub"]),
            signed_prekey_sig=_b64url_decode(bundle_dict["signed_prekey_sig"]),
            one_time_prekeys=active_otps,
            published_at=bundle_dict["published_at"],
        )
        return bundle, private_dict

    def consume_one_time_prekey(self, pub_key_b64: str) -> X25519KeyPair | None:
        """Mark a one-time prekey as used and return its key pair.

        Returns None if the key does not exist or was already consumed.
        """
        row = self._conn.execute(
            "SELECT private_key_b64 FROM one_time_prekeys WHERE pub_key_b64 = ? AND used = 0",
            (pub_key_b64,),
        ).fetchone()
        if row is None:
            return None
        with self._conn:
            self._conn.execute(
                "UPDATE one_time_prekeys SET used = 1 WHERE pub_key_b64 = ?",
                (pub_key_b64,),
            )
        priv = _b64url_decode(row[0])
        pub = _b64url_decode(pub_key_b64)
        return X25519KeyPair(private=priv, public=pub)
