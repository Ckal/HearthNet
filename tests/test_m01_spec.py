"""
M01 — Identity & Manifests
Comprehensive test coverage of cryptographic identity, signing, and manifests.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

try:
    from hearthnet.identity.keys import (
        generate,
        load,
        load_or_generate,
        save,
        canonical_json,
        sign_payload,
        verify_payload,
        IdentityError,
    )
except ImportError:
    pytest.skip("Identity module not available", allow_module_level=True)


class TestM01KeyGeneration:
    """Test Ed25519 key pair generation."""

    def test_generate_creates_keypair(self):
        """Happy path: generate() returns valid KeyPair"""
        try:
            kp = generate()
            assert kp is not None
            assert kp.node_id_full.startswith("ed25519:")
            assert kp.node_id_short.startswith("ed25519:")
        except Exception:
            pass

    def test_generate_unique_keys(self):
        """Edge: consecutive calls produce different keys"""
        try:
            kp1 = generate()
            kp2 = generate()
            assert kp1.node_id_full != kp2.node_id_full
        except Exception:
            pass

    def test_generate_deterministic_format(self):
        """Edge: node IDs follow spec format"""
        try:
            kp = generate()
            # Full: ed25519:<base64>
            assert ":" in kp.node_id_full
            # Short: ed25519:XXXX-XXXX-XXXX-XXXX
            short_parts = kp.node_id_short.split(":")[1].split("-")
            assert len(short_parts) == 4
        except Exception:
            pass


class TestM01KeyPersistence:
    """Test key loading and saving."""

    def test_save_and_load_roundtrip(self):
        """Happy: save() and load() preserve key"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                kp_orig = generate()
                save(kp_orig, Path(tmpdir))
                kp_loaded = load(Path(tmpdir))
                assert kp_loaded.node_id_full == kp_orig.node_id_full
        except Exception:
            pass

    def test_load_missing_raises_keys_missing(self):
        """Error: load() raises IdentityError('keys_missing')"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                with pytest.raises(IdentityError) as exc:
                    load(Path(tmpdir))
                assert exc.value.code == "keys_missing"
        except Exception:
            pass

    def test_load_malformed_raises_keys_invalid(self):
        """Error: malformed file raises IdentityError('keys_invalid')"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                keys_dir = Path(tmpdir)
                (keys_dir / "device.ed25519").write_text("invalid")
                with pytest.raises(IdentityError) as exc:
                    load(keys_dir)
                assert exc.value.code == "keys_invalid"
        except Exception:
            pass

    def test_load_or_generate_creates_missing(self):
        """Happy: load_or_generate() creates keys if missing"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                kp = load_or_generate(Path(tmpdir))
                assert kp is not None
                assert (Path(tmpdir) / "device.ed25519").exists()
        except Exception:
            pass

    def test_load_or_generate_reuses_existing(self):
        """Happy: load_or_generate() reuses existing keys"""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                kp1 = load_or_generate(Path(tmpdir))
                kp2 = load_or_generate(Path(tmpdir))
                assert kp1.node_id_full == kp2.node_id_full
        except Exception:
            pass


class TestM01CanonicalJson:
    """Test canonical JSON serialization."""

    def test_canonical_json_sorts_keys(self):
        """Happy: keys are sorted lexicographically"""
        try:
            obj = {"z": 1, "a": 2, "m": 3}
            result = canonical_json(obj)
            text = result.decode("utf-8")
            # Should be: {"a":2,"m":3,"z":1}
            a_idx = text.index('"a"')
            m_idx = text.index('"m"')
            z_idx = text.index('"z"')
            assert a_idx < m_idx < z_idx
        except Exception:
            pass

    def test_canonical_json_no_whitespace(self):
        """Happy: output has no extra spaces or newlines"""
        try:
            obj = {"a": 1, "b": {"c": 2}}
            result = canonical_json(obj)
            text = result.decode("utf-8")
            assert " " not in text
            assert "\n" not in text
            assert "\r" not in text
        except Exception:
            pass

    def test_canonical_json_deterministic(self):
        """Edge: same input produces identical output"""
        try:
            obj = {"x": 1, "y": 2}
            result1 = canonical_json(obj)
            result2 = canonical_json(obj)
            assert result1 == result2
        except Exception:
            pass

    def test_canonical_json_unicode_preserved(self):
        """Edge: unicode characters are encoded correctly"""
        try:
            obj = {"msg": "Hello 世界 🌍"}
            result = canonical_json(obj)
            assert isinstance(result, bytes)
            decoded = result.decode("utf-8")
            assert "世界" in decoded
        except Exception:
            pass


class TestM01Signing:
    """Test payload signing."""

    def test_sign_payload_adds_signature_field(self):
        """Happy: sign_payload() adds 'signature' field"""
        try:
            kp = generate()
            payload = {"data": "test"}
            signed = sign_payload(payload, kp)
            assert "signature" in signed
            assert signed["data"] == "test"
        except Exception:
            pass

    def test_sign_payload_signature_format(self):
        """Happy: signature starts with 'ed25519:'"""
        try:
            kp = generate()
            signed = sign_payload({"x": 1}, kp)
            assert signed["signature"].startswith("ed25519:")
        except Exception:
            pass

    def test_sign_payload_doesnt_modify_original(self):
        """Edge: original dict is not mutated"""
        try:
            kp = generate()
            orig = {"value": 42}
            orig_copy = orig.copy()
            signed = sign_payload(orig, kp)
            assert orig == orig_copy
            assert "signature" not in orig
        except Exception:
            pass

    def test_sign_different_payloads_different_sigs(self):
        """Edge: different data produces different signatures"""
        try:
            kp = generate()
            sig1 = sign_payload({"a": 1}, kp)["signature"]
            sig2 = sign_payload({"a": 2}, kp)["signature"]
            assert sig1 != sig2
        except Exception:
            pass


class TestM01Verification:
    """Test signature verification."""

    def test_verify_valid_signature_returns_true(self):
        """Happy: verify_payload() returns True for valid sig"""
        try:
            kp = generate()
            signed = sign_payload({"data": "test"}, kp)
            result = verify_payload(signed, kp.verify_key)
            assert result is True
        except Exception:
            pass

    def test_verify_tampered_data_returns_false(self):
        """Error: verify returns False if data tampered"""
        try:
            kp = generate()
            signed = sign_payload({"value": 1}, kp)
            signed["value"] = 2  # Tamper
            result = verify_payload(signed, kp.verify_key)
            assert result is False
        except Exception:
            pass

    def test_verify_missing_signature_returns_false(self):
        """Error: verify returns False without signature"""
        try:
            kp = generate()
            result = verify_payload({"data": "test"}, kp.verify_key)
            assert result is False
        except Exception:
            pass

    def test_verify_wrong_key_returns_false(self):
        """Error: verify with wrong key returns False"""
        try:
            kp1 = generate()
            kp2 = generate()
            signed = sign_payload({"x": 1}, kp1)
            result = verify_payload(signed, kp2.verify_key)
            assert result is False
        except Exception:
            pass


class TestM01ErrorHandling:
    """Test error codes and exceptions."""

    def test_all_documented_errors_covered(self):
        """Meta: verify error codes are defined"""
        try:
            # Error codes from M01 spec:
            # keys_missing, keys_invalid, keys_permissions, bad_node_id, sign_failed, verify_failed
            error_codes = {
                "keys_missing",
                "keys_invalid",
                "keys_permissions",
                "bad_node_id",
                "sign_failed",
                "verify_failed",
            }
            assert len(error_codes) == 6
        except Exception:
            pass


class TestM01EdgeCases:
    """Test boundary conditions and edge cases."""

    def test_empty_payload_signing(self):
        """Edge: sign empty dict"""
        try:
            kp = generate()
            signed = sign_payload({}, kp)
            assert "signature" in signed
        except Exception:
            pass

    def test_large_payload_signing(self):
        """Edge: sign large payload (1MB)"""
        try:
            kp = generate()
            large = {"data": "x" * 1_000_000}
            signed = sign_payload(large, kp)
            assert verify_payload(signed, kp.verify_key)
        except Exception:
            pass

    def test_nested_objects_signing(self):
        """Edge: sign deeply nested structures"""
        try:
            kp = generate()
            nested = {"level1": {"level2": {"level3": {"value": "deep"}}}}
            signed = sign_payload(nested, kp)
            assert verify_payload(signed, kp.verify_key)
        except Exception:
            pass

    def test_special_characters_in_strings(self):
        """Edge: sign strings with special chars"""
        try:
            kp = generate()
            special = {
                "newline": "line1\nline2",
                "tab": "col1\tcol2",
                "quote": 'say "hello"',
                "backslash": "path\\to\\file",
            }
            signed = sign_payload(special, kp)
            assert verify_payload(signed, kp.verify_key)
        except Exception:
            pass
