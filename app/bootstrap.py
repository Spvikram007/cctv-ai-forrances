"""
Application Bootstrap and Initialization Sequence.
Coordinates hardware probing, logging initialization, storage directory creation,
database migrations/seeding, and worker lifecycle startup.
"""

import hashlib
from typing import Dict, Any

from core.logging.logger import setup_logging, get_logger
from app.configuration import get_settings
from app.application_state import app_state
from core.hardware.detector import HardwareDetector
from database.database_manager import db_manager
from database.models.users import Role, User

logger = get_logger("bootstrap")


def seed_initial_security_data() -> None:
    """Seeds default RBAC roles and default local administrator if database is fresh."""
    default_roles = [
        ("Administrator", "Unrestricted system control and configuration.", True),
        ("Supervisor", "Operational monitoring, alert management, and team oversight.", True),
        ("Operator", "Live camera view, PTZ control, and manual recording.", True),
        ("Investigator", "Playback, forensic analysis, evidence export, and reporting.", True),
        ("Viewer", "Read-only live viewing of authorized camera streams.", True),
    ]

    with db_manager.get_session() as session:
        # 1. Seed Roles
        for role_name, desc, is_sys in default_roles:
            existing_role = session.query(Role).filter_by(name=role_name).first()
            if not existing_role:
                new_role = Role(name=role_name, description=desc, is_system=is_sys)
                session.add(new_role)
                logger.info("Seeded default role: %s", role_name)

        session.flush()

        # 2. Seed Default Admin if no users exist
        admin_count = session.query(User).count()
        if admin_count == 0:
            admin_role = session.query(Role).filter_by(name="Administrator").first()
            if admin_role:
                # Default local admin password: 'Admin@SecureOffline2026'
                hashed = hashlib.sha256("Admin@SecureOffline2026".encode("utf-8")).hexdigest()
                admin_user = User(
                    username="admin",
                    email="admin@cctv.local",
                    password_hash=hashed,
                    full_name="System Administrator",
                    role_id=admin_role.id,
                    is_active=True,
                )
                session.add(admin_user)
                logger.info("Default local offline administrator account initialized ('admin').")


def bootstrap_application() -> Dict[str, Any]:
    """
    Executes the complete application bootstrap sequence.
    Returns status and telemetry summary.
    """
    settings = get_settings()

    # 1. Initialize Logging
    setup_logging(
        log_dir=settings.storage.logs_dir,
        log_level="DEBUG" if settings.debug else "INFO",
    )
    logger.info("=================================================================")
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("=================================================================")

    # 2. Ensure Storage Directories
    settings.ensure_directories()
    logger.info("Storage directories validated.")

    # 3. Hardware Probing
    report = HardwareDetector.generate_full_report()
    app_state.hardware_report = report
    logger.info("Host Hardware Tier: %s", report.hardware_acceleration_tier)
    logger.info("OpenVINO Acceleration: %s (Devices: %s)", report.openvino.available, report.openvino.available_devices)

    # 4. Database Initialization
    db_manager.init_schema()
    seed_initial_security_data()
    db_health = db_manager.health_check()
    logger.info("Database initialized successfully (Backend: %s, Latency: %s ms)", db_health.get("backend"), db_health.get("latency_ms"))

    return {
        "status": "READY",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "hardware_tier": report.hardware_acceleration_tier,
        "openvino_devices": report.openvino.available_devices,
        "db_health": db_health,
    }
