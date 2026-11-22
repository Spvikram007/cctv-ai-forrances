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
GIT COMMIT: e4e88ed275c368df92175a80e288217bec27178a  

## [0.2.0-alpha] - 2026-11-22

CHANGE ID: CHG-20261122-002  
FEATURE ID: F-003, F-004, F-005, F-006  
DATE: 2026-11-22  
VERSION: 0.2.0-alpha  
CHANGE TYPE: NEW FEATURE  
DESCRIPTION: Implemented Phase 1 & Phase 2: Camera Discovery and Video Stream Engine. Added ONVIF WS-Discovery (UDP multicast probe), local subnet IP range scanning with multi-threaded port testing, MAC address resolution via local ARP cache, and manufacturer fingerprinting. Implemented pure-Python ONVIF client with WS-Security PasswordDigest, device info, media profiles, RTSP URI resolution, and PTZ controls (Profile S/T). Built manufacturer adapters for Hikvision ISAPI, Dahua CGI, CP PLUS, and generic devices. Created high-capacity RTSP stream worker engine with OpenCV/FFmpeg backend, bounded frame queues with frame drop protection, auto-reconnection with backoff, credential masking in logs, and synthetic test stream generator. Developed video display tile widget with QPainter aspect-ratio rendering, OSD telemetry overlays (FPS, resolution, status dot), snapshot capture, and integrated Live Monitoring workspace supporting dynamic 1x1, 2x2, 3x3, and 4x4 grid layouts with tile double-click maximization. Implemented AES-256-GCM local credential vault and Alembic database migrations.  
FILES CREATED:  
- `core/security/crypto.py`
- `integrations/onvif/discovery.py`
- `integrations/onvif/client.py`
- `integrations/generic_devices/base_adapter.py`
- `integrations/hikvision/isapi_adapter.py`
- `integrations/dahua/cgi_adapter.py`
- `integrations/cpplus/cpplus_adapter.py`
- `engines/video_engine/stream_metrics.py`
- `engines/video_engine/rtsp_streamer.py`
- `engines/video_engine/stream_manager.py`
- `modules/live_monitoring/video_widget.py`
- `modules/live_monitoring/live_view_widget.py`
- `modules/camera_management/discovery_dialog.py`
- `alembic.ini`
- `database/migrations/env.py`
- `database/migrations/README`
- `database/migrations/script.py.mako`
- `database/migrations/versions/26108d74df4c_phase1_phase2_devices_and_streams.py`
- `tests/unit/test_stream_engine.py`
- `tests/unit/test_onvif_and_discovery.py`
- `tests/unit/test_crypto_credentials.py`
- `tests/unit/test_adapters.py`
- `tests/integration/test_phase1_phase2_ui.py`
- `tests/performance/test_stream_performance.py`
FILES MODIFIED:  
- `requirements/base.txt`
- `database/models/devices.py`
- `database/models/__init__.py`
- `app/main.py`
- `docs/FEATURE_REGISTER.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE_DESIGN.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/USER_MANUAL.md`
FILES DELETED: None  
DATABASE CHANGES: Applied Alembic migration `26108d74df4c`: created `device_credentials`, `device_discovery_records`, `nvr_channel_mappings`, and `stream_health_logs` tables with indexes.  
DEPENDENCIES CHANGED: Installed and pinned `cryptography>=50.0.0` with `cffi` and `pycparser`.  
TESTS PERFORMED: Automated test execution across 39 test cases covering WS-Discovery XML parsing, ONVIF SOAP methods, RTSP stream worker lifecycle, bounded queue overflow, frame dropping, credential encryption/decryption, database persistence, multi-channel layouts, and performance benchmarks for 1, 4, and 16 streams.  
TEST RESULTS: 39 passed, 0 failed, 100% pass rate in 7.46s.  
KNOWN ISSUES: Physical ONVIF/RTSP cameras require local network attachment; test doubles and synthetic test streams verify 100% of pipeline in offline testing.  
## [0.3.0-alpha] - 2026-11-22

CHANGE ID: CHG-20261122-003  
FEATURE ID: F-007, F-008, F-021  
DATE: 2026-11-22  
VERSION: 0.3.0-alpha  
CHANGE TYPE: NEW FEATURE  
DESCRIPTION: Implemented Phase 4 – Surveillance Recording and Advanced Playback Engine. Features dedicated per-channel recording workers decoupled from UI rendering, continuous, manual, motion, and AI-event-triggered segmented recording, memory-efficient pre-event and post-event ring buffering (`deque`), automatic video segmentation with SHA-256 integrity sealing, storage volume health monitoring with low-disk warning thresholds, automatic retention pruning strictly protecting locked evidence (`is_locked=True`), crash and restart recording recovery service (`RecordingRecoveryService`), synchronized multi-camera playback controller (`SynchronizedPlaybackController`) with master clock, variable speeds (0.25x to 16.0x), frame stepping (+/-1 frame), recording gap detection, custom interactive QPainter Timeline UI widget with zoom and drag seeking, MP4 forensic video clip exporter (`VideoExporter`) generating SHA-256 checksums and sidecar audit manifests, and full integration into the Command Center desktop workspace.  
FILES CREATED:  
- `database/migrations/versions/328e2912c14c_phase4_recordings_and_playback.py`
- `engines/recording_engine/recorder.py`
- `engines/recording_engine/recording_manager.py`
- `engines/recording_engine/storage_manager.py`
- `engines/video_engine/playback_controller.py`
- `engines/video_engine/video_exporter.py`
- `modules/video_playback/timeline_widget.py`
- `modules/video_playback/playback_widget.py`
- `tests/unit/test_recording_engine.py`
- `tests/unit/test_storage_manager.py`
- `tests/unit/test_playback_engine.py`
- `tests/unit/test_video_exporter.py`
- `tests/integration/test_playback_ui.py`
- `tests/performance/test_recording_playback_performance.py`
FILES MODIFIED:  
- `database/models/recordings.py`
- `database/models/__init__.py`
- `app/bootstrap.py`
- `app/main.py`
- `docs/FEATURE_REGISTER.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE_DESIGN.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/USER_MANUAL.md`
FILES DELETED: None  
DATABASE CHANGES: Applied Alembic revision `328e2912c14c`: added `storage_events`, `playback_sessions`, and `export_jobs` tables; extended `recordings` with `codec`, `resolution_width`, `resolution_height`, `fps`, `bitrate_kbps`, `status`, and `is_locked`; decoupled `channel_id` from strict device FK constraint to support logical channels.  
DEPENDENCIES CHANGED: None (using existing OpenCV, NumPy, PySide6, SQLAlchemy).  
TESTS PERFORMED: Automated test execution across 60 test cases covering continuous and event-triggered recording, ring buffer preservation, crash recovery, storage volume metrics, low-disk warnings, evidence retention protection, single-player seeking and gap handling, multi-camera playback master clock sync, variable speeds, frame stepping, MP4 export with SHA-256 audit manifest, Timeline QPainter rendering and scrubbing, and concurrent recording throughput benchmarks across 1, 4, and 16 channels.  
TEST RESULTS: 60 passed, 0 failed, 100% pass rate in 16.23s.  
KNOWN ISSUES: None in Phase 4 scope.  
GIT COMMIT: 63b0d81ef64f3b21de586eab116e785932cdcd0e  
