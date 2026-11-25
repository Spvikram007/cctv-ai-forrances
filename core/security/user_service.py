"""
User Management and Authentication Service (Phase 14 - Module A).
Implements user lifecycle administration, secure bcrypt credential verification,
account lockout tracking, session expiration, and Super Administrator lockout immunity.
"""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from core.logging.logger import get_logger
from database.database_manager import db_manager
from database.models.users import User, Role, UserSession
from core.security.password import (
    hash_password,
    verify_password,
    validate_password_strength,
)

logger = get_logger("user_service")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
SESSION_LIFETIME_MINUTES = 30


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensures datetime object is timezone-aware in UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class UserService:
    """Manages user authentication, accounts, sessions, and credential security."""

    def __init__(self) -> None:
        pass

    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str = "127.0.0.1",
        user_agent: str = "PySide6-Desktop"
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Authenticates a user against stored credentials.
        
        Returns:
            (success, session_dict, error_message)
        """
        from core.security.audit_service import audit_service

        if not username or not password:
            return False, None, "Username and password are required."

        now = datetime.now(timezone.utc)

        with db_manager.get_session() as session:
            user = session.query(User).filter_by(username=username, is_deleted=False).first()
            if not user:
                audit_service.log_event(
                    action="LOGIN_FAILED",
                    category="AUTH",
                    resource_type="user",
                    resource_id=username,
                    status="FAILED",
                    username=username,
                    ip_address=ip_address,
                    details={"reason": "User not found"}
                )
                return False, None, "Invalid username or password."

            # 1. Check account active status
            if not user.is_active:
                audit_service.log_event(
                    action="LOGIN_BLOCKED_INACTIVE",
                    category="AUTH",
                    resource_type="user",
                    resource_id=user.id,
                    status="DENIED",
                    username=user.username,
                    ip_address=ip_address,
                    details={"reason": "Account is deactivated"}
                )
                return False, None, "Account is deactivated. Contact a System Administrator."

            # 2. Check account lockout status
            is_super_admin = user.role and user.role.name == "Super Administrator"
            user_locked = ensure_utc(user.locked_until)
            if user_locked and user_locked > now:
                # Super Administrator is immune to lockout attacks
                if not is_super_admin:
                    remaining_secs = int((user_locked - now).total_seconds())
                    remaining_mins = max(1, remaining_secs // 60)
                    audit_service.log_event(
                        action="LOGIN_BLOCKED_LOCKOUT",
                        category="AUTH",
                        resource_type="user",
                        resource_id=user.id,
                        status="DENIED",
                        username=user.username,
                        ip_address=ip_address,
                        details={"remaining_minutes": remaining_mins}
                    )
                    return False, None, f"Account is locked due to excessive failed attempts. Try again in {remaining_mins} minute(s)."

            # 3. Verify Password
            is_valid, needs_rehash = verify_password(password, user.password_hash)

            if not is_valid:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                    if not is_super_admin:
                        user.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                        logger.warning("Account %s locked out until %s after %d failed attempts.",
                                       user.username, user.locked_until, user.failed_login_attempts)
                    else:
                        logger.warning("Super Administrator %s exceeded %d failed attempts but remains immune to lockout.",
                                       user.username, user.failed_login_attempts)

                session.commit()
                audit_service.log_event(
                    action="LOGIN_FAILED",
                    category="AUTH",
                    resource_type="user",
                    resource_id=user.id,
                    status="FAILED",
                    username=user.username,
                    ip_address=ip_address,
                    details={"failed_attempts": user.failed_login_attempts, "locked": bool(user.locked_until)}
                )
                return False, None, "Invalid username or password."

            # 4. Success! Upgrade legacy hash if necessary
            if needs_rehash:
                user.password_hash = hash_password(password)
                logger.info("Upgraded legacy SHA-256 password hash to bcrypt for user '%s'.", user.username)

            # Reset lockout counters
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login_at = now
            user.last_activity_at = now

            # 5. Create Session
            token = secrets.token_urlsafe(32)
            expires_at = now + timedelta(minutes=SESSION_LIFETIME_MINUTES)
            user_session = UserSession(
                user_id=user.id,
                session_token=token,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=expires_at,
                is_revoked=False,
                last_seen_at=now
            )
            session.add(user_session)
            session.commit()

            role_name = user.role.name if user.role else "Viewer"

            audit_service.log_event(
                action="LOGIN_SUCCESS",
                category="AUTH",
                resource_type="user",
                resource_id=user.id,
                status="SUCCESS",
                username=user.username,
                session_id=user_session.id,
                ip_address=ip_address,
                details={"role": role_name}
            )

            session_dict = {
                "session_id": user_session.id,
                "session_token": token,
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "role_id": user.role_id,
                "role_name": role_name,
                "expires_at": expires_at.isoformat(),
            }
            return True, session_dict, "Login successful."

    def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """Validates an active session token and extends last_seen_at timestamp."""
        if not token:
            return None

        now = datetime.now(timezone.utc)
        with db_manager.get_session() as session:
            user_session = session.query(UserSession).filter_by(
                session_token=token, is_revoked=False
            ).first()

            if not user_session:
                return None

            expires_at_utc = ensure_utc(user_session.expires_at)
            if expires_at_utc and expires_at_utc < now:
                user_session.is_revoked = True
                session.commit()
                return None

            user = user_session.user
            if not user or not user.is_active or user.is_deleted:
                return None

            # Refresh last activity
            user_session.last_seen_at = now
            user.last_activity_at = now
            session.commit()

            return {
                "session_id": user_session.id,
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "role_id": user.role_id,
                "role_name": user.role.name if user.role else "Viewer",
                "expires_at": user_session.expires_at.isoformat(),
            }

    def logout(self, token: str) -> bool:
        """Revokes an active session."""
        from core.security.audit_service import audit_service

        with db_manager.get_session() as session:
            user_session = session.query(UserSession).filter_by(session_token=token).first()
            if user_session:
                user_session.is_revoked = True
                username = user_session.user.username if user_session.user else "unknown"
                session.commit()
                audit_service.log_event(
                    action="LOGOUT",
                    category="AUTH",
                    resource_type="user",
                    resource_id=user_session.user_id,
                    status="SUCCESS",
                    username=username,
                    session_id=user_session.id,
                    details={"session_token_prefix": token[:8] + "..."}
                )
                return True
        return False

    def create_user(
        self,
        username: str,
        password: str,
        full_name: str,
        role_id: str,
        email: Optional[str] = None,
        operator_user_id: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Creates a new user account with validated credentials."""
        from core.security.audit_service import audit_service
        from core.security.rbac import rbac_service

        if operator_user_id:
            rbac_service.require_permission(operator_user_id, "user:manage")

        # Validation
        if not username or not full_name or not role_id:
            return False, None, "Username, full name, and role are required."

        is_valid, msg = validate_password_strength(password)
        if not is_valid:
            return False, None, msg

        with db_manager.get_session() as session:
            # Check duplicate username
            existing = session.query(User).filter_by(username=username, is_deleted=False).first()
            if existing:
                return False, None, f"Username '{username}' is already in use."

            role = session.query(Role).filter_by(id=role_id, is_deleted=False).first()
            if not role:
                return False, None, "Selected role does not exist."

            # Privilege escalation protection: only Super Admin can create Super Admins
            if role.name == "Super Administrator" and operator_user_id:
                op_user = session.query(User).filter_by(id=operator_user_id).first()
                if not op_user or not op_user.role or op_user.role.name != "Super Administrator":
                    return False, None, "Only a Super Administrator can assign the Super Administrator role."

            new_user = User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role_id=role.id,
                is_active=True,
                password_changed_at=datetime.now(timezone.utc)
            )
            session.add(new_user)
            session.commit()

            audit_service.log_event(
                action="USER_CREATED",
                category="USER",
                resource_type="user",
                resource_id=new_user.id,
                status="SUCCESS",
                username=new_user.username,
                details={"created_by": operator_user_id, "role": role.name}
            )

            return True, self._user_to_dict(new_user, role.name), "User created successfully."

    def update_user(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        email: Optional[str] = None,
        role_id: Optional[str] = None,
        is_active: Optional[bool] = None,
        operator_user_id: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Updates user profile or role."""
        from core.security.audit_service import audit_service
        from core.security.rbac import rbac_service

        if operator_user_id:
            rbac_service.require_permission(operator_user_id, "user:manage")

        with db_manager.get_session() as session:
            user = session.query(User).filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return False, None, "User not found."

            old_role = user.role.name if user.role else "Unknown"

            # Prevent deactivating or demoting the last active Super Administrator
            if user.role and user.role.name == "Super Administrator":
                if is_active is False or (role_id and role_id != user.role_id):
                    active_super_admins = session.query(User).join(Role).filter(
                        Role.name == "Super Administrator",
                        User.is_active == True,
                        User.is_deleted == False
                    ).count()
                    if active_super_admins <= 1:
                        return False, None, "Cannot deactivate or change role of the last active Super Administrator."

            if full_name:
                user.full_name = full_name
            if email is not None:
                user.email = email
            if is_active is not None:
                user.is_active = is_active
            if role_id:
                new_role = session.query(Role).filter_by(id=role_id, is_deleted=False).first()
                if not new_role:
                    return False, None, "Selected role does not exist."
                # Escalation check
                if new_role.name == "Super Administrator" and operator_user_id:
                    op_user = session.query(User).filter_by(id=operator_user_id).first()
                    if not op_user or not op_user.role or op_user.role.name != "Super Administrator":
                        return False, None, "Only a Super Administrator can assign the Super Administrator role."
                user.role_id = new_role.id

            session.commit()

            role_name = user.role.name if user.role else "Unknown"
            audit_service.log_event(
                action="USER_UPDATED",
                category="USER",
                resource_type="user",
                resource_id=user.id,
                status="SUCCESS",
                username=user.username,
                details={"updated_by": operator_user_id, "new_role": role_name, "is_active": user.is_active}
            )

            return True, self._user_to_dict(user, role_name), "User updated successfully."

    def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """Allows a user to change their own password upon verifying current credentials."""
        from core.security.audit_service import audit_service

        is_valid, msg = validate_password_strength(new_password)
        if not is_valid:
            return False, msg

        with db_manager.get_session() as session:
            user = session.query(User).filter_by(id=user_id, is_deleted=False).first()
            if not user:
                return False, "User not found."

            valid_old, _ = verify_password(old_password, user.password_hash)
            if not valid_old:
                return False, "Current password verification failed."

            user.password_hash = hash_password(new_password)
            user.password_changed_at = datetime.now(timezone.utc)
            # Revoke other sessions for security
            session.query(UserSession).filter_by(user_id=user.id).update({"is_revoked": True})
            session.commit()

            audit_service.log_event(
                action="PASSWORD_CHANGED",
                category="AUTH",
                resource_type="user",
                resource_id=user.id,
                status="SUCCESS",
                username=user.username,
                details={"reason": "User self-service password change"}
            )
            return True, "Password changed successfully. All previous sessions revoked."

    def admin_reset_password(
        self,
        operator_user_id: Optional[str],
        target_user_id: str,
        new_password: str
    ) -> Tuple[bool, str]:
        """Allows an authorized administrator to reset another user's password."""
        from core.security.audit_service import audit_service
        from core.security.rbac import rbac_service

        if operator_user_id:
            rbac_service.require_permission(operator_user_id, "user:manage")

        is_valid, msg = validate_password_strength(new_password)
        if not is_valid:
            return False, msg

        with db_manager.get_session() as session:
            target_user = session.query(User).filter_by(id=target_user_id, is_deleted=False).first()
            if not target_user:
                return False, "User not found."

            # Non-super admins cannot reset Super Admin passwords
            if target_user.role and target_user.role.name == "Super Administrator":
                op_user = session.query(User).filter_by(id=operator_user_id).first()
                if not op_user or not op_user.role or op_user.role.name != "Super Administrator":
                    return False, "Only a Super Administrator can reset a Super Administrator password."

            target_user.password_hash = hash_password(new_password)
            target_user.password_changed_at = datetime.now(timezone.utc)
            target_user.failed_login_attempts = 0
            target_user.locked_until = None
            session.query(UserSession).filter_by(user_id=target_user.id).update({"is_revoked": True})
            session.commit()

            audit_service.log_event(
                action="PASSWORD_RESET_ADMIN",
                category="USER",
                resource_type="user",
                resource_id=target_user.id,
                status="SUCCESS",
                username=target_user.username,
                details={"reset_by": operator_user_id}
            )
            return True, f"Password reset successfully for user '{target_user.username}'."

    def unlock_user(self, operator_user_id: Optional[str], target_user_id: str) -> Tuple[bool, str]:
        """Unlocks an account that was locked due to excessive failed attempts."""
        from core.security.audit_service import audit_service
        from core.security.rbac import rbac_service

        if operator_user_id:
            rbac_service.require_permission(operator_user_id, "user:manage")

        with db_manager.get_session() as session:
            user = session.query(User).filter_by(id=target_user_id, is_deleted=False).first()
            if not user:
                return False, "User not found."

            user.failed_login_attempts = 0
            user.locked_until = None
            session.commit()

            audit_service.log_event(
                action="USER_UNLOCKED",
                category="USER",
                resource_type="user",
                resource_id=user.id,
                status="SUCCESS",
                username=user.username,
                details={"unlocked_by": operator_user_id}
            )
            return True, f"User '{user.username}' unlocked successfully."

    def list_users(self, session: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Lists all active and inactive users with role information and zero secrets."""
        def _query(sess: Session) -> List[Dict[str, Any]]:
            users = sess.query(User).filter_by(is_deleted=False).all()
            return [self._user_to_dict(u, u.role.name if u.role else "Unknown") for u in users]

        if session:
            return _query(session)
        with db_manager.get_session() as sess:
            return _query(sess)

    def list_active_sessions(self) -> List[Dict[str, Any]]:
        """Lists all currently valid, unexpired sessions across the platform."""
        now = datetime.now(timezone.utc)
        with db_manager.get_session() as session:
            sessions = session.query(UserSession).join(User).filter(
                UserSession.is_revoked == False,
                UserSession.expires_at > now
            ).all()

            return [
                {
                    "session_id": s.id,
                    "user_id": s.user_id,
                    "username": s.user.username if s.user else "Unknown",
                    "role_name": s.user.role.name if s.user and s.user.role else "Unknown",
                    "ip_address": s.ip_address,
                    "user_agent": s.user_agent,
                    "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else s.created_at.isoformat(),
                    "expires_at": s.expires_at.isoformat(),
                }
                for s in sessions
            ]

    def _user_to_dict(self, user: User, role_name: str) -> Dict[str, Any]:
        """Serializes user model to dictionary without exposing password hash."""
        now = datetime.now(timezone.utc)
        locked_utc = ensure_utc(user.locked_until)
        is_locked = bool(locked_utc and locked_utc > now)
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role_id": user.role_id,
            "role_name": role_name,
            "is_active": user.is_active,
            "is_locked": is_locked,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
            "failed_attempts": user.failed_login_attempts,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "last_activity_at": user.last_activity_at.isoformat() if user.last_activity_at else None,
            "created_at": user.created_at.isoformat(),
        }


# Global User Management singleton
user_service = UserService()
