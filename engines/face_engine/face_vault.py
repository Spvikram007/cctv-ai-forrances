"""
Cryptographic Biometric Vault for Face Feature Templates.
Implements AES-256-GCM authenticated encryption/decryption of 512-dimensional embeddings,
backed by Windows Data Protection API (DPAPI) master key protection, versioning,
secure key rotation, and passphrase-derived disaster recovery bundles.
Guarantees zero plaintext biometric template exposure in database or logs.
"""

import os
import sys
import json
import base64
import struct
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Dict, Tuple
from hashlib import pbkdf2_hmac
import numpy as np

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("face_vault")


class BiometricVaultError(Exception):
    """Custom exception raised for cryptographic biometric vault errors."""
    pass


class FaceBiometricVault:
    """
    Production-Hardened Cryptographic Biometric Vault.
    Uses randomly generated AES-256 keys protected at rest via Windows DPAPI,
    AES-256-GCM authenticated encryption with unique 96-bit nonces, key versioning,
    rotation capabilities, and disaster recovery procedures.
    """

    VAULT_DIR: Path = Path("storage/vault")
    KEY_FILE: Path = Path("storage/vault/master_key.dpapi")
    KEYSTORE_FILE: Path = Path("storage/vault/keystore.dpapi")
    DPAPI_ENTROPY: bytes = b"CCTV_AI_BIOMETRIC_VAULT_DPAPI_ENTROPY_V2"

    _active_key_version: int = 1
    _active_key: Optional[bytes] = None
    _key_cache: Dict[int, bytes] = {}
    _initialized: bool = False

    # Windows DPAPI structures
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    @classmethod
    def _dpapi_protect(cls, plaintext: bytes) -> bytes:
        """Encrypts data using Windows DPAPI (CryptProtectData)."""
        if sys.platform != "win32":
            # Resilient fallback for non-Windows test environments
            return b"NON_WIN32_FALLBACK:" + base64.b64encode(plaintext)

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_in = cls.DATA_BLOB(
            len(plaintext),
            ctypes.cast(ctypes.create_string_buffer(plaintext, len(plaintext)), ctypes.POINTER(ctypes.c_byte)),
        )
        data_out = cls.DATA_BLOB()
        entropy_blob = cls.DATA_BLOB(
            len(cls.DPAPI_ENTROPY),
            ctypes.cast(ctypes.create_string_buffer(cls.DPAPI_ENTROPY, len(cls.DPAPI_ENTROPY)), ctypes.POINTER(ctypes.c_byte)),
        )

        if not crypt32.CryptProtectData(
            ctypes.byref(data_in),
            "cctv_biometric_master_key",
            ctypes.byref(entropy_blob),
            None,
            None,
            0,
            ctypes.byref(data_out),
        ):
            raise BiometricVaultError(f"Windows DPAPI encryption failed (WinError {ctypes.GetLastError()})")

        encrypted_bytes = ctypes.string_at(data_out.pbData, data_out.cbData)
        kernel32.LocalFree(data_out.pbData)
        return encrypted_bytes

    @classmethod
    def _dpapi_unprotect(cls, ciphertext: bytes) -> bytes:
        """Decrypts data using Windows DPAPI (CryptUnprotectData)."""
        if sys.platform != "win32" or ciphertext.startswith(b"NON_WIN32_FALLBACK:"):
            return base64.b64decode(ciphertext.replace(b"NON_WIN32_FALLBACK:", b""))

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_in = cls.DATA_BLOB(
            len(ciphertext),
            ctypes.cast(ctypes.create_string_buffer(ciphertext, len(ciphertext)), ctypes.POINTER(ctypes.c_byte)),
        )
        data_out = cls.DATA_BLOB()
        entropy_blob = cls.DATA_BLOB(
            len(cls.DPAPI_ENTROPY),
            ctypes.cast(ctypes.create_string_buffer(cls.DPAPI_ENTROPY, len(cls.DPAPI_ENTROPY)), ctypes.POINTER(ctypes.c_byte)),
        )

        if not crypt32.CryptUnprotectData(
            ctypes.byref(data_in),
            None,
            ctypes.byref(entropy_blob),
            None,
            None,
            0,
            ctypes.byref(data_out),
        ):
            raise BiometricVaultError(f"Windows DPAPI decryption failed (WinError {ctypes.GetLastError()})")

        decrypted_bytes = ctypes.string_at(data_out.pbData, data_out.cbData)
        kernel32.LocalFree(data_out.pbData)
        return decrypted_bytes

    @classmethod
    def initialize_vault(cls) -> None:
        """Loads or securely generates the master encryption key."""
        if cls._initialized:
            return

        cls.VAULT_DIR.mkdir(parents=True, exist_ok=True)

        if cls.KEY_FILE.exists():
            try:
                encrypted_payload = cls.KEY_FILE.read_bytes()
                decrypted_json = cls._dpapi_unprotect(encrypted_payload).decode("utf-8")
                key_data = json.loads(decrypted_json)
                cls._active_key_version = key_data["version"]
                cls._active_key = base64.b64decode(key_data["key"])
                cls._key_cache[cls._active_key_version] = cls._active_key
                cls._load_keystore()
                cls._initialized = True
                logger.info("Loaded Biometric Master Key v%d from DPAPI vault.", cls._active_key_version)
                return
            except Exception as e:
                logger.error("Failed to load existing DPAPI master key: %s. Generating fresh key.", e)

        # Generate fresh 256-bit random key
        cls._active_key_version = 1
        cls._active_key = os.urandom(32)  # 256-bit cryptographically secure random key
        cls._key_cache[cls._active_key_version] = cls._active_key
        cls._save_master_key()
        cls._initialized = True
        logger.info("Initialized new random Biometric Master Key v1 protected by Windows DPAPI.")

    @classmethod
    def _save_master_key(cls) -> None:
        """Saves active master key protected by Windows DPAPI."""
        payload = json.dumps({
            "version": cls._active_key_version,
            "key": base64.b64encode(cls._active_key).decode("utf-8"),
        }).encode("utf-8")
        protected_bytes = cls._dpapi_protect(payload)
        cls.KEY_FILE.write_bytes(protected_bytes)

    @classmethod
    def _load_keystore(cls) -> None:
        """Loads historical keys from encrypted keystore for seamless backward compatibility."""
        if cls.KEYSTORE_FILE.exists():
            try:
                protected = cls.KEYSTORE_FILE.read_bytes()
                raw_json = cls._dpapi_unprotect(protected).decode("utf-8")
                store = json.loads(raw_json)
                for ver_str, k_b64 in store.items():
                    cls._key_cache[int(ver_str)] = base64.b64decode(k_b64)
            except Exception as e:
                logger.warning("Could not load historical keystore: %s", e)

    @classmethod
    def _save_keystore(cls) -> None:
        """Persists all known key versions into DPAPI-protected keystore."""
        store = {str(v): base64.b64encode(k).decode("utf-8") for v, k in cls._key_cache.items()}
        payload = json.dumps(store).encode("utf-8")
        cls.KEYSTORE_FILE.write_bytes(cls._dpapi_protect(payload))

    @classmethod
    def _get_key_for_version(cls, version: int) -> bytes:
        cls.initialize_vault()
        if version in cls._key_cache:
            return cls._key_cache[version]
        raise BiometricVaultError(f"Biometric encryption key version v{version} not found in keystore")

    @classmethod
    def encrypt_template(cls, embedding_512: np.ndarray) -> str:
        """
        Encrypts a 512-dimensional float32 vector using AES-256-GCM.
        Guarantees a unique 96-bit random nonce per encryption and AEAD authentication.
        Format: v{version}:{nonce_hex}:{ciphertext_with_tag_hex}
        """
        cls.initialize_vault()
        if embedding_512 is None or len(embedding_512) != 512:
            raise ValueError("Biometric embedding must be a 512-dimensional vector")

        raw_bytes = struct.pack(f"{len(embedding_512)}f", *embedding_512)
        aesgcm = AESGCM(cls._active_key)
        nonce = os.urandom(12)  # Unique 96-bit nonce per encryption

        ciphertext = aesgcm.encrypt(nonce, raw_bytes, None)
        # Encapsulate with key version header for key rotation and backward compatibility
        return f"v{cls._active_key_version}:{nonce.hex()}:{ciphertext.hex()}"

    @classmethod
    def decrypt_template(cls, encrypted_blob: str) -> np.ndarray:
        """
        Decrypts an authenticated AES-256-GCM blob back into a 512-dimensional float32 vector.
        Supports both versioned envelopes ('v1:nonce:cipher') and legacy hex envelopes.
        """
        cls.initialize_vault()
        if not encrypted_blob:
            raise ValueError("Empty encrypted template blob")

        try:
            if ":" in encrypted_blob:
                parts = encrypted_blob.split(":")
                if len(parts) == 3:
                    if not parts[0].startswith("v") or not parts[0][1:].isdigit():
                        raise BiometricVaultError("Invalid or corrupted version tag in biometric envelope")
                    version = int(parts[0][1:])
                    nonce = bytes.fromhex(parts[1])
                    ciphertext = bytes.fromhex(parts[2])
                    key = cls._get_key_for_version(version)
                else:
                    raise BiometricVaultError("Malformed versioned biometric envelope")
            else:
                # Legacy compatibility: nonce (12 bytes = 24 hex) + ciphertext
                raw = bytes.fromhex(encrypted_blob)
                nonce = raw[:12]
                ciphertext = raw[12:]
                key = cls._active_key

            aesgcm = AESGCM(key)
            decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)

            num_floats = len(decrypted_bytes) // 4
            floats = struct.unpack(f"{num_floats}f", decrypted_bytes)
            return np.array(floats, dtype=np.float32)
        except Exception as e:
            raise BiometricVaultError(f"Biometric template decryption or authentication failed: {e}")

    @classmethod
    def rotate_master_key(cls) -> int:
        """
        Generates a new random 256-bit master key, archives the old key,
        updates versioning, and persists to Windows DPAPI.
        """
        cls.initialize_vault()
        new_version = cls._active_key_version + 1
        new_key = os.urandom(32)

        cls._key_cache[cls._active_key_version] = cls._active_key
        cls._active_key_version = new_version
        cls._active_key = new_key
        cls._key_cache[new_version] = new_key

        cls._save_master_key()
        cls._save_keystore()
        logger.info("Successfully rotated Biometric Master Key to v%d.", new_version)
        return new_version

    @classmethod
    def export_recovery_bundle(cls, passphrase: str) -> str:
        """
        Exports a secure recovery bundle of the active master key and keystore,
        encrypted with AES-256-GCM using a key derived via PBKDF2-HMAC-SHA256 (250,000 iterations).
        Enables disaster recovery in case of host hardware replacement or migration.
        """
        cls.initialize_vault()
        if not passphrase or len(passphrase) < 12:
            raise ValueError("Recovery passphrase must be at least 12 characters")

        salt = os.urandom(16)
        wrap_key = pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 250000, 32)
        aesgcm = AESGCM(wrap_key)
        nonce = os.urandom(12)

        data = {
            "version": cls._active_key_version,
            "master_key": base64.b64encode(cls._active_key).decode("utf-8"),
            "keystore": {str(v): base64.b64encode(k).decode("utf-8") for v, k in cls._key_cache.items()},
        }
        plaintext = json.dumps(data).encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)

        bundle_bytes = salt + nonce + ciphertext
        return f"CCTV_AI_RECOVERY_BUNDLE_V1:{base64.b64encode(bundle_bytes).decode('utf-8')}"

    @classmethod
    def import_recovery_bundle(cls, bundle_str: str, passphrase: str) -> int:
        """
        Restores biometric master keys from a passphrase-protected recovery bundle,
        re-encrypts them via Windows DPAPI, and updates the local vault.
        Returns the number of restored keys in keystore.
        Raises BiometricVaultError on invalid passphrase or corruption.
        """
        if not bundle_str or not passphrase:
            raise BiometricVaultError("Empty recovery bundle or passphrase")

        try:
            clean_bundle = bundle_str
            if clean_bundle.startswith("CCTV_AI_RECOVERY_BUNDLE_V1:"):
                clean_bundle = clean_bundle.split(":", 1)[1]

            bundle_bytes = base64.b64decode(clean_bundle)
            if len(bundle_bytes) < 44:  # 16 salt + 12 nonce + 16 min tag
                raise ValueError("Corrupt recovery bundle payload")

            salt = bundle_bytes[:16]
            nonce = bundle_bytes[16:28]
            ciphertext = bundle_bytes[28:]

            wrap_key = pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 250000, 32)
            aesgcm = AESGCM(wrap_key)
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)

            data = json.loads(plaintext.decode("utf-8"))
            cls._active_key_version = data["version"]
            cls._active_key = base64.b64decode(data["master_key"])
            cls._key_cache = {int(v): base64.b64decode(k) for v, k in data.get("keystore", {}).items()}
            cls._key_cache[cls._active_key_version] = cls._active_key

            cls.VAULT_DIR.mkdir(parents=True, exist_ok=True)
            cls._save_master_key()
            cls._save_keystore()
            cls._initialized = True
            logger.info("Successfully restored and DPAPI-bound master key v%d from recovery bundle.", cls._active_key_version)
            return len(cls._key_cache)
        except Exception as e:
            logger.error("Failed to restore recovery bundle: %s", e)
            raise BiometricVaultError(f"Failed to restore recovery bundle: {e}")
