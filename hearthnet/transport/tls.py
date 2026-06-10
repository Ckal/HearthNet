"""TLS certificate generation and peer cert pinning."""

from __future__ import annotations

import json
from pathlib import Path


class PinnedCerts:
    """Stores first-seen TLS cert fingerprint per NodeID."""

    def __init__(self, store_path: Path):
        self._path = store_path
        self._pins: dict[str, str] = {}
        self._load()

    def pin(self, node_id: str, cert_fingerprint: str) -> None:
        if node_id not in self._pins:
            self._pins[node_id] = cert_fingerprint
            self._save()

    def verify(self, node_id: str, presented_fingerprint: str) -> bool:
        expected = self._pins.get(node_id)
        if expected is None:
            self.pin(node_id, presented_fingerprint)
            return True
        return expected == presented_fingerprint

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._pins = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception:
                self._pins = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._pins), encoding="utf-8")


def generate_self_signed_cert(node_id: str, host: str = "0.0.0.0") -> tuple[bytes, bytes]:
    """Generate self-signed X.509 cert+key. Returns (cert_pem, key_pem).

    Uses cryptography library if available, else returns empty bytes
    (no TLS in dev mode).
    """
    try:
        import datetime

        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        cn = f"{node_id[:16]}.hearthnet.local"
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, cn),
            ]
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(cn)]),
                critical=False,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        return cert_pem, key_pem
    except ImportError:
        return b"", b""


def load_or_generate_cert(
    cert_path: Path,
    key_path: Path,
    node_id: str,
) -> tuple[Path, Path]:
    """Load existing cert/key, or generate and save if missing."""
    if not cert_path.exists() or not key_path.exists():
        cert_pem, key_pem = generate_self_signed_cert(node_id)
        if cert_pem:
            cert_path.parent.mkdir(parents=True, exist_ok=True)
            cert_path.write_bytes(cert_pem)
            key_path.write_bytes(key_pem)
    return cert_path, key_path
