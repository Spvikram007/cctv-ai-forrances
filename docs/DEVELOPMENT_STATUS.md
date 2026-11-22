# Development Status & Phase Roadmap

## 1. Roadmap Phase Progression

| Phase | Milestone | Status | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Phase 0** | **Foundation & Architecture** | **COMPLETE** | Modular monolith skeleton, pinned dependencies, hardware detector (Intel CPU/UHD 730 GPU, OpenVINO 2026.4.1), worker manager, redacting logger, PostgreSQL/SQLite WAL data layer, PySide6 desktop Command Center with 15 navigation views and dashboard workspace, 17 automated tests (100% pass), all 11 mandatory documents. |
| **Phase 1** | **Desktop UI & Navigation Polish** | **PLANNED** | Advanced layout switching widgets, responsive splitters, dialogs, site manager interface, and UI settings panels. |
| **Phase 2** | **Device Integration Layer** | **PLANNED** | ONVIF WS-Discovery, ONVIF Profile S/G/T clients, RTSP stream probing, Hikvision ISAPI, Dahua CGI, CP PLUS integration. |
| **Phase 3** | **Live CCTV Monitoring Grid** | **PLANNED** | High-performance 1, 4, 9, 16, 25, 36, 64-channel display grid with substream/mainstream switching, PTZ controls, and auto-reconnect. |
| **Phase 4** | **Recording & Playback Engines** | **PLANNED** | Continuous/motion/AI video segment recording, keyframe indexer, synchronized multi-camera timeline playback, and clip export. |
| **Phase 5** | **AI Inference Core (OpenVINO)** | **PLANNED** | OpenVINO Intel GPU acceleration pipeline, YOLO/object detection, ByteTrack multi-object tracking, and CPU fallback scheduler. |
| **Phase 6** | **Smart Video Investigation** | **PLANNED** | High-speed metadata indexing and parametric search for object classes, clothing attributes, plate numbers, and time windows. |
| **Phase 7** | **Biometric Face & ANPR Intelligence** | **PLANNED** | Authorized local face enrollment and verification (512-d embeddings), ANPR plate detection and OCR pipeline. |
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

- **Completed Task**: Phase 0 Foundation Implementation (F-001, F-002, F-022 initial schema/seeding).
- **Next Task**: Phase 1 & Phase 2: Device Integration Layer (F-003, F-004, F-005) — Implementing ONVIF device discovery, RTSP streaming pipeline with FFmpeg D3D11VA hardware acceleration, and camera credential management.

---

## 3. Risk Management & Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **64-Channel Stream Saturation** | High | Substream-based AI processing (640x360) while displaying/recording mainstreams; bounded frame queues with frame dropping on lagging decoders. |
| **Hardware Decode Exhaustion** | Medium | Hardware detection dynamically identifies Intel GPU capabilities and schedules hardware decoders with CPU fallback. |
| **Relational Database Locks** | High | SQLite configured with Write-Ahead Logging (WAL) and 5000ms busy timeout; PostgreSQL available for multi-station deployments. Video binaries stored outside database on file system. |
| **Credential Leakage in Logs** | High | Regular expression-based redacting formatter intercepts and masks RTSP passwords, database DSNs, and auth tokens before logging. |
