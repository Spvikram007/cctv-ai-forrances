"""
Password Hashing and Complexity Validation Service (Phase 14).
Implements industry-standard bcrypt hashing with legacy SHA-256 upgrade path
and rigorous credential complexity validation.
"""

import re
import hashlib
from typing import Tuple
import bcrypt


MIN_PASSWORD_LENGTH = 8
BCRYPT_ROUNDS = 12


def hash_password(plaintext: str) -> str:
    """Hashes a plaintext password using bcrypt with standard salt rounds."""
    if not plaintext:
        raise ValueError("Password cannot be empty.")
    # bcrypt accepts bytes
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed_bytes = bcrypt.hashpw(plaintext.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plaintext: str, stored_hash: str) -> Tuple[bool, bool]:
    """
    Verifies a plaintext password against the stored password hash.
    
    Returns:
        (is_valid, needs_rehash):
        is_valid: True if password matches stored hash.
        needs_rehash: True if stored hash used legacy SHA-256 and should be upgraded to bcrypt.
    """
    if not plaintext or not stored_hash:
        return False, False

    # 1. Check if stored hash is a legacy SHA-256 hash (64 hex chars, no $ prefix)
    if len(stored_hash) == 64 and not stored_hash.startswith("$"):
        computed_sha = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        if computed_sha.lower() == stored_hash.lower():
            return True, True  # Match! Needs upgrade to bcrypt
        return False, False

    # 2. Bcrypt verification
    try:
        is_valid = bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("utf-8"))
        return is_valid, False
    except Exception:
        # Fallback in case of corrupted or unrecognized hash format
        return False, False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Enforces enterprise credential security rules:
    - Minimum 8 characters
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one numerical digit (0-9)
    - At least one special character (!@#$%^&*()-_=+[]{}|;:,.<>?)
    """
    if not password:
        return False, "Password cannot be empty."
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one numerical digit."
    if not re.search(r"[!@#$%^&*()_\-+=\[\]{}|;:,.<>?/~`]", password):
        return False, "Password must contain at least one special character."

    return True, "Password meets all complexity requirements."
