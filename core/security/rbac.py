"""
Role-Based Access Control (RBAC) Engine (Phase 14 - Module B).
Manages 10 default hierarchical surveillance roles, 22 operational permission codes,
backend authorization checking, privilege escalation prevention, and least-privilege defaults.
"""

from typing import Dict, Any, List, Set, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.logging.logger import get_logger
from database.database_manager import db_manager
from database.models.users import Role, Permission, RolePermission, User

logger = get_logger("rbac_service")


class PermissionCodes:
    """Canonical 22 Permission Codes across 15 Operational Subsystems."""
    # 1. Dashboard
    DASHBOARD_VIEW = "dashboard:view"

    # 2. Live Monitoring & Camera Control
    LIVE_VIEW = "live:view"
    CAMERA_MANAGE = "camera:manage"
    PTZ_CONTROL = "ptz:control"

    # 3. Playback & Recordings
    PLAYBACK_VIEW = "playback:view"
    PLAYBACK_EXPORT = "playback:export"

    # 4. AI Video Analytics
    AI_VIEW = "ai:view"
    AI_CONFIGURE = "ai:configure"

    # 5. Face & ANPR Biometrics
    BIOMETRICS_VIEW = "biometrics:view"
    BIOMETRICS_MANAGE = "biometrics:manage"

    # 6. Alarms & Incidents
    ALARM_VIEW = "alarm:view"
    ALARM_MANAGE = "alarm:manage"

    # 7. Forensics & Evidence Locker
    FORENSIC_VIEW = "forensic:view"
    EVIDENCE_EXPORT = "evidence:export"

    # 8. Storage Management
    STORAGE_MANAGE = "storage:manage"

    # 9. Network Intelligence
    NETWORK_VIEW = "network:view"
    NETWORK_SCAN = "network:scan"

    # 10. Security Administration
    USER_MANAGE = "user:manage"
    ROLE_MANAGE = "role:manage"

    # 11. Audit & Export
    AUDIT_VIEW = "audit:view"
    AUDIT_EXPORT = "audit:export"

    # 12. System Configuration
    SYSTEM_CONFIG = "system:config"


ALL_PERMISSIONS = [
    (PermissionCodes.DASHBOARD_VIEW, "View System Dashboard", "dashboard", "Access operational overview and health telemetry."),
    (PermissionCodes.LIVE_VIEW, "Live Camera View", "live", "Monitor real-time camera grid video feeds."),
    (PermissionCodes.CAMERA_MANAGE, "Manage Cameras & Devices", "camera", "Add, edit, and configure cameras, NVRs, and RTSP streams."),
    (PermissionCodes.PTZ_CONTROL, "PTZ Camera Control", "camera", "Control pan, tilt, zoom, presets, and camera direction."),
    (PermissionCodes.PLAYBACK_VIEW, "View Recorded Playback", "playback", "Search, scrub, and replay recorded surveillance segments."),
    (PermissionCodes.PLAYBACK_EXPORT, "Export Video Clips", "playback", "Download and export surveillance MP4 clips."),
    (PermissionCodes.AI_VIEW, "View AI Analytics", "ai", "Inspect real-time detection, tracking, and behaviour metadata."),
    (PermissionCodes.AI_CONFIGURE, "Configure AI Analytics", "ai", "Create and modify intrusion zones, tripwires, and rules."),
    (PermissionCodes.BIOMETRICS_VIEW, "View Face & ANPR Logs", "biometrics", "View recognized number plates and authorized face candidate matches."),
    (PermissionCodes.BIOMETRICS_MANAGE, "Manage Biometric Vault", "biometrics", "Enroll and manage face templates and vehicle watchlists."),
    (PermissionCodes.ALARM_VIEW, "View Incident Alarms", "alarm", "Access unified alarm center, active alerts, and incident queue."),
    (PermissionCodes.ALARM_MANAGE, "Acknowledge & Triage Alarms", "alarm", "Acknowledge, assign, resolve, and escalate alarms."),
    (PermissionCodes.FORENSIC_VIEW, "View Forensic Integrity", "forensic", "Inspect video authenticity, discontinuity analysis, and Evidence Locker."),
    (PermissionCodes.EVIDENCE_EXPORT, "Export Evidence Packages", "forensic", "Generate court-admissible cryptographically signed evidence packages."),
    (PermissionCodes.STORAGE_MANAGE, "Manage Storage Pools", "storage", "Configure storage volumes, quotas, NAS links, and failover targets."),
    (PermissionCodes.NETWORK_VIEW, "View Network Intelligence", "network", "Inspect network topology, device inventory, and bandwidth telemetry."),
    (PermissionCodes.NETWORK_SCAN, "Execute Subnet Scans", "network", "Perform authorized network discovery, diagnostics, and security audits."),
    (PermissionCodes.USER_MANAGE, "Manage User Accounts", "admin", "Create, edit, lock, unlock, and deactivate user accounts."),
    (PermissionCodes.ROLE_MANAGE, "Manage Roles & Permissions", "admin", "Configure RBAC roles, permission assignments, and access policies."),
    (PermissionCodes.AUDIT_VIEW, "View Audit Trail", "audit", "Query and inspect immutable system and operational audit logs."),
    (PermissionCodes.AUDIT_EXPORT, "Export Audit Reports", "audit", "Generate and export PDF/CSV compliance audit reports."),
    (PermissionCodes.SYSTEM_CONFIG, "System Settings", "system", "Configure system-wide networking, TLS/HTTPS, and hardware parameters."),
]


# 10 Standard Hierarchical Role Definitions
DEFAULT_ROLES: Dict[str, Dict[str, Any]] = {
    "Super Administrator": {
        "description": "Unrestricted system control, cryptographic root authority, and user/role administration.",
        "is_system": True,
        "permissions": [code for code, _, _, _ in ALL_PERMISSIONS],
    },
    "Administrator": {
        "description": "Full administrative control over devices, storage, users, and security configurations.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW, PermissionCodes.CAMERA_MANAGE,
            PermissionCodes.PTZ_CONTROL, PermissionCodes.PLAYBACK_VIEW, PermissionCodes.PLAYBACK_EXPORT,
            PermissionCodes.AI_VIEW, PermissionCodes.AI_CONFIGURE, PermissionCodes.BIOMETRICS_VIEW,
            PermissionCodes.BIOMETRICS_MANAGE, PermissionCodes.ALARM_VIEW, PermissionCodes.ALARM_MANAGE,
            PermissionCodes.FORENSIC_VIEW, PermissionCodes.EVIDENCE_EXPORT, PermissionCodes.STORAGE_MANAGE,
            PermissionCodes.NETWORK_VIEW, PermissionCodes.NETWORK_SCAN, PermissionCodes.USER_MANAGE,
            PermissionCodes.ROLE_MANAGE, PermissionCodes.AUDIT_VIEW, PermissionCodes.AUDIT_EXPORT,
            PermissionCodes.SYSTEM_CONFIG,
        ],
    },
    "Security Manager": {
        "description": "Security operational supervision, policy adjustments, and forensic incident investigation.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW, PermissionCodes.CAMERA_MANAGE,
            PermissionCodes.PTZ_CONTROL, PermissionCodes.PLAYBACK_VIEW, PermissionCodes.PLAYBACK_EXPORT,
            PermissionCodes.AI_VIEW, PermissionCodes.AI_CONFIGURE, PermissionCodes.BIOMETRICS_VIEW,
            PermissionCodes.BIOMETRICS_MANAGE, PermissionCodes.ALARM_VIEW, PermissionCodes.ALARM_MANAGE,
            PermissionCodes.FORENSIC_VIEW, PermissionCodes.EVIDENCE_EXPORT, PermissionCodes.NETWORK_VIEW,
            PermissionCodes.AUDIT_VIEW, PermissionCodes.AUDIT_EXPORT,
        ],
    },
    "Supervisor": {
        "description": "Operational monitoring, alert management, operator oversight, and shift reporting.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW, PermissionCodes.PTZ_CONTROL,
            PermissionCodes.PLAYBACK_VIEW, PermissionCodes.PLAYBACK_EXPORT, PermissionCodes.AI_VIEW,
            PermissionCodes.BIOMETRICS_VIEW, PermissionCodes.ALARM_VIEW, PermissionCodes.ALARM_MANAGE,
            PermissionCodes.FORENSIC_VIEW, PermissionCodes.NETWORK_VIEW, PermissionCodes.AUDIT_VIEW,
        ],
    },
    "CCTV Operator": {
        "description": "Live surveillance monitoring, PTZ joystick operations, and real-time alarm handling.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW, PermissionCodes.PTZ_CONTROL,
            PermissionCodes.PLAYBACK_VIEW, PermissionCodes.ALARM_VIEW, PermissionCodes.ALARM_MANAGE,
        ],
    },
    "Investigator": {
        "description": "Historical footage analysis, forensic timeline scrubbing, and evidence export.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW, PermissionCodes.PLAYBACK_VIEW,
            PermissionCodes.PLAYBACK_EXPORT, PermissionCodes.AI_VIEW, PermissionCodes.BIOMETRICS_VIEW,
            PermissionCodes.ALARM_VIEW, PermissionCodes.FORENSIC_VIEW, PermissionCodes.EVIDENCE_EXPORT,
            PermissionCodes.AUDIT_VIEW,
        ],
    },
    "Evidence Manager": {
        "description": "Evidence Locker administration, cryptographic signatures, and chain-of-custody exports.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.PLAYBACK_VIEW, PermissionCodes.PLAYBACK_EXPORT,
            PermissionCodes.FORENSIC_VIEW, PermissionCodes.EVIDENCE_EXPORT, PermissionCodes.AUDIT_VIEW,
            PermissionCodes.AUDIT_EXPORT,
        ],
    },
    "Technician": {
        "description": "Physical camera onboarding, network diagnostics, storage pool setup, and system diagnostics.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW, PermissionCodes.CAMERA_MANAGE,
            PermissionCodes.PTZ_CONTROL, PermissionCodes.STORAGE_MANAGE, PermissionCodes.NETWORK_VIEW,
            PermissionCodes.NETWORK_SCAN, PermissionCodes.SYSTEM_CONFIG,
        ],
    },
    "Auditor": {
        "description": "Independent read-only access to audit logs, compliance reports, and integrity records.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.FORENSIC_VIEW, PermissionCodes.AUDIT_VIEW,
            PermissionCodes.AUDIT_EXPORT,
        ],
    },
    "Read-Only Viewer": {
        "description": "Restricted live viewing of permitted camera streams with zero modification rights.",
        "is_system": True,
        "permissions": [
            PermissionCodes.DASHBOARD_VIEW, PermissionCodes.LIVE_VIEW,
        ],
    },
}


class AccessDeniedError(PermissionError):
    """Raised when an operation is rejected due to insufficient RBAC permissions."""
    pass


class RBACService:
    """Manages role hierarchies, permission mapping, and authorization decisions."""

    @staticmethod
    def seed_permissions_and_roles(session: Session) -> None:
        """Seeds all 22 permissions and 10 default roles if missing."""
        # 1. Seed Permissions
        perm_map: Dict[str, Permission] = {}
        for code, name, module, desc in ALL_PERMISSIONS:
            existing_perm = session.query(Permission).filter_by(code=code).first()
            if not existing_perm:
                existing_perm = Permission(code=code, name=name, module=module, description=desc)
                session.add(existing_perm)
                logger.debug("Seeded permission: %s", code)
            perm_map[code] = existing_perm

        session.flush()

        # 2. Seed Roles and Mappings
        for role_name, role_info in DEFAULT_ROLES.items():
            existing_role = session.query(Role).filter_by(name=role_name).first()
            if not existing_role:
                existing_role = Role(
                    name=role_name,
                    description=role_info["description"],
                    is_system=role_info["is_system"]
                )
                session.add(existing_role)
                session.flush()
                logger.info("Seeded default role: %s", role_name)

            # Ensure role has its configured permissions
            assigned_codes = {
                rp.permission.code for rp in existing_role.permissions if rp.permission
            }
            for code in role_info["permissions"]:
                if code not in assigned_codes and code in perm_map:
                    perm = perm_map[code]
                    rp = RolePermission(role_id=existing_role.id, permission_id=perm.id)
                    session.add(rp)

        session.commit()

    @staticmethod
    def get_user_permissions(user_id: str, session: Optional[Session] = None) -> Set[str]:
        """Returns the complete set of permission codes assigned to a user's role."""
        def _query(sess: Session) -> Set[str]:
            user = sess.query(User).filter_by(id=user_id, is_active=True).first()
            if not user or not user.role:
                return set()
            return {
                rp.permission.code
                for rp in user.role.permissions
                if rp.permission and not rp.is_deleted
            }

        if session:
            return _query(session)
        with db_manager.get_session() as sess:
            return _query(sess)

    @staticmethod
    def has_permission(user_id: str, permission_code: str, session: Optional[Session] = None) -> bool:
        """Checks if a user holds a specific permission code."""
        permissions = RBACService.get_user_permissions(user_id, session)
        return permission_code in permissions

    @staticmethod
    def require_permission(user_id: str, permission_code: str, session: Optional[Session] = None) -> None:
        """Enforces a permission check; raises AccessDeniedError if unauthorized."""
        if not RBACService.has_permission(user_id, permission_code, session):
            logger.warning("Access denied: User %s lacks permission %s", user_id, permission_code)
            raise AccessDeniedError(f"Access Denied: You do not possess the required permission '{permission_code}'.")

    @staticmethod
    def get_all_roles(session: Optional[Session] = None) -> List[Dict[str, Any]]:
        """Lists all system and custom roles with user counts and permission lists."""
        def _query(sess: Session) -> List[Dict[str, Any]]:
            roles = sess.query(Role).filter_by(is_deleted=False).all()
            result = []
            for role in roles:
                perms = [
                    {"code": rp.permission.code, "name": rp.permission.name, "module": rp.permission.module}
                    for rp in role.permissions
                    if rp.permission
                ]
                user_count = sess.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(
                        User.role_id == role.id,
                        User.is_deleted.is_(False)
                    )
                ) or 0
                result.append({
                    "id": role.id,
                    "name": role.name,
                    "description": role.description,
                    "is_system": role.is_system,
                    "user_count": user_count,
                    "permissions": perms,
                })
            return result

        if session:
            return _query(session)
        with db_manager.get_session() as sess:
            return _query(sess)


# Global RBAC singleton
rbac_service = RBACService()
