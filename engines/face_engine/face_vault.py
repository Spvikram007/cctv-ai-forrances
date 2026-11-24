"""
Cryptographic Biometric Vault for Face Feature Templates.
Implements AES-256-GCM encryption/decryption of 512-dimensional embeddings,
guaranteeing zero plaintext biometric template exposure in database or logs.
"""

import os
import struct
from typing import Optional
import numpy as np

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.hardware.detector import HardwareDetector
from core.logging.logger import get_logger

logger = get_logger("face_vault")


class FaceBiometricVault:
    """
    Hardware-bound AES-256-GCM encryption vault for biometric face templates.
    """

    _key: Optional[bytes] = None

    @classmethod
    def _get_key(cls) -> bytes:
        if cls._key is None:
            # Derive 256-bit key from local hardware identity
            cpu_info = HardwareDetector.detect_cpu()
            processor_name = cpu_info.model or "Intel-CPU"
            seed = f"{processor_name}-CCTV-AI-BIOMETRIC-VAULT-2026".encode("utf-8")
            from hashlib import pbkdf2_hmac
            cls._key = pbkdf2_hmac("sha256", seed, b"CCTV_AI_BIOMETRICS_SALT_V1", 100000, dklen=32)
        return cls._key

    @classmethod
    def encrypt_template(cls, embedding_512: np.ndarray) -> str:
        """
        Encrypts a 512-dimensional float32 vector into a hex-encoded AES-256-GCM blob.
        """
        if embedding_512 is None or len(embedding_512) != 512:
            raise ValueError("Biometric embedding must be a 512-dimensional vector")

        raw_bytes = struct.pack(f"{len(embedding_512)}f", *embedding_512)
        key = cls._get_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # 96-bit unique nonce

        ciphertext = aesgcm.encrypt(nonce, raw_bytes, None)
        # Store as nonce + ciphertext in hex
        encrypted_blob = (nonce + ciphertext).hex()
        return encrypted_blob

    @classmethod
    def decrypt_template(cls, encrypted_hex: str) -> np.ndarray:
        """
        Decrypts a hex-encoded AES-256-GCM blob back into a 512-dimensional float32 vector.
        """
        if not encrypted_hex:
            raise ValueError("Empty encrypted template blob")

        raw = bytes.fromhex(encrypted_hex)
        nonce = raw[:12]
        ciphertext = raw[12:]

        key = cls._get_key()
        aesgcm = AESGCM(key)
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)

        num_floats = len(decrypted_bytes) // 4
        floats = struct.unpack(f"{num_floats}f", decrypted_bytes)
        return np.array(floats, dtype=np.float32)
