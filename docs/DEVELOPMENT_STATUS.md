# Development Status & Phase Roadmap

## 1. Roadmap Phase Progression

| Phase | Milestone | Status | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 0** | **Foundation & Architecture** | **COMPLETE** | Modular monolith skeleton, pinned dependencies, hardware detector (Intel CPU/UHD 730 GPU, OpenVINO 2026.4.1), worker manager, redacting logger, PostgreSQL/SQLite WAL data layer, PySide6 desktop Command Center with 15 navigation views and dashboard workspace, 17 automated tests (100% pass), all 11 mandatory documents. |
| **Phase 1** | **Desktop UI & Live Monitoring Grid** | **COMPLETE** | Dynamic 1, 4, 9, 16 camera monitoring grid with tile double-click maximization, OSD telemetry overlays (FPS, resolution, status dot), and snapshot capture. |
| **Phase 2** | **Device Integration & RTSP Stream Engine** | **COMPLETE** | ONVIF WS-Discovery (UDP multicast probe), subnet IP scanner, pure-Python ONVIF client with WS-Security PasswordDigest and PTZ, Hikvision/Dahua/CP PLUS adapters, bounded queue RTSP worker engine, and AES-256 credential vault. |
| **Phase 3** | **Stream Polish & PTZ Controller** | **COMPLETE** | Universal PTZ control (ONVIF Profile S/T, Hikvision ISAPI, Dahua CGI), 8-direction pan/tilt + zoom, presets, home position, non-blocking async execution, stream reliability (exponential backoff with jitter, frozen frame detection via perceptual difference hashing, stale timestamp recovery), dynamic main/sub-stream profile switching, live monitoring grid supporting 1, 4, 9, 16, 25, 36, and 64 channels with lazy tile instantiation, double-click maximization, interactive digital zoom (1.0x-5.0x), drag-and-drop, multi-monitor detached video wall, and comprehensive stream diagnostics with credential-redacted export. |
| **Phase 4** | **Recording & Playback Engines** | **COMPLETE** | Continuous/motion/AI segmented recording, pre/post ring buffering, SHA-256 seal, storage volume retention with evidence locking, crash recovery, multi-camera synchronized playback (1/4/9/16), interactive timeline, and forensic MP4 export. |
| **Phase 5** | **AI Inference Core (OpenVINO)** | **COMPLETE** | OpenVINO Intel UHD 730 GPU acceleration pipeline, CPU AVX2 fallback, YOLO object detection (person, car, bus, truck, motorcycle, bicycle), ByteTrack multi-object tracking, strict per-camera tracking isolation, AI event processor with deduplication, snapshot capture, AI-event-triggered recording, and AI Intelligence dashboard workspace. |
| **Phase 6** | **Advanced Video Analytics & Rules**| **COMPLETE** | Polygon intrusion zones (F-013), virtual tripwire line crossing (F-014), loitering dwell time with occlusion tolerance (F-015), people and vehicle counting with real-time occupancy (F-016), movement heatmaps with Jet color contouring (F-017), interactive drawing canvas, rules management UI, and Alembic migration `57a91c3e80ab`. |
| **Phase 7** | **Authorized Face & ANPR Intelligence** | **COMPLETE** | Authorized local face intelligence (F-026), biometric quality filtering, AES-256-GCM hardware-bound template vault, cosine similarity candidate matching, human verification workflows, immutable biometric audit logs, dedicated ANPR engine (F-027) with plate localization, deskewing, CLAHE, offline OCR, positional confusion resolution, regional format validation, vehicle track association caching (10.0s window), watchlist alerts, ANPR search engine with CSV export, PySide6 ANPRWorkspaceWidget and FaceWorkspaceWidget, and Alembic migration `62f4c08e921d`. |
| **Phase 7.1** | **Biometric Security & ANPR Hardening** | **COMPLETE** | Windows DPAPI master key protection, versioned envelopes (`v{ver}:{nonce}:{cipher}`), key rotation with DB re-encryption, PBKDF2 disaster recovery bundles, learned MobileFaceNet 512-d ONNX embeddings, upper-body non-face rejection, genuine/impostor FAR/FRR calibration, learned 36-class plate character CNN, multi-line / two-tier square plate support, 4-tier RBAC, automated 30-day retention enforcement, multi-camera streaming resilience (Hikvision, Dahua, CP PLUS, ONVIF), BIOMETRIC_SECURITY_REVIEW.md report, 178 automated tests (100% pass). |
| **Phase 8** | **Advanced Behaviour Analytics** | **PLANNED** | Virtual line-crossing, perimeter intrusion zones, loitering, crowd density, and abandoned object detectors. |
| **Phase 9** | **Video Enhancement Engine** | **PLANNED** | Low-light brightening, dehazing, sharpening, motion blur reduction, and AI super-resolution (raw footage preserved). |
| **Phase 10** | **Digital Forensics & Authenticity** | **PLANNED** | Cryptographic SHA-256 evidence chain of custody, frame discontinuity audits, duplicate frame analysis, and forensic reports. |
| **Phase 11** | **Network Intelligence Tools** | **PLANNED** | Subnet IP scanner, MAC discovery, ping latency, packet loss, RTSP port verification, and network topology maps. |
| **Phase 12** | **Alarm Management Engine** | **PLANNED** | Real-time incident inbox, visual/audio alert triggers, acknowledgement and operator assignment workflows. |
| **Phase 13** | **Storage & Multi-Site Sync** | **PLANNED** | Storage volume quotas, automatic retention pruning, NAS support, and multi-site configuration. |
| **Phase 14** | **User Management & Reporting** | **PLANNED** | Full RBAC permission manager, session security, and automated PDF/Excel security reporting. |
| **Phase 15** | **Optimization, QA & Windows Packaging**| **PLANNED** | 64-channel load testing, memory leak profiling, PyInstaller Windows packaging, and final production installer. |

---

## 2. Current Sprint Focus

- **Current Version**: `0.7.0-alpha`
- **Completed Tasks**: Phase 0 Foundation (F-001, F-002, F-022), Phase 1 Live View & Discovery UI (F-006), Phase 2 Device Integration & RTSP Stream Engine (F-003, F-004, F-005), Phase 3 Stream Polish, Universal PTZ, 64-Channel Monitoring & Diagnostics (F-028, F-029, F-030, F-031, F-032), Phase 4 Surveillance Recording, Storage Retention & Synchronized Playback Engine (F-007, F-008, F-021), Phase 5 AI Inference Core, Detection & ByteTrack Tracking (F-009, F-010, F-011, F-012), Phase 6 Advanced Video Analytics & Rules (F-013, F-014, F-015, F-016, F-017), Phase 7 Authorized Face & ANPR Intelligence (F-026, F-027), and Phase 7.1 Biometric Security, Validation & Production Hardening Pass.
- **Automated Test Baseline**: 206 passed, 0 failed, 100% pass rate in 31.15s.
- **Next Task**: Phase 8 Advanced Behaviour Analytics, Phase 9 Video Enhancement Engine, or Phase 10 Digital Forensics & Authenticity.

---

## 3. Risk Management & Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **64-Channel Stream Saturation** | High | Substream-based AI processing (640x360) while displaying/recording mainstreams; bounded frame queues with frame dropping on lagging decoders. |
| **Hardware Decode Exhaustion** | Medium | Hardware detection dynamically identifies Intel GPU capabilities and schedules hardware decoders with CPU fallback. |
| **Relational Database Locks** | High | SQLite configured with Write-Ahead Logging (WAL) and 5000ms busy timeout; PostgreSQL available for multi-station deployments. Video binaries stored outside database on file system. |
| **Credential Leakage in Logs** | High | Regular expression-based redacting formatter intercepts and masks RTSP passwords, database DSNs, and auth tokens before logging. |
