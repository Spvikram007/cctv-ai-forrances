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

    # 5. Crash / Restart Recording Recovery
    from engines.recording_engine.recorder import RecordingRecoveryService
    recovered_count = RecordingRecoveryService.recover_interrupted_recordings()
    if recovered_count > 0:
        logger.warning("Recovered %d interrupted recording segments from prior session.", recovered_count)
    else:
        logger.info("No unclosed recording segments found; storage integrity verified.")

    # 6. AI Inference Engine Initialization
    from engines.ai_engine.inference_engine import openvino_engine, onnx_engine
    openvino_ready = openvino_engine.initialize()
    onnx_ready = onnx_engine.initialize()
    logger.info("AI Engines: OpenVINO=%s (Active: %s), ONNX=%s",
                openvino_ready, openvino_engine.active_device, onnx_ready)

    # 7. Video Analytics Engine Initialization
    from engines.analytics_engine.analytics_pipeline import analytics_manager
    from engines.recording_engine.recording_manager import recording_manager
    analytics_manager.set_recording_manager(recording_manager)
    analytics_manager.load_from_db()
    logger.info("Video Analytics Engine initialized with %d camera pipelines.", len(analytics_manager._pipelines))

    # 8. ANPR & Authorized Face Intelligence Initialization
    from engines.anpr_engine.anpr_pipeline import anpr_pipeline
    from engines.face_engine.face_service import face_intelligence_service
    anpr_pipeline.set_recording_manager(recording_manager)
    face_intelligence_service.set_recording_manager(recording_manager)
    loaded_faces = face_intelligence_service.reload_enrolled_templates()
    logger.info("Face Intelligence: %d authorized identities active; ANPR pipeline ready.", loaded_faces)

    # 9. Unified Alarm Management Engine Initialization (Phase 12 - F-046)
    from engines.alarm_engine.adapters import alarm_adapter
    alarm_adapter.start()
    logger.info("Unified Alarm Engine: EventBus adapters active and listening.")

    return {
        "status": "READY",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "hardware_tier": report.hardware_acceleration_tier,
        "openvino_devices": report.openvino.available_devices,
        "openvino_ready": openvino_ready,
        "active_ai_device": openvino_engine.active_device,
        "analytics_ready": True,
        "anpr_ready": True,
        "face_intelligence_ready": True,
        "alarm_engine_ready": True,
        "db_health": db_health,
        "recovered_recordings": recovered_count,
    }
