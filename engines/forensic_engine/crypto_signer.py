"""
Cryptographic Signing Engine & Windows DPAPI Key Management (Phase 10 - F-023).
Generates and protects ECDSA (NIST P-256) signing keys using Windows DPAPI,
signs evidence manifests, verifies asymmetric digital signatures, and manages
public verification certificates.
"""

import os
import sys
import base64
import ctypes
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger("forensic_crypto_signer")


class CryptoSignerError(Exception):
    """Exception raised for cryptographic signing errors."""
    pass


class ForensicSigner:
    """
    Manages ECDSA (SECP256R1 / NIST P-256) asymmetric keypairs.
    Protects private keys at rest via Windows DPAPI (CryptProtectData).
    Signs evidence manifests and verifies digital signatures.
    """

    DPAPI_ENTROPY: bytes = b"CCTV_AI_FORENSIC_SIGNING_ENTROPY_V1"

    # Windows DPAPI structures
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def __init__(self, keys_dir: Optional[str] = None) -> None:
        if keys_dir is None:
            self.keys_dir = Path(settings.storage.evidence_dir) / ".keys"
        else:
            self.keys_dir = Path(keys_dir)

        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = self.keys_dir / "forensic_signing_key.dpapi"
        self.pub_file = self.keys_dir / "forensic_public_key.pem"

        self._private_key: Optional[ec.EllipticCurvePrivateKey] = None
        self._public_key_pem: Optional[str] = None
        self._init_keys()

    def _dpapi_protect(self, plaintext: bytes) -> bytes:
        """Encrypts private key bytes using Windows DPAPI."""
        if sys.platform != "win32":
            # Resilient fallback for non-Windows test environments
            return b"NON_WIN32_FALLBACK:" + base64.b64encode(plaintext)

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_in = self.DATA_BLOB(
            len(plaintext),
            ctypes.cast(ctypes.create_string_buffer(plaintext, len(plaintext)), ctypes.POINTER(ctypes.c_byte)),
        )
        entropy_in = self.DATA_BLOB(
            len(self.DPAPI_ENTROPY),
            ctypes.cast(ctypes.create_string_buffer(self.DPAPI_ENTROPY, len(self.DPAPI_ENTROPY)), ctypes.POINTER(ctypes.c_byte)),
        )
        data_out = self.DATA_BLOB()

        # CRYPTPROTECT_UI_FORBIDDEN = 0x1
        ret = crypt32.CryptProtectData(
            ctypes.byref(data_in),
            "CCTV_AI_Forensic_Signing_Key",
            ctypes.byref(entropy_in),
            None,
            None,
            0x1,
            ctypes.byref(data_out),
        )
        if not ret:
            err = kernel32.GetLastError()
            raise CryptoSignerError(f"Windows DPAPI CryptProtectData failed with error code: {err}")

        try:
            cipher_bytes = ctypes.string_at(data_out.pbData, data_out.cbData)
            return cipher_bytes
        finally:
            kernel32.LocalFree(data_out.pbData)

    def _dpapi_unprotect(self, ciphertext: bytes) -> bytes:
        """Decrypts private key bytes using Windows DPAPI."""
        if sys.platform != "win32":
            if ciphertext.startswith(b"NON_WIN32_FALLBACK:"):
                return base64.b64decode(ciphertext[len(b"NON_WIN32_FALLBACK:"):])
            raise CryptoSignerError("Invalid non-Windows key format")

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        data_in = self.DATA_BLOB(
            len(ciphertext),
            ctypes.cast(ctypes.create_string_buffer(ciphertext, len(ciphertext)), ctypes.POINTER(ctypes.c_byte)),
        )
        entropy_in = self.DATA_BLOB(
            len(self.DPAPI_ENTROPY),
            ctypes.cast(ctypes.create_string_buffer(self.DPAPI_ENTROPY, len(self.DPAPI_ENTROPY)), ctypes.POINTER(ctypes.c_byte)),
        )
        data_out = self.DATA_BLOB()

        ret = crypt32.CryptUnprotectData(
            ctypes.byref(data_in),
            None,
            ctypes.byref(entropy_in),
            None,
            None,
            0x1,
            ctypes.byref(data_out),
        )
        if not ret:
            err = kernel32.GetLastError()
            raise CryptoSignerError(f"Windows DPAPI CryptUnprotectData failed with error code: {err}")

        try:
            plain_bytes = ctypes.string_at(data_out.pbData, data_out.cbData)
            return plain_bytes
        finally:
            kernel32.LocalFree(data_out.pbData)

    def _init_keys(self) -> None:
        """Loads existing keypair or generates a fresh one protected by DPAPI."""
        if self.key_file.exists() and self.pub_file.exists():
            try:
                with open(self.key_file, "rb") as f:
                    cipher_blob = f.read()
                plain_pem = self._dpapi_unprotect(cipher_blob)
                self._private_key = serialization.load_pem_private_key(plain_pem, password=None)
                with open(self.pub_file, "r", encoding="utf-8") as f:
                    self._public_key_pem = f.read()
                logger.info("Successfully loaded DPAPI-protected forensic signing key.")
                return
            except Exception as e:
                logger.warning("Failed to unprotect existing signing key (%s). Generating fresh keypair.", e)

        self._generate_fresh_keypair()

    def _generate_fresh_keypair(self) -> None:
        """Generates fresh ECDSA SECP256R1 keypair and seals with DPAPI."""
        self._private_key = ec.generate_private_key(ec.SECP256R1())
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_key = self._private_key.public_key()
        self._public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        # Protect private key with Windows DPAPI
        protected_blob = self._dpapi_protect(private_pem)
        with open(self.key_file, "wb") as f:
            f.write(protected_blob)

        with open(self.pub_file, "w", encoding="utf-8") as f:
            f.write(self._public_key_pem)

        logger.info("Generated fresh ECDSA SECP256R1 keypair and sealed private key with Windows DPAPI.")

    def get_public_key_pem(self) -> str:
        """Returns the public key in standard PEM format."""
        if self._public_key_pem is None:
            raise CryptoSignerError("Public key is not initialized.")
        return self._public_key_pem

    def sign_payload(self, payload: bytes) -> str:
        """
        Signs arbitrary binary payload (e.g. SHA-256 hash or canonical manifest JSON)
        using ECDSA SECP256R1 and SHA-256. Returns hex-encoded DER signature.
        """
        if self._private_key is None:
            raise CryptoSignerError("Private signing key is not initialized.")

        signature_der = self._private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return signature_der.hex()

    @staticmethod
    def verify_signature(payload: bytes, signature_hex: str, public_key_pem: str) -> bool:
        """
        Verifies ECDSA digital signature using the provided public key PEM.
        Returns True if valid, False if altered or forged.
        """
        try:
            pub_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
            signature_der = bytes.fromhex(signature_hex)
            pub_key.verify(signature_der, payload, ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, ValueError, TypeError) as e:
            logger.warning("Digital signature verification failed: %s", e)
            return False
        except Exception as e:
            logger.error("Unexpected error during signature verification: %s", e)
            return False
