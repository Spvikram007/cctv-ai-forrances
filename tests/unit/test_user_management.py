"""
Unit Tests for User Management and Password Security (Phase 14 - Module A).
"""

import pytest
from datetime import datetime, timezone, timedelta

from database.database_manager import db_manager
from database.models.users import User, Role, UserSession
from core.security.password import (
    hash_password,
    verify_password,
    validate_password_strength,
)
from core.security.user_service import user_service, MAX_FAILED_ATTEMPTS


def test_password_complexity_validation():
    """Verifies that password complexity rules enforce enterprise security policies."""
    # Too short
    ok, msg = validate_password_strength("Short1!")
    assert not ok
    assert "at least 8" in msg

    # Missing uppercase
    ok, msg = validate_password_strength("lowercase123!")
    assert not ok
    assert "uppercase" in msg

    # Missing lowercase
    ok, msg = validate_password_strength("UPPERCASE123!")
    assert not ok
    assert "lowercase" in msg

    # Missing digit
    ok, msg = validate_password_strength("NoDigitsHere!")
    assert not ok
    assert "digit" in msg

    # Missing special char
    ok, msg = validate_password_strength("NoSymbols1234")
    assert not ok
    assert "special character" in msg

    # Valid password
    ok, msg = validate_password_strength("Valid@Pass2026")
    assert ok


def test_bcrypt_hashing_and_verification():
    """Verifies bcrypt hashing and matching."""
    pwd = "Enterprise#Password2026"
    hashed = hash_password(pwd)
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert hashed != pwd

    # Valid check
    valid, needs_rehash = verify_password(pwd, hashed)
    assert valid
    assert not needs_rehash

    # Invalid check
    valid, _ = verify_password("WrongPassword123!", hashed)
    assert not valid


def test_legacy_sha256_hash_upgrade():
    """Verifies that legacy SHA-256 hashes are verified and flagged for rehash."""
    import hashlib
    raw = "Admin@SecureOffline2026"
    legacy_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    valid, needs_rehash = verify_password(raw, legacy_sha)
    assert valid
    assert needs_rehash

    # Wrong password with legacy sha
    valid, _ = verify_password("WrongPass123!", legacy_sha)
    assert not valid


def test_user_authentication_flow():
    """Tests successful authentication, session creation, and last login updates."""
    with db_manager.get_session() as session:
        role = session.query(Role).filter_by(name="Operator").first() or \
               session.query(Role).filter_by(name="CCTV Operator").first()
        assert role is not None
        role_id = role.id

    username = f"test_op_{datetime.now().microsecond}"
    password = "TestOperator@2026"
    ok, user_dict, msg = user_service.create_user(
        username=username,
        password=password,
        full_name="Test Operator",
        role_id=role_id,
        email=f"{username}@cctv.local"
    )
    assert ok
    assert user_dict["username"] == username
    assert "password_hash" not in user_dict

    # Successful login
    ok, sess_dict, msg = user_service.authenticate(username, password)
    assert ok
    assert sess_dict is not None
    assert sess_dict["username"] == username
    assert "session_token" in sess_dict
    token = sess_dict["session_token"]

    # Validate session
    val_sess = user_service.validate_session(token)
    assert val_sess is not None
    assert val_sess["username"] == username

    # Logout
    logout_ok = user_service.logout(token)
    assert logout_ok

    # Validate after logout (should fail)
    val_after = user_service.validate_session(token)
    assert val_after is None


def test_account_lockout_after_consecutive_failures():
    """Verifies that 5 consecutive failed logins lock an account for 15 minutes."""
    with db_manager.get_session() as session:
        role = session.query(Role).filter_by(name="CCTV Operator").first() or \
               session.query(Role).filter_by(name="Operator").first()
        role_id = role.id

    username = f"lock_test_{datetime.now().microsecond}"
    password = "LockPassword@2026"
    ok, _, _ = user_service.create_user(
        username=username,
        password=password,
        full_name="Lockout Target",
        role_id=role_id
    )
    assert ok

    # Fail 5 times
    for i in range(MAX_FAILED_ATTEMPTS):
        ok, _, msg = user_service.authenticate(username, "BadPassword123!")
        assert not ok

    # 6th attempt should be blocked by account lockout
    ok, sess, msg = user_service.authenticate(username, password)
    assert not ok
    assert "Account is locked" in msg

    # Admin unlocks user
    with db_manager.get_session() as session:
        u = session.query(User).filter_by(username=username).first()
        uid = u.id

    unlock_ok, unlock_msg = user_service.unlock_user(None, uid)
    assert unlock_ok

    # Now login succeeds
    ok, sess, msg = user_service.authenticate(username, password)
    assert ok
    assert sess is not None


def test_super_admin_lockout_immunity():
    """Verifies that Super Administrators are immune to brute-force account lockout."""
    with db_manager.get_session() as session:
        role = session.query(Role).filter_by(name="Super Administrator").first()
        assert role is not None
        role_id = role.id

    username = f"super_immune_{datetime.now().microsecond}"
    password = "SuperPassword@2026"
    ok, _, _ = user_service.create_user(
        username=username,
        password=password,
        full_name="Super Immune Admin",
        role_id=role_id
    )
    assert ok

    # Fail 7 times (greater than MAX_FAILED_ATTEMPTS)
    for _ in range(7):
        ok, _, _ = user_service.authenticate(username, "WrongGuess123!")
        assert not ok

    # Super Admin can still log in immediately with correct password
    ok, sess, msg = user_service.authenticate(username, password)
    assert ok
    assert sess is not None
    assert sess["role_name"] == "Super Administrator"
