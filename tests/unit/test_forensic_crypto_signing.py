"""
Unit Tests for Cryptographic Signing & Windows DPAPI Key Management (Phase 10 - F-023).
"""

import os
import tempfile
import pytest

from engines.forensic_engine.crypto_signer import ForensicSigner, CryptoSignerError


@pytest.fixture
def signer() -> ForensicSigner:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield ForensicSigner(keys_dir=tmpdir)


def test_signer_generates_and_protects_key(signer: ForensicSigner) -> None:
    """Verifies signer initializes ECDSA SECP256R1 key and saves DPAPI file."""
    assert signer.key_file.exists()
    assert signer.pub_file.exists()

    pub_pem = signer.get_public_key_pem()
    assert "BEGIN PUBLIC KEY" in pub_pem
    assert "END PUBLIC KEY" in pub_pem


def test_signature_generation_and_verification(signer: ForensicSigner) -> None:
    """Verifies digital signature verification on valid payload."""
    payload = b"CCTV_EVIDENCE_HASH_SHA256:4f9b2d8e17a356c9d08e1a7b453e921d"
    signature_hex = signer.sign_payload(payload)

    assert isinstance(signature_hex, str)
    assert len(signature_hex) > 64

    pub_pem = signer.get_public_key_pem()
    is_valid = ForensicSigner.verify_signature(payload, signature_hex, pub_pem)
    assert is_valid is True


def test_tampered_payload_signature_rejection(signer: ForensicSigner) -> None:
    """Verifies signature verification fails when payload is altered."""
    payload = b"GENUINE_MANIFEST_PAYLOAD"
    signature_hex = signer.sign_payload(payload)
    pub_pem = signer.get_public_key_pem()

    tampered_payload = b"TAMPERED_MANIFEST_PAYLOAD"
    is_valid = ForensicSigner.verify_signature(tampered_payload, signature_hex, pub_pem)
    assert is_valid is False


def test_corrupted_signature_rejection(signer: ForensicSigner) -> None:
    """Verifies invalid or malformed signature strings are rejected safely."""
    payload = b"TEST_DATA"
    pub_pem = signer.get_public_key_pem()

    assert ForensicSigner.verify_signature(payload, "00112233445566778899aabbccddeeff", pub_pem) is False
    assert ForensicSigner.verify_signature(payload, "INVALID_HEX_STRING", pub_pem) is False


def test_key_persistence_across_instances() -> None:
    """Verifies DPAPI protected key is loaded intact across distinct signer instances."""
    with tempfile.TemporaryDirectory() as tmpdir:
        signer1 = ForensicSigner(keys_dir=tmpdir)
        pub1 = signer1.get_public_key_pem()

        payload = b"TEST_CROSS_INSTANCE_SIGNING"
        sig1 = signer1.sign_payload(payload)

        # Second instance using same directory
        signer2 = ForensicSigner(keys_dir=tmpdir)
        pub2 = signer2.get_public_key_pem()

        assert pub1 == pub2
        assert ForensicSigner.verify_signature(payload, sig1, pub2) is True
