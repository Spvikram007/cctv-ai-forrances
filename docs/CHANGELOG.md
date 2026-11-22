# CCTV AI Intelligence Platform Changelog

## [0.1.0-alpha] - 2026-11-22

CHANGE ID: CHG-20261122-001  
FEATURE ID: F-001, F-002, F-022  
DATE: 2026-11-22  
VERSION: 0.1.0-alpha  
CHANGE TYPE: NEW FEATURE  
DESCRIPTION: Initialized Phase 0 foundation of the CCTV AI Intelligence Platform. Configured repository, complete modular monolith directory structure, pinned Python dependencies, hardware detection engine (Intel CPU, RAM, Intel UHD 730 GPU, Storage, OpenVINO Core runtime), thread/process worker management, structured redacting logging, Pydantic settings, event bus, database management engine (PostgreSQL connection and SQLite WAL mode resilient fallback), complete SQLAlchemy database models, and PySide6 dark surveillance desktop application with 15 workspace views and real-time dashboard telemetry.  
FILES CREATED:  
- `.gitignore`
- `VERSION`
- `README.md`
- `requirements/base.txt`
- `requirements/dev.txt`
- `requirements/prod.txt`
- `core/__init__.py`
- `core/logging/logger.py`
- `core/config/settings.py`
- `core/hardware/detector.py`
- `core/events/event_bus.py`
- `core/workers/worker_manager.py`
- `database/database_manager.py`
- `database/models/base.py`
- `database/models/users.py`
- `database/models/devices.py`
- `database/models/recordings.py`
- `database/models/ai.py`
- `database/models/__init__.py`
- `app/application_state.py`
- `app/configuration.py`
- `app/bootstrap.py`
- `app/main.py`
- `resources/styles/theme.py`
- `modules/dashboard/dashboard_widget.py`
- `tests/conftest.py`
- `tests/unit/test_hardware.py`
- `tests/unit/test_config.py`
- `tests/unit/test_logging.py`
- `tests/unit/test_database.py`
- `tests/unit/test_workers.py`
- `tests/integration/test_ui_smoke.py`
- `docs/ARCHITECTURE.md`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
FILES MODIFIED: None  
FILES DELETED: None  
DATABASE CHANGES: Created initial relational schema: `roles`, `permissions`, `role_permissions`, `users`, `user_sessions`, `audit_logs`, `sites`, `locations`, `devices`, `device_channels`, `stream_profiles`, `device_capabilities`, `device_status`, `storage_volumes`, `recordings`, `recording_segments`, `recording_schedules`, `ai_models`, `ai_model_versions`, `ai_jobs`, `detections`, `object_tracks`, `ai_events`. Seeded 5 core default roles and default offline administrator.  
DEPENDENCIES CHANGED: Installed and pinned PySide6 (6.12.0), OpenVINO (2026.4.1), ONNX Runtime (1.32.0), SQLAlchemy (2.1.9), Alembic (1.20.1), Pydantic (2.14.4), Pydantic Settings (2.16.3), pytest (9.2.0).  
TESTS PERFORMED: Automated test execution across 17 test cases spanning hardware detection, Pydantic configuration, structured credential-redacting logging, SQLite WAL database session management and transactions, thread worker pool lifecycle, and PySide6 offscreen GUI smoke testing.  
TEST RESULTS: 17 passed, 0 failed, 100% pass rate in 1.08s.  
KNOWN ISSUES: None in Phase 0 scope.  
GIT COMMIT: Pending initial commit.  
