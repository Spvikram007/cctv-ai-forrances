"""
Cryptographic Signing Engine & Windows DPAPI Key Management (Phase 10 & 10.1 - F-023).
Generates and protects ECDSA (NIST P-256) signing keys using Windows DPAPI,
signs evidence manifests, verifies asymmetric digital signatures, and manages
public verification certificates, key fingerprints, trusted keystores, and revocation.
"""

import os
import sys
import json
import base64
import ctypes
import hashlib
from ctypes import wintypes
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger("forensic_crypto_signer")


class CryptoSignerError(Exception):
    """Exception raised for cryptographic signing errors."""
    pass


class KeyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


def compute_key_fingerprint(public_key_pem: str) -> str:
    """
    Computes a standardized SHA-256 fingerprint of the public key's DER SubjectPublicKeyInfo.
    Returns format 'SHA256:<64_hex_chars>'.
    """
    pub_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    der_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return f"SHA256:{hashlib.sha256(der_bytes).hexdigest()}"


class TrustedKeyStore:
    """
    Authoritative Trust Store for forensic public keys.
    Maintains trusted keys, fingerprints, operator identities, and revocation records.
    Prevents self-signed trust injection by validating candidate keys against
    authoritative trust records.
    """

    def __init__(self, trust_store_path: Optional[str] = None) -> None:
        if trust_store_path is None:
            self.store_file = Path(settings.storage.evidence_dir) / "trust_store" / "trusted_keys.json"
        else:
            self.store_file = Path(trust_store_path)

        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        self._keys: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        """Loads trusted keys from storage."""
        if self.store_file.exists():
            try:
                with open(self.store_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._keys = data.get("keys", {})
            except Exception as e:
                logger.error("Failed to load trust store from %s: %s", self.store_file, e)
                self._keys = {}
        else:
            self._keys = {}

    def save(self) -> None:
        """Persists trusted keys to storage."""
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "format_version": "1.0",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "keys": self._keys,
        }
        with open(self.store_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def register_key(
        self,
        key_id: str,
        public_key_pem: str,
        identity: str,
        status: KeyStatus = KeyStatus.ACTIVE,
    ) -> Dict[str, Any]:
        """Registers a new public key in the trust store."""
        fingerprint = compute_key_fingerprint(public_key_pem)
        entry = {
            "key_id": key_id,
            "fingerprint": fingerprint,
            "public_key_pem": public_key_pem.strip(),
            "identity": identity,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": status.value if isinstance(status, KeyStatus) else str(status),
            "revoked_at_utc": None,
            "revocation_reason": None,
        }
        self._keys[fingerprint] = entry
        self.save()
        logger.info("Registered trusted key '%s' (%s) for identity '%s'", key_id, fingerprint, identity)
        return entry

    def revoke_key(self, fingerprint_or_key_id: str, reason: str = "Key rotated or revoked") -> bool:
        """Revokes an existing key by fingerprint or key ID."""
        target_entry = None
        for fp, entry in self._keys.items():
            if fp == fingerprint_or_key_id or entry.get("key_id") == fingerprint_or_key_id:
                target_entry = entry
                break

        if not target_entry:
            logger.warning("Cannot revoke key: '%s' not found in trust store.", fingerprint_or_key_id)
            return False

        target_entry["status"] = KeyStatus.REVOKED.value
        target_entry["revoked_at_utc"] = datetime.now(timezone.utc).isoformat()
        target_entry["revocation_reason"] = reason
        self.save()
        logger.warning("Revoked key '%s': %s", target_entry.get("key_id"), reason)
        return True

    def rotate_key(
        self,
        old_key_id_or_fp: str,
        new_key_id: str,
        new_public_key_pem: str,
        identity: str,
        reason: str = "Scheduled key rotation",
    ) -> Dict[str, Any]:
        """Atomically rotates a key: revokes old key and registers new key."""
        self.revoke_key(old_key_id_or_fp, reason)
        return self.register_key(new_key_id, new_public_key_pem, identity, status=KeyStatus.ACTIVE)

    def is_key_trusted(self, public_key_pem: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Validates whether a public key PEM exists in the trusted store and is ACTIVE.
        Returns: (is_trusted, key_entry, reason)
        """
        try:
            candidate_fp = compute_key_fingerprint(public_key_pem)
        except Exception as e:
            return False, None, f"Malformed public key PEM: {e}"

        entry = self._keys.get(candidate_fp)
        if not entry:
            for fp, k_entry in self._keys.items():
                try:
                    if compute_key_fingerprint(k_entry["public_key_pem"]) == candidate_fp:
                        entry = k_entry
                        break
                except Exception:
                    pass

        if not entry:
            return False, None, f"Public key with fingerprint '{candidate_fp}' is not recognized in trust store."

        if entry.get("status") == KeyStatus.REVOKED.value:
            return False, entry, f"Key '{entry.get('key_id')}' was REVOKED on {entry.get('revoked_at_utc')}: {entry.get('revocation_reason')}."

        if entry.get("status") == KeyStatus.EXPIRED.value:
            return False, entry, f"Key '{entry.get('key_id')}' has EXPIRED."

        return True, entry, "Key is trusted and ACTIVE."

    def get_all_keys(self) -> List[Dict[str, Any]]:
        """Returns all registered keys."""
        return list(self._keys.values())


class ForensicSigner:
    """
    Manages ECDSA (SECP256R1 / NIST P-256) asymmetric keypairs.
    Protects private keys at rest via Windows DPAPI (CryptProtectData).
    Signs evidence manifests, manages key fingerprints and key IDs,
    and coordinates with the TrustedKeyStore.
    """

    DPAPI_ENTROPY: bytes = b"CCTV_AI_FORENSIC_SIGNING_ENTROPY_V1"

    # Windows DPAPI structures
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def __init__(
        self,
        keys_dir: Optional[str] = None,
        trust_store: Optional[TrustedKeyStore] = None,
        key_id: Optional[str] = None,
        identity: str = "CCTV_FORENSIC_AUTHORITY_PRIMARY",
    ) -> None:
        if keys_dir is None:
            self.keys_dir = Path(settings.storage.evidence_dir) / ".keys"
        else:
            self.keys_dir = Path(keys_dir)

        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = self.keys_dir / "forensic_signing_key.dpapi"
        self.pub_file = self.keys_dir / "forensic_public_key.pem"
        self.meta_file = self.keys_dir / "key_metadata.json"

        self.identity = identity
        self.trust_store = trust_store or TrustedKeyStore(self.keys_dir.parent / "trust_store" / "trusted_keys.json")

        self._private_key: Optional[ec.EllipticCurvePrivateKey] = None
        self._public_key_pem: Optional[str] = None
        self.key_id = key_id or "KEY-2026-PRIMARY-01"
        self.key_fingerprint: str = ""

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

    def _load_metadata(self) -> None:
        """Loads persistent key ID and metadata."""
        if self.meta_file.exists():
            try:
                with open(self.meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    self.key_id = meta.get("key_id", self.key_id)
                    self.identity = meta.get("identity", self.identity)
            except Exception:
                pass

    def _save_metadata(self) -> None:
        """Persists key metadata."""
        meta = {
            "key_id": self.key_id,
            "identity": self.identity,
            "fingerprint": self.key_fingerprint,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def _init_keys(self) -> None:
        """Loads existing keypair or generates a fresh one protected by DPAPI."""
        self._load_metadata()

        if self.key_file.exists() and self.pub_file.exists():
            try:
                with open(self.key_file, "rb") as f:
                    cipher_blob = f.read()
                plain_pem = self._dpapi_unprotect(cipher_blob)
                self._private_key = serialization.load_pem_private_key(plain_pem, password=None)
                with open(self.pub_file, "r", encoding="utf-8") as f:
                    self._public_key_pem = f.read()
                self.key_fingerprint = compute_key_fingerprint(self._public_key_pem)

                # Ensure key is registered in trust store
                is_trusted, _, _ = self.trust_store.is_key_trusted(self._public_key_pem)
                if not is_trusted:
                    self.trust_store.register_key(
                        key_id=self.key_id,
                        public_key_pem=self._public_key_pem,
                        identity=self.identity,
                        status=KeyStatus.ACTIVE,
                    )

                logger.info("Loaded DPAPI signing key '%s' (Fingerprint: %s)", self.key_id, self.key_fingerprint)
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

        self.key_fingerprint = compute_key_fingerprint(self._public_key_pem)

        # Protect private key with Windows DPAPI
        protected_blob = self._dpapi_protect(private_pem)
        with open(self.key_file, "wb") as f:
            f.write(protected_blob)

        with open(self.pub_file, "w", encoding="utf-8") as f:
            f.write(self._public_key_pem)

        self._save_metadata()

        # Register in Trust Store
        self.trust_store.register_key(
            key_id=self.key_id,
            public_key_pem=self._public_key_pem,
            identity=self.identity,
            status=KeyStatus.ACTIVE,
        )

        logger.info(
            "Generated fresh ECDSA SECP256R1 keypair '%s' (Fingerprint: %s) sealed with Windows DPAPI.",
            self.key_id,
            self.key_fingerprint,
        )

    def rotate_key(self, new_key_id: str, reason: str = "Key rotation") -> Tuple[str, str]:
        """
        Rotates signing keys: revokes existing key in trust store, generates fresh keypair,
        and registers the new key as ACTIVE.
        Returns: (new_key_id, new_key_fingerprint).
        """
        old_key_id = self.key_id
        old_fp = self.key_fingerprint
        self.trust_store.revoke_key(old_fp, reason=reason)

        self.key_id = new_key_id
        self._generate_fresh_keypair()
        logger.info("Successfully rotated key from '%s' to '%s'.", old_key_id, new_key_id)
        return self.key_id, self.key_fingerprint

    def get_public_key_pem(self) -> str:
        """Returns the public key in standard PEM format."""
        if self._public_key_pem is None:
            raise CryptoSignerError("Public key is not initialized.")
        return self._public_key_pem

    def sign_payload(self, payload: bytes) -> str:
        """
        Signs arbitrary binary payload using ECDSA SECP256R1 and SHA-256.
        Returns hex-encoded DER signature.
        """
        if self._private_key is None:
            raise CryptoSignerError("Private signing key is not initialized.")

        signature_der = self._private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
        return signature_der.hex()

    @staticmethod
    def verify_signature(
        payload: bytes,
        signature_hex: str,
        public_key_pem: str,
        trust_store: Optional[TrustedKeyStore] = None,
    ) -> bool:
        """
        Verifies ECDSA digital signature using the provided public key PEM.
        If trust_store is supplied, also verifies that the public key is trusted and active.
        """
        if trust_store is not None:
            is_trusted, _, reason = trust_store.is_key_trusted(public_key_pem)
            if not is_trusted:
                logger.warning("Signature verification rejected: Untrusted signing identity (%s)", reason)
                return False

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
