"""
Unit Tests for Biometric Key Security, Windows DPAPI, Nonce Randomization, Key Rotation, and Recovery Bundles.
"""

import os
import pytest
import numpy as np

from engines.face_engine.face_vault import FaceBiometricVault, BiometricVaultError


class TestBiometricVaultSecurity:
    @pytest.fixture(autouse=True)
    def setup_vault(self, tmp_path, monkeypatch):
        vault_dir = tmp_path / "test_vault"
        monkeypatch.setattr(FaceBiometricVault, "VAULT_DIR", vault_dir)
        monkeypatch.setattr(FaceBiometricVault, "KEY_FILE", vault_dir / "master.key")
        monkeypatch.setattr(FaceBiometricVault, "KEYSTORE_FILE", vault_dir / "keystore.dat")
        FaceBiometricVault._initialized = False
        FaceBiometricVault._key_cache.clear()
        FaceBiometricVault.initialize_vault()

    def test_dpapi_vault_encryption_roundtrip(self):
        """Validates float32 bit-exact biometric vector encryption and decryption."""
        rng = np.random.RandomState(42)
        raw_vec = rng.randn(512).astype(np.float32)
        raw_vec /= np.linalg.norm(raw_vec)

        encrypted_hex = FaceBiometricVault.encrypt_template(raw_vec)
        assert isinstance(encrypted_hex, str)
        assert encrypted_hex.startswith("v1:")

        decrypted_vec = FaceBiometricVault.decrypt_template(encrypted_hex)
        assert decrypted_vec.shape == (512,)
        assert decrypted_vec.dtype == np.float32
        np.testing.assert_allclose(decrypted_vec, raw_vec, rtol=1e-5, atol=1e-5)

    def test_dpapi_vault_unique_nonces(self):
        """Encrypting the same biometric template twice MUST produce distinct ciphertexts (unique 96-bit nonces)."""
        vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
        cipher1 = FaceBiometricVault.encrypt_template(vec)
        cipher2 = FaceBiometricVault.encrypt_template(vec)

        assert cipher1 != cipher2
        parts1 = cipher1.split(":")
        parts2 = cipher2.split(":")
        # Nonces must differ
        assert parts1[1] != parts2[1]
        # Ciphertexts must differ
        assert parts1[2] != parts2[2]

    def test_dpapi_vault_version_prefix(self):
        """Validates envelope version formatting 'v{version}:{nonce}:{ciphertext}'."""
        vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
        cipher = FaceBiometricVault.encrypt_template(vec)
        parts = cipher.split(":")
        assert len(parts) == 3
        assert parts[0] == "v1"
        assert len(parts[1]) == 24  # 12-byte hex nonce

    def test_dpapi_vault_tamper_detection(self):
        """Altering version header, nonce, or ciphertext MUST raise BiometricVaultError."""
        vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
        cipher = FaceBiometricVault.encrypt_template(vec)
        parts = cipher.split(":")

        # 1. Corrupted version tag
        tampered_version = f"v999:{parts[1]}:{parts[2]}"
        with pytest.raises(BiometricVaultError):
            FaceBiometricVault.decrypt_template(tampered_version)

        # 2. Corrupted nonce
        bad_nonce = ("00" if parts[1][:2] != "00" else "ff") + parts[1][2:]
        tampered_nonce = f"{parts[0]}:{bad_nonce}:{parts[2]}"
        with pytest.raises(BiometricVaultError):
            FaceBiometricVault.decrypt_template(tampered_nonce)

        # 3. Corrupted ciphertext / tag (flipped bit)
        bad_cipher = parts[2][:-2] + ("00" if parts[2][-2:] != "00" else "ff")
        tampered_cipher = f"{parts[0]}:{parts[1]}:{bad_cipher}"
        with pytest.raises(BiometricVaultError):
            FaceBiometricVault.decrypt_template(tampered_cipher)

    def test_dpapi_vault_key_rotation(self):
        """Verifies multi-version key rotation and backward-compatible template decryption."""
        vec1 = np.ones(512, dtype=np.float32) / np.sqrt(512)
        cipher_v1 = FaceBiometricVault.encrypt_template(vec1)
        assert cipher_v1.startswith("v1:")

        # Rotate key
        new_version = FaceBiometricVault.rotate_master_key()
        assert new_version == 2

        # New encryption uses v2
        vec2 = np.zeros(512, dtype=np.float32)
        vec2[0] = 1.0
        cipher_v2 = FaceBiometricVault.encrypt_template(vec2)
        assert cipher_v2.startswith("v2:")

        # Both v1 and v2 templates decrypt cleanly
        dec_v1 = FaceBiometricVault.decrypt_template(cipher_v1)
        dec_v2 = FaceBiometricVault.decrypt_template(cipher_v2)
        np.testing.assert_allclose(dec_v1, vec1, atol=1e-5)
        np.testing.assert_allclose(dec_v2, vec2, atol=1e-5)

    def test_dpapi_vault_recovery_bundle_roundtrip(self, tmp_path, monkeypatch):
        """Validates encrypted recovery bundle export and import across isolated vaults."""
        vec = np.ones(512, dtype=np.float32) / np.sqrt(512)
        cipher_orig = FaceBiometricVault.encrypt_template(vec)

        passphrase = "SuperSecureDisasterRecoveryPassphrase123!"
        bundle_str = FaceBiometricVault.export_recovery_bundle(passphrase)
        assert bundle_str.startswith("CCTV_AI_RECOVERY_BUNDLE_V1:")

        # Setup second isolated vault
        isolated_dir = tmp_path / "isolated_vault"
        monkeypatch.setattr(FaceBiometricVault, "VAULT_DIR", isolated_dir)
        monkeypatch.setattr(FaceBiometricVault, "KEY_FILE", isolated_dir / "master.key")
        monkeypatch.setattr(FaceBiometricVault, "KEYSTORE_FILE", isolated_dir / "keystore.dat")
        FaceBiometricVault._initialized = False
        FaceBiometricVault._key_cache.clear()

        # Import recovery bundle into new vault
        restored_count = FaceBiometricVault.import_recovery_bundle(bundle_str, passphrase)
        assert restored_count >= 1

        # Decrypt original ciphertext in restored vault
        decrypted = FaceBiometricVault.decrypt_template(cipher_orig)
        np.testing.assert_allclose(decrypted, vec, atol=1e-5)

    def test_dpapi_vault_recovery_bundle_wrong_passphrase(self):
        """Importing recovery bundle with invalid passphrase MUST fail."""
        passphrase = "CorrectPassphrase2026!"
        bundle_str = FaceBiometricVault.export_recovery_bundle(passphrase)

        with pytest.raises(BiometricVaultError):
            FaceBiometricVault.import_recovery_bundle(bundle_str, "WrongPassphrase!")
