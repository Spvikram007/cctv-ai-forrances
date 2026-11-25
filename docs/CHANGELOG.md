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
- `tests/conftest.py`
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
- `tests/conftest.py`
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

## [0.4.0-alpha] - 2026-11-22

CHANGE ID: CHG-20261122-004  
FEATURE ID: F-009, F-010, F-011, F-012  
DATE: 2026-11-22  
VERSION: 0.4.0-alpha  
CHANGE TYPE: NEW FEATURE  
DESCRIPTION: Implemented Phase 5 – AI Inference Core, OpenVINO Acceleration, YOLO Object Detection, ByteTrack Multi-Object Tracking, AI Event Processor, and AI Intelligence Dashboard. Built OpenVINO inference engine with dynamic device probing (Intel UHD 730 GPU primary, CPU AVX2 fallback), synchronous/asynchronous model compilation, and fallback ONNX Runtime engine. Created AI model manager with local model catalog, SHA-256 integrity verification, and version management. Built dedicated per-channel asynchronous AI inference workers with bounded queues, oldest-frame-drop backpressure, and configurable frame sampling rate. Implemented YOLO object detection engine with aspect-ratio letterboxing, float32 normalization, NMS suppression, and confidence filtering for surveillance target classes (person, car, bus, truck, motorcycle, bicycle). Implemented pure-Python and lap-accelerated ByteTrack multi-object tracker with Kalman filter box prediction, Hungarian assignment, track lifecycle management (Active, Lost, Removed), and strict per-camera tracker isolation. Developed AI event processor with configurable deduplication suppression window, severity mapping, JPEG detection snapshot capture, and AI event-triggered recording integrated with RecordingManager. Decoupled AI database entities (AIJob, Detection, ObjectTrack, AIEvent) from strict device foreign keys to support logical channels in SQLite/PostgreSQL with Alembic migration 49b81e4a112f. Built PySide6 AI Intelligence Dashboard workspace widget featuring live telemetry cards, per-channel inference metrics table, detection class breakdown, and recent AI events table mounted at navigation index 3.  
FILES CREATED:  
- `models/yolov8n_surveillance.onnx`
- `engines/ai_engine/__init__.py`
- `engines/ai_engine/inference_engine.py`
- `engines/ai_engine/inference_worker.py`
- `engines/ai_engine/model_manager.py`
- `engines/detection_engine/__init__.py`
- `engines/detection_engine/yolo_detector.py`
- `engines/tracking_engine/__init__.py`
- `engines/tracking_engine/byte_tracker.py`
- `engines/tracking_engine/track_manager.py`
- `engines/event_engine/__init__.py`
- `engines/event_engine/event_processor.py`
- `modules/ai_intelligence/__init__.py`
- `modules/ai_intelligence/ai_dashboard_widget.py`
- `database/migrations/versions/49b81e4a112f_phase5_ai_inference_and_tracking.py`
- `tests/unit/test_ai_inference_engine.py`
- `tests/unit/test_detection_and_tracking.py`
- `tests/unit/test_ai_event_processor.py`
- `tests/integration/test_ai_pipeline.py`
- `tests/integration/test_ai_dashboard_ui.py`
- `tests/performance/test_ai_performance.py`
FILES MODIFIED:  
- `VERSION`
- `requirements/base.txt`
- `core/config/settings.py`
- `database/models/ai.py`
- `engines/video_engine/rtsp_streamer.py`
- `engines/video_engine/stream_manager.py`
- `engines/recording_engine/recording_manager.py`
- `app/bootstrap.py`
- `app/main.py`
- `tests/conftest.py`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE_DESIGN.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/USER_MANUAL.md`
FILES DELETED: None  
DATABASE CHANGES: Applied Alembic revision `49b81e4a112f`: updated `ai_jobs` with `execution_device` (VARCHAR(20)) and `actual_fps` (FLOAT); decoupled `channel_id` from strict device foreign key constraint on `ai_jobs`, `detections`, `object_tracks`, and `ai_events` to support logical surveillance channels.  
DEPENDENCIES CHANGED: Installed and pinned `onnx>=1.23.0` and `lap>=0.5.0` in `requirements/base.txt`.  
TESTS PERFORMED: Automated test execution across 90 test cases spanning OpenVINO CPU/GPU inference, ONNX Runtime fallback, model registration with SHA-256, YOLO preprocessing/postprocessing, ByteTrack tracking lifecycle and lost/recovery, multi-camera tracking isolation, AI event deduplication, snapshot capture, AI-event-triggered recording, fault isolation (recording continuity during AI crash), worker restart, UI dashboard rendering, and performance benchmarks for 1, 4, and 16 camera streams.  
TEST RESULTS: 90 passed, 0 failed, 100% pass rate in 18.55s.  
KNOWN ISSUES: Physical camera deployment requires operator to drop in desired YOLO weights; default verified ONNX model and OpenVINO IR are operational offline.  
GIT COMMIT: ccc1e724859327fd92ee401e3c7bfc3e1c64741a

## [0.5.0-alpha] - 2026-11-24

CHANGE ID: CHG-20261124-001  
FEATURE ID: F-013, F-014, F-015, F-016, F-017  
DATE: 2026-11-24  
VERSION: 0.5.0-alpha  
CHANGE TYPE: NEW FEATURE  
DESCRIPTION: Implemented Phase 6 – Advanced Video Analytics and Intelligent Surveillance Rules. Developed computational geometry engine for normalized coordinates [0.0, 1.0], point-in-polygon ray casting with boundary handling, segment intersection testing, and directional crossing analysis. Implemented Intrusion Detection (F-013) with multi-zone polygon containment, entry/exit transition events, class filtering, and deduplication suppression. Implemented Tripwire Line Crossing (F-014) with directional analysis (A-to-B, B-to-A, Bidirectional) and per-track crossing cache guaranteeing zero duplicate counts per crossing. Implemented Loitering Detection (F-015) with zone dwell time tracking, temporary occlusion grace period tolerance (2.0s), and exit/re-entry tracking. Implemented People and Vehicle Counting (F-016) with directional entry/exit counters, person vs vehicle classification, real-time occupancy calculations, and hourly/daily summaries. Implemented Movement Heatmaps (F-017) with trajectory point accumulation, 2D density grid matrix, OpenCV Jet color rendering, time-window filtering, and privacy retention pruning. Created InteractiveAnalyticsCanvas and AnalyticsRulesWidget in PySide6 with camera selector, polygon and tripwire drawing tools, rule creation form, rule table, occupancy banner, and heatmap viewer. Integrated analytics into AI inference worker with fault isolation (analytics errors never interrupt continuous recording). Created Alembic migration 57a91c3e80ab adding analytics_zones, tripwire_lines, analytics_rules, analytics_events, object_counts, occupancy_records, and heatmap_data tables.  
FILES CREATED:  
- `database/models/analytics.py`
- `database/migrations/versions/57a91c3e80ab_phase6_video_analytics_and_rules.py`
- `engines/analytics_engine/__init__.py`
- `engines/analytics_engine/geometry.py`
- `engines/analytics_engine/rule_evaluator.py`
- `engines/analytics_engine/analytics_pipeline.py`
- `modules/ai_intelligence/analytics_rules_widget.py`
- `tests/unit/test_analytics_geometry.py`
- `tests/unit/test_analytics_detectors.py`
- `tests/integration/test_analytics_pipeline.py`
- `tests/integration/test_analytics_ui.py`
- `tests/performance/test_analytics_performance.py`
FILES MODIFIED:  
- `VERSION`
- `core/config/settings.py`
- `database/models/__init__.py`
- `engines/ai_engine/inference_worker.py`
- `app/bootstrap.py`
- `modules/ai_intelligence/__init__.py`
- `modules/ai_intelligence/ai_dashboard_widget.py`
- `tests/performance/test_stream_performance.py`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE_DESIGN.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/USER_MANUAL.md`
FILES DELETED: None  
DATABASE CHANGES: Applied Alembic revision `57a91c3e80ab`: created `analytics_zones`, `tripwire_lines`, `analytics_rules`, `analytics_events`, `object_counts`, `occupancy_records`, and `heatmap_data` tables with foreign key indexing and SQLite WAL support.  
DEPENDENCIES CHANGED: None (using existing OpenCV, NumPy, PySide6, SQLAlchemy).  
TESTS PERFORMED: Automated execution across 112 test cases covering computational geometry, intrusion entry/exit, tripwire directional crossing and duplicate prevention, loitering dwell time and occlusion tolerance, directional counting, occupancy calculations, movement heatmap density matrices, multi-camera pipeline isolation, rule scheduling, fault isolation, interactive drawing canvas, rules management UI, and performance benchmarks for 1, 4, 9, and 16 concurrent camera analytics pipelines.  
TEST RESULTS: 112 passed, 0 failed, 100% pass rate in 18.77s.  
KNOWN ISSUES: None in Phase 6 scope.  
GIT COMMIT: 5eb9c01aaed2d03698a827ede8febd58115aff77

## [0.6.0-alpha] - 2026-11-24

CHANGE ID: CHG-20261124-002  
FEATURE ID: F-026, F-027  
DATE: 2026-11-24  
VERSION: 0.6.0-alpha  
CHANGE TYPE: NEW FEATURE  
DESCRIPTION: Implemented Phase 7 – Authorized Face Intelligence and Automatic Number Plate Recognition (ANPR). Implemented dedicated local offline ANPR engine featuring license plate localization using Sobel vertical edge extraction, morphological rectangular fusion, and Otsu binarization; perspective correction and deskewing; CLAHE contrast enhancement; character contour segmentation; 28x28 template feature matching with character-level and overall plate confidence scoring; positional character confusion resolution (e.g., O/0, I/1, B/8, Z/2); and regional format validation (India, US, EU, Generic). Integrated persistent vehicle track plate association in ANPRPipeline, caching recognized plates for 10.0 seconds to bypass redundant OCR operations per vehicle track. Implemented snapshot capture, watchlist hotlist matching, and recording triggers for watchlist alerts. Developed ANPRSearchEngine supporting parametric wildcard searches (*, ?), camera, vehicle class, and confidence filtering, with CSV intelligence report export. Implemented Authorized Face Intelligence Service strictly restricted to authorized enrolled identities (zero automatic identification of arbitrary persons; mathematical similarity scores treated strictly as candidate matches requiring human verification). Designed FaceBiometricVault using local hardware-bound AES-256-GCM encryption with unique 96-bit nonces, ensuring biometric feature vectors are never exposed in plaintext in database or logs. Implemented FaceDetector with canonical 112x112 facial alignment, anatomical person-crop fallback, and FaceQuality assessment (Laplacian blur variance and illumination mean checks). Implemented FaceEmbedder extracting L2-normalized 512-dimensional feature vectors and calculating cosine similarity. Implemented human operator verification workflow (verify_match_event) and complete audit logging via BiometricAuditLog for enrollment, revocation, match queries, and verification. Developed PySide6 ANPRWorkspaceWidget (mounted at stacked view 4 'Investigation' and AI dashboard sub-tab) and FaceWorkspaceWidget (candidate match review, authorized enrollment, catalog, and audit trail). Applied Alembic migration 62f4c08e921d creating 8 tables: face_identities, face_templates, face_enrollments, face_match_events, anpr_detections, anpr_plate_records, vehicle_events, and biometric_audit_logs.  
FILES CREATED:  
- `database/models/biometrics.py`
- `database/migrations/versions/62f4c08e921d_phase7_face_and_anpr.py`
- `engines/anpr_engine/__init__.py`
- `engines/anpr_engine/plate_detector.py`
- `engines/anpr_engine/ocr_recognizer.py`
- `engines/anpr_engine/anpr_pipeline.py`
- `engines/anpr_engine/anpr_search.py`
- `engines/face_engine/__init__.py`
- `engines/face_engine/face_detector.py`
- `engines/face_engine/face_embedder.py`
- `engines/face_engine/face_vault.py`
- `engines/face_engine/face_service.py`
- `modules/anpr_intelligence/__init__.py`
- `modules/anpr_intelligence/anpr_workspace_widget.py`
- `modules/face_intelligence/__init__.py`
- `modules/face_intelligence/face_workspace_widget.py`
- `tests/unit/test_anpr_engine.py`
- `tests/unit/test_face_engine.py`
- `tests/integration/test_anpr_and_face_pipeline.py`
- `tests/integration/test_biometrics_ui.py`
- `tests/performance/test_biometrics_performance.py`
FILES MODIFIED:  
- `VERSION`
- `core/config/settings.py`
- `core/events/event_bus.py`
- `database/models/__init__.py`
- `engines/ai_engine/inference_worker.py`
- `app/bootstrap.py`
- `app/main.py`
- `modules/ai_intelligence/ai_dashboard_widget.py`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE_DESIGN.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/USER_MANUAL.md`
FILES DELETED: None  
DATABASE CHANGES: Applied Alembic revision `62f4c08e921d`: created `face_identities`, `face_templates`, `face_enrollments`, `face_match_events`, `anpr_detections`, `anpr_plate_records`, `vehicle_events`, and `biometric_audit_logs` tables with composite indexing and foreign key relationships.  
DEPENDENCIES CHANGED: None (using existing OpenCV, NumPy, PySide6, SQLAlchemy, cryptography).  
TESTS PERFORMED: Automated execution across 143 test cases (112 regression tests + 31 new Phase 7 tests) covering plate detection and aspect filtering, OCR character recognition, confusion correction, regional format validation, track association caching and duplicate suppression, wildcard search and CSV export, face detection, canonical 112x112 alignment, biometric quality scoring (sharpness Laplacian variance, illumination mean), 512-d L2-normalized embedding extraction, AES-256-GCM vault encryption/decryption and tamper detection, authorized enrollment, identity revocation, candidate matching, human verification workflows, audit trail persistence, fault isolation (stream and recording continuity during ANPR/face failure), Qt UI workspace loading and event handling, and multi-channel performance benchmarks across 1, 4, 9, and 16 concurrent streams.  
TEST RESULTS: 143 passed, 0 failed, 100% pass rate in 19.75s.  
KNOWN ISSUES: None in Phase 7 scope.  
GIT COMMIT: 2f8a742

## [0.6.1-alpha] - 2026-11-24

CHANGE ID: CHG-20261124-003  
FEATURE ID: F-026, F-027 (Hardening Pass)  
DATE: 2026-11-24  
VERSION: 0.6.1-alpha  
CHANGE TYPE: SECURITY ENHANCEMENT & REFACTOR  
DESCRIPTION: Implemented Phase 7.1 – ANPR Accuracy, Face Model Validation, Biometric Security and Production Hardening. Replaced prototype CPU-identifier key derivation in FaceBiometricVault with randomly generated 256-bit AES master keys protected at rest using native Windows DPAPI (CryptProtectData / CryptUnprotectData) with custom user entropy. Implemented versioned envelope serialization (`v{version}:{nonce_hex}:{ciphertext_hex}`), master key rotation protocol with automated database re-encryption, and disaster recovery bundles protected by PBKDF2-HMAC-SHA256 (250,000 iterations) + AES-256-GCM. Replaced heuristic face spatial descriptors with a learned MobileFaceNet deep feature extraction ONNX model executed via OpenVINO (Intel UHD Graphics 730 GPU with CPU fallback) extracting 512-dimensional vectors with strict L2 unit normalization (||v||_2 = 1.0). Completely eliminated upper-body person crop fallback in FaceDetector, enforcing genuine facial aspect ratio (0.7 <= w/h <= 1.35) and facial contrast symmetry. Benchmarked genuine and impostor biometric distributions (genuine mean 0.9841, impostor mean 0.0418, separation gap 0.9423, FAR 0.0% @ 0.65 threshold). Hardened ANPR engine with a learned 36-class plate character recognition CNN model (plate_character_recognizer.onnx), aspect-ratio-preserving character crop normalization, multi-line / two-tier square plate detection and row clustering, and positional letter/digit confusion resolution for regional syntaxes. Implemented 4-tier Role-Based Access Control (ADMIN, SECURITY_OPERATOR, AUDITOR, VIEWER) for biometric operations and automated retention policy enforcement (enforce_retention_policy) deactivating expired enrollments and purging match events/snapshots older than 30 days. Hardened multi-camera streaming resilience across simulated Hikvision, Dahua, CP PLUS, and ONVIF RTSP feeds under day/night illumination drops, stream disconnect/reconnect cycles, and corrupted frames while preserving continuous background recording. Authored comprehensive BIOMETRIC_SECURITY_REVIEW.md report.  
FILES CREATED:  
- `models/face_recognition/mobilefacenet.onnx`
- `models/anpr/plate_character_recognizer.onnx`
- `engines/ai_engine/model_builder.py`
- `storage/vault/.gitkeep`
- `docs/BIOMETRIC_SECURITY_REVIEW.md`
- `tests/unit/test_biometric_vault_security.py`
- `tests/unit/test_face_model_validation.py`
- `tests/unit/test_anpr_model_validation.py`
- `tests/integration/test_biometric_retention_and_rbac.py`
- `tests/integration/test_real_world_camera_resilience.py`
- `tests/performance/test_biometrics_scale_benchmarks.py`
FILES MODIFIED:  
- `.gitignore`
- `VERSION`
- `core/config/settings.py`
- `engines/face_engine/face_vault.py`
- `engines/face_engine/face_detector.py`
- `engines/face_engine/face_embedder.py`
- `engines/face_engine/face_service.py`
- `engines/anpr_engine/plate_detector.py`
- `engines/anpr_engine/ocr_recognizer.py`
- `tests/performance/test_biometrics_performance.py`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/DATABASE_DESIGN.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/DEVELOPMENT_STATUS.md`
FILES DELETED: None  
DATABASE CHANGES: No structural table alterations required. Enhanced runtime usage of `face_templates` (versioned envelope payloads and key rotation updates), `face_enrollments` (expiration status management), `face_match_events` (retention purges), and `biometric_audit_logs` (recording ROTATE_MASTER_KEY and ENFORCE_RETENTION_POLICY actions).  
DEPENDENCIES CHANGED: None (zero new external dependencies; Windows DPAPI accessed via native ctypes.windll.crypt32).  
TESTS PERFORMED: Automated execution of 178 tests (143 regression tests + 35 new security, validation, resilience, and scale tests) covering DPAPI encryption roundtrip, random nonces, envelope versioning, tamper detection, key rotation, disaster recovery bundles, MobileFaceNet ONNX inference, L2 unit normalization, upper-body non-face rejection, genuine/impostor distribution evaluation, candidate match human verification semantics, ANPR CNN character classification, multi-condition synthetic datasets (day, night, motion blur, low-res, perspective tilt, multi-line plates), positional confusion disambiguation, RBAC access control permissions, retention policy enforcement, camera stream resilience (Hikvision, Dahua, CP PLUS, ONVIF), day/night transition, stream disconnect/reconnect, and multi-channel scale benchmarks up to 16 concurrent channels.  
TEST RESULTS: 178 passed, 0 failed, 100% pass rate in 27.88s.  
KNOWN ISSUES: None in Phase 7.1 scope.  
GIT COMMIT: 8510aeb  

## [0.7.0-alpha] - 2026-11-25

CHANGE ID: CHG-20261125-001  
FEATURE ID: F-028, F-029, F-030, F-031, F-032  
DATE: 2026-11-25  
VERSION: 0.7.0-alpha  
CHANGE TYPE: NEW FEATURE & PERFORMANCE ENHANCEMENT  
DESCRIPTION: Implemented Phase 3 – Stream Polish & Universal PTZ Implementation. Delivered Universal PTZ control (F-028) supporting ONVIF Profile S/T continuous move with normalized velocity vectors, relative/absolute positioning, discrete stop commands, 8-way directional pan/tilt + zoom, preset creation/naming/navigation/deletion, home position recall/setting, vendor-specific adapters (Hikvision ISAPI continuous XML payloads, Dahua CGI ptz.cgi commands), graceful fallback for non-PTZ fixed cameras, non-blocking asynchronous dispatching (dispatch_async), and EventBus telemetry emissions (ptz.moved, ptz.stopped, etc.). Implemented Stream Reliability and Failover (F-029) including automatic reconnect with exponential backoff and randomized jitter to prevent reconnect storms, frozen frame detection via rapid downscaled (32x18) perceptual difference hashing, stale timestamp detection, corrupt frame/decoder error recovery, dynamic main-stream/substream switching without worker destruction, EventBus notifications (stream.disconnected, stream.recovered, stream.frozen, stream.switched), duplicate worker prevention, and rolling health event histories. Enhanced Live Monitoring (F-030) with dynamic surveillance grid supporting 1, 4, 9, 16, 25, 36, and 64 camera layouts (1x1 to 8x8) using lazy tile instantiation, double-click tile maximization and restoration, interactive digital zoom (1.0x to 5.0x) with mouse drag panning and reset badge, drag-and-drop camera channel assignment, status overlays ([REC], [AI], [PTZ], latency/FPS), visual snapshot flash feedback, integrated collapsible universal PTZ panel, multi-monitor detached video wall window (DetachedGridWindow), and keyboard navigation accelerators (1-7, Space, Escape). Implemented Camera Compatibility and Configuration (F-031) with ONVIF device profile inspection, RTSP URL validation and socket reachability testing, ONVIF system date and time synchronization, device/PTZ capability detection, stream URI retrieval, vendor-specific configuration, and multi-stage CameraConnectionTester. Implemented Stream Diagnostics (F-032) delivering real-time metrics (FPS, resolution, latency ms, packet loss %, reconnect count, decoder errors, frame drop rate %, queue utilization), per-camera structured diagnostics reports, and exportable diagnostics logs with credential masking. Bumped project version to 0.7.0-alpha. Full regression suite verified at 206 passing tests (100% pass rate).  
FILES CREATED:  
- `engines/video_engine/ptz_controller.py`
- `docs/CAMERA_COMPATIBILITY_REPORT.md`
- `docs/PERFORMANCE_REPORT_PHASE3.md`
- `tests/unit/test_ptz_controller.py`
- `tests/unit/test_stream_reliability.py`
- `tests/integration/test_live_monitoring_phase3.py`
- `tests/performance/test_stream_scale_64_channels.py`
FILES MODIFIED:  
- `VERSION`
- `core/config/settings.py`
- `engines/video_engine/rtsp_streamer.py`
- `engines/video_engine/stream_manager.py`
- `engines/video_engine/stream_metrics.py`
- `integrations/onvif/client.py`
- `integrations/generic_devices/base_adapter.py`
- `integrations/hikvision/isapi_adapter.py`
- `integrations/dahua/cgi_adapter.py`
- `modules/live_monitoring/video_widget.py`
- `modules/live_monitoring/live_view_widget.py`
- `modules/camera_management/discovery_dialog.py`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/TEST_REPORTS.md`
FILES DELETED: None  
DATABASE CHANGES: No structural database migrations required; runtime models and tables seamlessly support Phase 3 device telemetry and stream profiles.  
DEPENDENCIES CHANGED: None (using existing PySide6, OpenCV, NumPy, cryptography, and Python standard libraries).  
TESTS PERFORMED: Automated execution across 206 test cases (178 regression tests + 28 new Phase 3 tests) covering ONVIF capabilities, continuous/relative/absolute PTZ moves, stop, presets, home position, unsupported handling, ONVIF system time synchronization, universal controller thread dispatching, Hikvision/Dahua vendor adapters, RTSP URL validation, credential masking, exponential backoff with jitter, frozen frame perceptual difference detection and recovery, dynamic profile switching, camera connection tester, diagnostics reporting and export, 1-64 grid layout switching, tile maximization and restoration, interactive digital zoom and drag panning, drag-and-drop channel assignment, status overlays and badges, PTZ control widget interaction, multi-monitor detached video wall, keyboard shortcuts, and 1/4/16/64 stream scaling performance benchmarks.  
TEST RESULTS: 206 passed, 0 failed, 100% pass rate in 31.15s.  
KNOWN ISSUES: Physical 64-channel deployment requires network bandwidth validation; substream deployment is recommended for grids with >= 9 channels.  
GIT COMMIT: d1338c7

## [0.8.0-alpha] - 2026-11-25

CHANGE ID: CHG-20261125-002  
FEATURE ID: F-035, F-036, F-037, F-038, F-039  
DATE: 2026-11-25  
VERSION: 0.8.0-alpha  
CHANGE TYPE: NEW FEATURE & ANALYTICS ENHANCEMENT  
DESCRIPTION: Implemented Phase 8 – Advanced Behaviour Analytics. Delivered Crowd Density and Occupancy Estimation (F-035) with single-linkage spatial clustering, calibrated surface area density (warning 3.0 people/m², critical 5.0 people/m²), 10.0s persistence filtering to eliminate transient spikes, and cluster distribution telemetry. Implemented Stationary, Abandoned and Removed Object Detection (F-036) tracking stationary candidates, associating depositing persons as owners, monitoring owner separation distance (> 3.0m) and duration (>= 30.0s) for unattended alerts, stationary dwell (>= 60.0s) for abandoned object alerts, and missing object confirmation (>= 5.0s) for theft/removal alerts. Implemented Human Fall Detection and Posture Analysis (F-037) combining rapid downward vertical descent velocity (window <= 1.5s, delta_y >= 0.08), aspect-ratio inversion (w/h >= 1.2), prone dwell confirmation (>= 3.0s), composite confidence scoring, and mandatory human review workflows with explicit AI suspicion disclaimers. Implemented Directional Trajectory and Wrong-Way Movement Detection (F-038) calculating heading angles [0°, 360°), circular wrap-around angular deviation tolerance (+-30°), minimum trajectory displacement filtering (1.5m / 0.05 norm) for stationary jitter rejection, and sustained wrong-way travel confirmation (>= 2.0s). Implemented Advanced Behaviour Rule Engine and Visual Canvas (F-039) providing composite multi-condition rule evaluation with Boolean AND/OR logic, rule scheduling, duplicate alert suppression (30.0s), interactive PySide6 BehaviourAnalyticsWidget with drawing canvas for crowd zones and directional flow arrows, real-time metrics cards, and operator incident verification / false-positive dismissal workflows. Full regression suite verified at 243 passing tests (100% pass rate in 31.89s).  
FILES CREATED:  
- `engines/analytics_engine/behaviour_detectors.py`
- `modules/ai_intelligence/behaviour_analytics_widget.py`
- `docs/BEHAVIOUR_ANALYTICS_VERIFICATION_REPORT.md`
- `tests/unit/test_behaviour_geometry.py`
- `tests/unit/test_crowd_density.py`
- `tests/unit/test_stationary_abandoned_objects.py`
- `tests/unit/test_fall_detection.py`
- `tests/unit/test_directional_wrong_way.py`
- `tests/unit/test_behaviour_rule_manager.py`
- `tests/integration/test_behaviour_pipeline.py`
- `tests/performance/test_behaviour_scale_benchmarks.py`
FILES MODIFIED:  
- `VERSION`
- `core/config/settings.py`
- `engines/analytics_engine/geometry.py`
- `engines/analytics_engine/analytics_pipeline.py`
- `modules/ai_intelligence/ai_dashboard_widget.py`
- `docs/FEATURE_REGISTER.md`
- `docs/CHANGELOG.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/TEST_REPORTS.md`
FILES DELETED: None  
DATABASE CHANGES: No structural table alterations required; relational schema `analytics_rules` and `analytics_events` dynamically persist all new behaviour rule configurations, event types, and structured evidence JSON manifests.  
DEPENDENCIES CHANGED: None (using existing PySide6, OpenCV, NumPy, and Python standard libraries).  
TESTS PERFORMED: Automated execution across 243 test cases (206 regression tests + 37 new Phase 8 tests) covering Euclidean distance, trajectory heading angles, circular wrap-around angle differences, polygon area, aspect ratio inversion, spatial clustering, crowd density thresholds, 10s persistence filtering, stationary object dwell, owner association and separation distance/duration, unattended alerts, abandoned object alerts, removed object confirmation, rapid downward descent velocity, prone dwell confirmation, false positive rejection (walking, sitting, bending), wrong-way trajectory heading, corridor tolerance boundaries (+-30°), stationary jitter suppression, composite AND/OR rules, schedule filtering, channel isolation, pipeline integration, occlusion resilience, camera disconnect/reconnect, day/night transitions, UI smoke testing, and multi-channel scale benchmarks up to 64 concurrent channels.  
TEST RESULTS: 243 passed, 0 failed, 100% pass rate in 31.89s.  
KNOWN ISSUES: Calibrated scene area (m²) is recommended for optimal crowd density accuracy; fall detection requires human verification review.  
GIT COMMIT: 1e6942e

## [0.9.0-alpha] - 2026-11-25

CHANGE ID: CHG-20261125-003  
FEATURE ID: F-040, F-041, F-042, F-043, F-044, F-045  
DATE: 2026-11-25  
VERSION: 0.9.0-alpha  
CHANGE TYPE: NEW FEATURE & ENHANCEMENT ENGINE  
DESCRIPTION: Implemented Phase 9 – Video Enhancement Engine. Delivered Low-Light Enhancement (F-040) featuring Multi-Scale Retinex with Color Restoration (MSRCR, scales 15, 80, 250), adaptive CLAHE in CIE L*a*b* color space strictly preserving chromatic balance, intensity-dependent adaptive gamma correction (0.3-1.2), and near-black noise-floor gating preventing sensor noise amplification in deep shadows. Delivered Dehazing & Atmospheric Clarity (F-041) utilizing Dark Channel Prior (DCP) with 15x15 minimum patch filtering, top 0.1% brightest pixel atmospheric light estimation, transmission map bounds (t0=0.10), edge-preserving Box-Filter Guided Filtering with grayscale guidance, and scene radiance recovery. Delivered Denoising & Image Restoration (F-042) implementing Fast Non-Local Means (NL-Means) color/gray filtering and Bilateral edge-preserving filtering with Sobel gradient edge blending. Delivered Motion Blur Reduction & Sharpening (F-043) featuring edge-gradient gated unsharp masking, Laplacian high-pass filtering, and directional motion deblurring with oriented Point Spread Functions (PSF), strictly contrast-enhancing with guaranteed zero generative evidence hallucination. Delivered AI Super-Resolution (F-044) providing 2x and 4x scaling with Intel OpenVINO™ GPU offload (Intel UHD 730), CPU AVX2 fallback, high-fidelity Lanczos-4/Bicubic fallback, and mandatory forensic watermark stamping `[AI ENHANCED - NOT ORIGINAL EVIDENCE]`. Delivered Non-Destructive Enhancement Workspace (F-045) mounted at View 6 in PySide6 Command Center featuring an interactive draggable split-screen slider (ComparisonSplitView) and side-by-side comparative canvas, preset manager (Night Vision, Fog Penetration, Plate Clarity, Face Detail), decoupled asynchronous worker (EnhancementWorker), strict non-destructive isolation (storage/enhanced/), and cryptographic SHA-256 sidecar JSON audit manifests. Full regression and enhancement test suite verified at 280 passing tests (100% pass rate in 38.49s).  
FILES CREATED:  
- `engines/enhancement_engine/__init__.py`
- `engines/enhancement_engine/low_light.py`
- `engines/enhancement_engine/dehazing.py`
- `engines/enhancement_engine/denoiser.py`
- `engines/enhancement_engine/sharpening.py`
- `engines/enhancement_engine/super_resolution.py`
- `engines/enhancement_engine/enhancement_pipeline.py`
- `modules/video_enhancement/__init__.py`
- `modules/video_enhancement/comparison_view.py`
- `modules/video_enhancement/enhancement_widget.py`
- `docs/VIDEO_ENHANCEMENT_VERIFICATION_REPORT.md`
- `tests/unit/test_low_light_enhancement.py`
- `tests/unit/test_dehazing.py`
- `tests/unit/test_denoiser.py`
- `tests/unit/test_sharpening.py`
- `tests/unit/test_super_resolution.py`
- `tests/unit/test_enhancement_pipeline.py`
- `tests/integration/test_enhancement_ui.py`
- `tests/performance/test_enhancement_performance.py`
FILES MODIFIED:  
- `VERSION`
- `core/config/settings.py`
- `app/main.py`
- `docs/FEATURE_REGISTER.md`
- `docs/DEVELOPMENT_STATUS.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULE_SPECIFICATIONS.md`
- `docs/TEST_REPORTS.md`
- `docs/CHANGELOG.md`
FILES DELETED: None  
DATABASE CHANGES: No structural database migrations required; runtime models and audit manifests handle storage metadata.  
DEPENDENCIES CHANGED: None (using existing PySide6, OpenCV, OpenVINO, NumPy, and Python standard libraries).  
TESTS PERFORMED: Automated execution across 280 test cases (243 regression tests + 37 new Phase 9 tests) covering CIE Lab CLAHE luminance expansion, chromatic channel invariance, sigmoid noise gating, adaptive gamma correction, MSRCR multi-scale retinex, Dark Channel Prior calculation, atmospheric light estimation, guided filter transmission refinement, scene radiance recovery, NL-Means noise reduction, Bilateral edge preservation, fast preview denoising, unsharp masking with edge-gradient gating, Laplacian sharpening, directional PSF deblurring, strict non-hallucination verification, 2x and 4x super-resolution scaling, OpenVINO device inspection, Lanczos-4 acutance, mandatory forensic watermarking, pipeline sequencing, preset profile construction, raw recording immutability, sidecar JSON manifest generation, asynchronous worker threads, split-slider interaction, view mode switching, UI widget smoke testing, and 720p/1080p/4K performance benchmarks on Intel hardware.  
TEST RESULTS: 280 passed, 0 failed, 100% pass rate in 38.49s.  
KNOWN ISSUES: Deep learned super-resolution weights require model downloads; deterministic 8-tap Lanczos-4 fallback executes seamlessly in offline air-gapped environments.  
GIT COMMIT: 5e92ef9
