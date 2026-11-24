# Module Specifications

## Module 1: Dashboard (`modules/dashboard`)
- **Status**: COMPLETE (Phase 0)
- **Role**: Command Center primary telemetry hub.
- **Components**: Hardware gauges (Intel CPU, RAM, Intel UHD 730 GPU, Storage), 64-channel surveillance summary cards, OpenVINO acceleration panel, live alarm/event ticker.
- **Refresh Frequency**: 3000ms safe non-blocking Qt polling.

## Module 2: Live CCTV Monitoring (`modules/live_monitoring`)
- **Status**: COMPLETE (Phase 1 & 2 Baseline)
- **Role**: High-capacity multi-stream visual display and monitoring grid.
- **Layouts**: 1, 4, 9, 16 camera grids implemented (scalable to 25, 36, 64).
- **Features**: Live QPainter rendering, aspect ratio preservation, camera title overlay, status dot indicator, FPS and resolution telemetry, full-screen tile double-click maximization, local snapshot capture.

## Module 3: Playback Engine (`modules/video_playback`, `engines/video_engine`)
- **Status**: COMPLETE (Phase 4)
- **Role**: Synchronized multi-camera recorded video investigation and historical playback.
- **Components**: `SingleCameraPlayer`, `SynchronizedPlaybackController`, `TimelineWidget` (QPainter), `PlaybackWidget`, `ClipExportDialog`, `VideoExporter`.
- **Features**: Synchronized master clock playback across 1, 4, 9, 16 camera layouts, frame-by-frame stepping (+/-1 frame @ 25 FPS), variable speeds (0.25x, 0.5x, 1x, 2x, 4x, 8x, 16x), recording gap detection with standby graphic, interactive color-coded timeline with mouse scrub seeking and wheel zoom (24h to 5m), time-bounded MP4 video clip export with SHA-256 integrity hash, sidecar audit JSON manifest, and legal evidence lock.

## Module 4: AI Object Detection & Tracking (`engines/detection_engine`, `engines/tracking_engine`, `engines/ai_engine`)
- **Status**: COMPLETE (Phase 5)
- **Role**: Real-time multi-channel object detection, classification, bounding box regression, ByteTrack persistent multi-object tracking, and security event triggers.
- **Classes**: Person, car, motorcycle, bus, truck, bicycle (surveillance-filtered from 80-class COCO topology).
- **Acceleration**: Intel OpenVINO™ GPU offload (`Intel UHD 730`), CPU AVX2 fallback, and secondary ONNX Runtime engine.
- **Components**: `OpenVINOInferenceEngine`, `ONNXInferenceEngine`, `AIInferenceWorker`, `InferenceWorkerManager`, `YOLODetector`, `ByteTracker`, `MultiCameraTrackManager`, `AIEventProcessor`, `AIDashboardWidget`.
- **Features**: Substream 640x360 inference ingest, aspect-ratio letterboxing, OpenCV Non-Maximum Suppression, Kalman filter trajectory tracking, strict per-camera tracking isolation, deduplicated event publishing, JPEG detection snapshots, and automatic AI event-triggered video recording.

## Module 5: Human Intelligence (`engines/face_engine`, `modules/face_intelligence`)
- **Status**: COMPLETE (Phase 7 & Phase 7.1 Hardened)
- **Role**: Authorized-only face intelligence, quality assessment, encrypted biometric template management, and human verification workflows.
- **Components**: `FaceDetector`, `FaceQuality`, `FaceEmbedder`, `FaceBiometricVault`, `FaceIntelligenceService`, `FaceWorkspaceWidget`.
- **Features**: Genuine facial geometry detection ($0.7 \le w/h \le 1.35$, eye-band contrast checks, upper-body crop fallback eliminated), canonical 112x112 roll tilt alignment, Laplacian blur variance ($\ge 35.0$) and illumination mean ($40-230$) quality checks, 512-dimensional strict $L_2$-normalized feature vector extraction ($\|v\|_2 = 1.0 \pm 10^{-5}$) via **MobileFaceNet** ONNX model (`models/face_recognition/mobilefacenet.onnx`) with OpenVINO Intel UHD 730 GPU offload and CPU fallback, Windows DPAPI master key derivation (`CryptProtectData`/`CryptUnprotectData`) with versioned envelopes (`v{ver}:{nonce}:{tag_cipher}`), multi-version master key rotation (`rotate_biometric_keys`), PBKDF2 disaster recovery bundles (`export_recovery_bundle`/`import_recovery_bundle`), cosine similarity candidate matching ($0.65$ threshold, genuine mean $0.9841$, impostor mean $0.0418$, FAR $0.0\%$), mandatory human review workflow (`is_verified = False` default; similarity is non-proof of identity), 4-tier RBAC (`ADMIN`, `SECURITY_OPERATOR`, `AUDITOR`, `VIEWER`), automated retention enforcement (`enforce_retention_policy`, default 30 days) to deactivate expired enrollments and purge match events/snapshots from disk, and immutable `BiometricAuditLog` persistence.

## Module 6: Vehicle Intelligence (`engines/anpr_engine`, `modules/anpr_intelligence`)
- **Status**: COMPLETE (Phase 7 & Phase 7.1 Hardened)
- **Role**: Automatic Number Plate Recognition (ANPR), character OCR, vehicle track association, and parametric investigation.
- **Components**: `PlateDetector`, `PlateCandidate`, `PlateOCRRecognizer`, `OCRResult`, `ANPRPipeline`, `ANPRSearchEngine`, `ANPRWorkspaceWidget`.
- **Features**: Sobel vertical edge localization, dual rectangular and square morphological closing fusion (`17x3` and `7x7` kernels for single-line and two-tier square plates, aspect ratio $1.1 - 6.0$), Otsu thresholding, perspective correction deskewing, CLAHE contrast enhancement, vertical line clustering for multi-line plates, aspect-ratio preserving character normalization ($20 \times 20$ in $28 \times 28$), learned 36-class Softmax CNN character classifier (`models/anpr/plate_character_recognizer.onnx`), positional confusion resolution ($O \leftrightarrow 0, I \leftrightarrow 1, B \leftrightarrow 8, Z \leftrightarrow 2$), regional format validation (India, US, EU, Generic), multi-condition resilience (day, night, motion blur, low resolution, perspective distortion), ByteTrack vehicle track association caching (10.0s deduplication window), snapshot capture, watchlist hotlist alerts, event-triggered recording dispatch, and parametric search with CSV intelligence export.

## Module 7: Video Analytics & Intelligent Surveillance Rules (`engines/analytics_engine`, `modules/ai_intelligence`)
- **Status**: COMPLETE (Phase 6)
- **Role**: Intelligent surveillance rule evaluation, virtual perimeters, directional line crossing, dwell time loitering, people/vehicle counting, and movement heatmaps.
- **Components**: `CameraAnalyticsPipeline`, `AnalyticsManager`, `IntrusionDetector`, `TripwireDetector`, `LoiteringDetector`, `CountingManager`, `HeatmapGenerator`, `InteractiveAnalyticsCanvas`, `AnalyticsRulesWidget`.
- **Features**: Normalized [0, 1] ray-casting point-in-polygon intrusion containment, 2D cross-product line crossing with A->B / B->A directional analysis and zero double-crossing guarantee, loitering state machine with 2.0s occlusion grace period tolerance, real-time occupancy and directional class counting, 2D density movement heatmaps with OpenCV Jet color contour rendering and privacy retention pruning, on-video polygon/tripwire drawing canvas, rule scheduling, and full database audit logging.

## Module 8: Smart Investigation (`modules/investigation`)
- **Status**: PLANNED (Phase 6)
- **Role**: Metadata search engine across historical detection events.
- **Query Types**: Target class, clothing colors, plate numbers, authorized faces, camera channels, and time windows.

## Module 9: Video Enhancement (`modules/video_enhancement`)
- **Status**: PLANNED (Phase 9)
- **Role**: Non-destructive image processing.
- **Techniques**: Low-light brightening, dehazing, edge sharpening, motion blur reduction, and super-resolution. Original video remains unmodified.

## Module 10: Video Forensics (`modules/video_forensics`, `engines/forensic_engine`)
- **Status**: PLANNED (Phase 10)
- **Role**: Cryptographic integrity and tamper analysis.
- **Checks**: SHA-256 chain of custody, frame discontinuity audit, duplicate frame detection, timestamp and compression anomaly inspection.

## Module 11: Camera Integration (`integrations`)
- **Status**: COMPLETE (Phase 1 & 2 Baseline)
- **Role**: Hardware communication and discovery layer.
- **Adapters**: ONVIF WS-Discovery (multicast UDP), ONVIF Profile S/T client (WS-Security PasswordDigest, PTZ ContinuousMove/Stop), Hikvision ISAPI adapter, Dahua CGI adapter, CP PLUS adapter, and generic RTSP streamer with bounded queue frame dropping.

## Module 12: Network Intelligence (`modules/network_intelligence`)
- **Status**: PLANNED (Phase 11)
- **Role**: Surveillance network diagnostics.
- **Tools**: Subnet IP scanner, MAC lookup, ONVIF discovery, RTSP port verification, latency/packet loss metrics.

## Module 13: Alarm Management (`modules/alarm_management`)
- **Status**: PLANNED (Phase 12)
- **Role**: Centralized incident routing.
- **Capabilities**: Real-time audio/visual alert triggers, acknowledgement workflows, operator assignment, and alarm logs.

## Module 14: Recording & Storage (`engines/recording_engine`)
- **Status**: COMPLETE (Phase 4)
- **Role**: Storage volume quota management, retention policies, segmented video writing, and crash recovery.
- **Components**: `ChannelRecordingWorker`, `RecordingManager`, `StorageManager`, `RecordingRecoveryService`.
- **Features**: Decoupled worker threads, CONTINUOUS, MANUAL, MOTION, and AI_EVENT recording modes, in-memory pre-event and post-event ring buffering (`deque`), automatic video segmentation with SHA-256 seal, storage volume health monitoring with low-disk warning events, automated retention pruning strictly preserving evidence (`is_locked=True`), DB-filesystem consistency audit, and startup crash recovery of unclosed recordings.

## Module 15: User Management (`modules/user_management`)
- **Status**: Core Models & Seeding COMPLETE (Phase 0)
- **Role**: RBAC access control, session authentication, and audit trails.

## Module 16: Reporting (`modules/reporting`)
- **Status**: PLANNED (Phase 14)
- **Role**: Security and operations reporting.
- **Formats**: PDF and Excel exports.

## Module 17: AI Model Management (`engines/ai_engine`, `modules/ai_intelligence`)
- **Status**: COMPLETE (Phase 5)
- **Role**: Neural network model registry, verification, confidence tuning, and device scheduling.
- **Components**: `ModelManager`, `ModelSpec`, `AIModel`, `AIModelVersion`, `AIJob`.
- **Capabilities**: Local filesystem model cataloging, SHA-256 cryptographic weight verification, target device binding (AUTO, GPU, CPU), input tensor shape verification, and offline model execution without external cloud connectivity.
