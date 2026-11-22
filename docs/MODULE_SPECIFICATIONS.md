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

## Module 5: Human Intelligence (`engines/face_engine`, `engines/detection_engine`)
- **Status**: PLANNED (Phase 7)
- **Role**: Person re-identification, clothing attribute analysis, authorized face matching.
- **Biometrics**: Strict candidate verification workflow; 512-d feature vectors from authorized enrolled identity database only.

## Module 6: Vehicle Intelligence (`engines/anpr_engine`)
- **Status**: PLANNED (Phase 7)
- **Role**: Vehicle classification, directional tracking, license plate localization and OCR.

## Module 7: Behaviour Analytics (`engines/event_engine`)
- **Status**: PLANNED (Phase 8)
- **Role**: Virtual perimeter monitoring, intrusion zones, line-crossing alarms, loitering detection, crowd density calculation.

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
