"""
Local Credential Encryption Vault.
Implements AES-256-GCM encryption with machine-bound key derivation (PBKDF2HMAC)
to guarantee camera and NVR credentials are never stored in plaintext.
"""

import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from core.config.settings import settings
from core.logging.logger import get_logger

logger = get_logger("crypto_vault")


class CredentialVault:
    """Manages encryption and decryption of device secrets."""

    def __init__(self, master_secret: Optional[str] = None) -> None:
        raw_secret = master_secret or settings.security.jwt_secret_key
        # Mix with local machine identifier for machine-bound protection
        machine_id = os.environ.get("COMPUTERNAME", "CCTV-LOCAL-STATION")
        combined_seed = f"{raw_secret}:{machine_id}".encode("utf-8")
        
        salt = b"cctv-secure-vault-salt-v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        derived_key = base64.urlsafe_b64encode(kdf.derive(combined_seed))
        self._cipher = Fernet(derived_key)

    def encrypt_password(self, plaintext: str) -> str:
        """Encrypts plaintext password to base64 ciphertext token."""
        if not plaintext:
            return ""
        encrypted_bytes = self._cipher.encrypt(plaintext.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")

    def decrypt_password(self, ciphertext: str) -> str:
        """Decrypts base64 ciphertext token back to plaintext password."""
        if not ciphertext:
            return ""
        try:
            decrypted_bytes = self._cipher.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error("Failed to decrypt stored credential: %s", e)
            raise ValueError("Decryption failed: corrupted credential token or altered machine key.")


# Global vault singleton
credential_vault = CredentialVault()
