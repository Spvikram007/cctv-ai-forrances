# Module Specifications

## Module 1: Dashboard (`modules/dashboard`)
- **Status**: COMPLETE (Phase 0)
- **Role**: Command Center primary telemetry hub.
- **Components**: Hardware gauges (Intel CPU, RAM, Intel UHD 730 GPU, Storage), 64-channel surveillance summary cards, OpenVINO acceleration panel, live alarm/event ticker.
- **Refresh Frequency**: 3000ms safe non-blocking Qt polling.

## Module 2: Live CCTV Monitoring (`modules/live_monitoring`)
- **Status**: COMPLETE (Phase 1, 2 & Phase 3 Universal PTZ / Stream Polish)
- **Role**: High-capacity multi-stream visual display and monitoring grid.
- **Layouts**: 1, 4, 9, 16, 25, 36, and 64 camera grids implemented (1x1 to 8x8) with lazy on-demand tile allocation.
- **Components**: `LiveViewWidget`, `VideoTileWidget`, `PTZControlWidget`, `DetachedGridWindow`.
- **Features**: Live QPainter rendering, aspect ratio preservation, camera title overlay, status dot indicator (online, reconnecting, frozen, offline), FPS, resolution, and latency telemetry, full-screen tile double-click maximization and previous layout restoration, interactive digital zoom (1.0x-5.0x) with mouse wheel zooming, drag panning, and zoom reset badge, drag-and-drop camera assignment (`dragEnterEvent`/`dropEvent`), status overlays (`[REC]`, `[AI]`, `[PTZ]`), visual snapshot flash feedback, integrated collapsible universal PTZ panel, multi-monitor detached video wall window, keyboard navigation shortcuts (1-7 for layouts, Space to maximize, Escape to restore), right-click context menu (profile switching, PTZ panel toggle, zoom reset, snapshot), and rolling stream diagnostics.

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

## Module 7: Video Analytics & Advanced Behaviour Intelligence (`engines/analytics_engine`, `modules/ai_intelligence`)
- **Status**: COMPLETE (Phase 6 & Phase 8 Advanced Behaviour Analytics)
- **Role**: Intelligent surveillance rule evaluation, virtual perimeters, directional line crossing, dwell time loitering, counting, movement heatmaps, crowd density estimation, abandoned/removed object tracking, fall detection posture analysis, wrong-way detection, and composite behaviour rule composition.
- **Components**: `CameraAnalyticsPipeline`, `AnalyticsManager`, `IntrusionDetector`, `TripwireDetector`, `LoiteringDetector`, `CountingManager`, `HeatmapGenerator`, `CrowdDensityDetector`, `StationaryObjectDetector`, `FallDetector`, `DirectionalDetector`, `BehaviourAnalyticsManager`, `InteractiveAnalyticsCanvas`, `InteractiveBehaviourCanvas`, `AnalyticsRulesWidget`, `BehaviourAnalyticsWidget`.
- **Features**: Normalized [0, 1] ray-casting point-in-polygon intrusion containment, 2D cross-product line crossing with A->B / B->A directional analysis and zero double-crossing guarantee, loitering state machine with 2.0s occlusion grace period tolerance, real-time occupancy and directional class counting, 2D density movement heatmaps with OpenCV Jet color contour rendering, crowd density estimation with single-linkage spatial clustering (warning 3 people/m², critical 5 people/m², 10s persistence), stationary object dwell (60s) with owner proximity association and separation duration (30s) unattended alerts, removed object theft detection (5s), fall detection using rapid downward centroid descent (window <= 1.5s), aspect ratio inversion (w/h >= 1.2), prone dwell confirmation (>= 3.0s) with mandatory human review workflows, directional trajectory analysis with circular wrap-around angle deviation tolerance (+-30°) and sustained wrong-way confirmation (>= 2s), composite AND/OR rules, interactive visual rule canvas, and incident review workflows.

## Module 8: Smart Investigation (`modules/investigation`)
- **Status**: PLANNED (Phase 6)
- **Role**: Metadata search engine across historical detection events.
- **Query Types**: Target class, clothing colors, plate numbers, authorized faces, camera channels, and time windows.

## Module 9: Video Enhancement (`modules/video_enhancement`, `engines/enhancement_engine`)
- **Status**: COMPLETE (Phase 9)
- **Role**: Non-destructive video & image enhancement, low-light visibility recovery, atmospheric dehazing, sensor denoising, motion blur deblurring, AI super-resolution, and legal forensic evidence audit packaging.
- **Components**: `LowLightEnhancer`, `DehazeEnhancer`, `DenoiseEnhancer`, `SharpeningEnhancer`, `SuperResolutionEnhancer`, `EnhancementPipeline`, `EnhancementConfig`, `EnhancementWorker`, `EnhancementManifest`, `PresetProfile`, `ComparisonSplitView`, `VideoEnhancementWidget`.
- **Key Features**:
  - *Low-Light Enhancement (F-040)*: Multi-Scale Retinex with Color Restoration (MSRCR, scales 15, 80, 250), adaptive CLAHE on L* channel in CIE L*a*b* space (clip limit 1.0-10.0), intensity-dependent adaptive gamma correction ($\gamma = 0.3-1.2$), and near-black noise-floor gating preventing amplification of sensor noise.
  - *Dehazing & Atmospheric Clarity (F-041)*: Dark Channel Prior (DCP) with $15 \times 15$ local neighborhood minimum filtering, atmospheric light $A$ estimation from top $0.1\%$ brightest dark-channel pixels, transmission map estimation ($\omega = 0.95, t_0 = 0.10$), edge-preserving Guided Filter transmission map refinement, and radiance recovery.
  - *Denoising & Image Restoration (F-042)*: Fast Non-Local Means (NL-Means) color and grayscale filtering ($h \in [2, 25]$), Bilateral edge-preserving filtering ($d=9, \sigma_{\text{color}}=75, \sigma_{\text{space}}=75$), and gradient-based edge preservation blending.
  - *Motion Blur Reduction & Sharpening (F-043)*: Unsharp masking with Sobel edge-gradient gating (suppressing noise amplification in flat regions), Laplacian second-derivative high-pass filtering, and directional motion deblurring with oriented PSF kernels. Strictly contrast/acutance restoration; guaranteed zero generative detail hallucination.
  - *AI Super-Resolution & Forensic Watermarking (F-044)*: $2\times$ and $4\times$ scaling factor with OpenVINO Intel UHD 730 GPU offload and CPU AVX2 fallback, high-fidelity Lanczos-4/Bicubic fallback, and mandatory visual evidence watermarking stamped at bottom-right: `[AI ENHANCED - NOT ORIGINAL EVIDENCE]`.
  - *Non-Destructive Enhancement Workspace (F-045)*: PySide6 command center mounted at View 6 featuring interactive draggable split-screen slider ($0\%-100\%$) and side-by-side viewports, preset manager (Neutral, Night Vision, Fog Penetration, Plate Clarity, Face Detail), decoupled asynchronous worker (`EnhancementWorker`), strict non-destructive isolation (`storage/enhanced/`), and cryptographic SHA-256 sidecar JSON audit manifests.

## Module 10: Video Forensics (`modules/video_forensics`, `engines/forensic_engine`)
- **Status**: COMPLETE (Phase 10 & Phase 10.1 Security Hardened)
- **Role**: Digital video authenticity verification, frame discontinuity & duplicate frame analysis, container & atom inspection, Windows DPAPI-protected asymmetric signing, authoritative trusted keystores, independent signed checkpoints, controlled evidence locker, append-only Merkle hash-chained custody ledgers, 5-Tier Forensic RBAC, standalone court export packaging, and judicial verification utilities.
- **Components**: `VideoAuthenticityAnalyzer`, `ForensicAnalysisReport`, `FrameDiscontinuity`, `DuplicateFrameCluster`, `TimestampAnomaly`, `ContainerMetadata`, `ForensicSigner`, `TrustedKeyStore`, `KeyStatus`, `SignedEvidenceManifest`, `ChainOfCustodyLedger`, `CustodyEvent`, `CustodyCheckpoint`, `EvidenceLocker`, `EvidencePackager`, `VideoForensicsWidget`.
- **Key Features**:
  - *Video Authenticity & Hash Verification (F-018)*: Chunked SHA-256 binary hashing, container signature & atom structure inspection (`ftyp`, `moov`, `mdat`, `EBML_HEADER`, `RIFF`), and codec profile verification.
  - *Discontinuity & Duplicate Frame Detection (F-018)*: Downscaled $64 \times 36$ perceptual difference analysis; detects frozen sequences ($D < 0.002$), abrupt visual splicing cuts ($D > 0.65$), and timeline omissions without visual jumps.
  - *Timestamp Cadence & Anomaly Analysis (F-018)*: Evaluates Presentation Time Stamps (PTS); flags dropped frames ($\Delta t > 1.5 \times dt$), out-of-order/reversed timestamps ($\Delta t < -0.005\text{s}$), and framerate drift.
  - *Authoritative Trusted KeyStore (F-023)*: Authoritative keystore (`storage/evidence/trust_store/trusted_keys.json`) maintaining standardized SHA-256 key fingerprints ($\text{"SHA256:"} + \text{SHA256}(\text{DER}(\text{SubjectPublicKeyInfo}))$), operator identities, active key status, revocation timestamps, and scheduled rotation workflows. Neutralizes self-signed package trust forgery.
  - *Controlled Evidence Locker & Immutability (F-023)*: Centralized secure vaulting (`storage/evidence/locker/<evidence_id>/`), Windows read-only filesystem attribute enforcement (`FILE_ATTRIBUTE_READONLY`), active locker integrity scanning (`scan_locker_integrity`), and integration guidance for hardware WORM and S3 Object Lock compliance modes.
  - *5-Tier Forensic Role-Based Access Control (F-023)*: Enforces strict permissions across Tier 1 (`ADMIN`), Tier 2 (`INVESTIGATOR`), Tier 3 (`SUPERVISOR`), Tier 4 (`OPERATOR`), and Tier 5 (`VIEWER`). Unauthorized ingest, export, or checkpoint attempts trigger `ForensicAccessDeniedError` and are permanently logged.
  - *Cryptographic Signing Engine (F-023)*: Asymmetric ECDSA (SECP256R1 / NIST P-256) digital signatures with SHA-256. Private signing keys are sealed at rest using Windows Data Protection API (**Windows DPAPI**, `CryptProtectData` with custom hardware entropy `b"CCTV_AI_FORENSIC_SIGNING_ENTROPY_V1"`).
  - *Append-Only Chain-of-Custody Ledger (F-023)*: Merkle-style hash-chained JSONL records ($H_i = \text{SHA256}(H_{i-1} + \text{canonical}(event_i))$) logging every access, view, verification, export, and unauthorized attempt.
  - *Independent Signed Custody Checkpoints (F-023)*: Periodic signed checkpoints stored in an independent directory outside the evidence locker (`storage/evidence/checkpoints/<evidence_id>_checkpoints.json`). Detects malicious admin attacks where an attacker with local filesystem access rewrites past records and recomputes Merkle hashes.
  - *Derived Enhancement Provenance (Phase 9 Integration)*: Automatically detects Phase 9 derived enhanced files, marks them as `DERIVED_ENHANCEMENT`, preserves original source hash and pipeline settings, and burns legal disclaimers.
  - *Standalone Verification Utility & Packages (F-023)*: Exports `.cctvevid` zip containers containing media, signed manifest, public key, custody ledger, signed checkpoints, and standalone CLI verification script (`tools/verify_evidence.py`). Enforces mandatory signature verification with 4 clean exit states (`VERIFIED`, `FAILED`, `UNTRUSTED SIGNING IDENTITY`, `VERIFICATION INCOMPLETE`) and space-safe Windows path quoting.

## Module 11: Camera Integration (`integrations`, `engines/video_engine`)
- **Status**: COMPLETE (Phase 1, 2 & Phase 3 Universal PTZ / Stream Polish)
- **Role**: Hardware communication, discovery layer, and universal PTZ control.
- **Adapters**: ONVIF WS-Discovery (multicast UDP), ONVIF Profile S/T client (WS-Security PasswordDigest, continuous/relative/absolute move, 8-directional control + zoom, presets, home position, system date/time synchronization), Hikvision ISAPI adapter (PTZ continuous XML payloads), Dahua CGI adapter (PTZ continuous cgi commands), CP PLUS adapter, and generic RTSP streamer with bounded queue frame dropping.
- **PTZ Components**: `PTZController`, `PTZCapabilities`, `PTZPreset`, `PTZDirection`, `PTZControlWidget`. Features 8-way directional pan/tilt, zoom in/out, configurable pan/tilt/zoom speeds, preset saving/naming/navigation/removal, home position setting/recall, asynchronous non-blocking thread dispatching, and EventBus telemetry (`ptz.moved`, `ptz.stopped`, `ptz.preset_saved`, `ptz.preset_reached`, `ptz.home_reached`).
- **Compatibility Tools**: `CameraConnectionTester` for multi-stage connectivity validation (TCP socket reachability, RTSP handshake, ONVIF discovery probe), ONVIF system date and time synchronization (`get_system_date_and_time`, `set_system_date_and_time`), and credential protection.

## Module 12: Network Intelligence & Security Audit (`modules/network_intelligence`, `engines/network_engine`)
- **Status**: COMPLETE (Phase 11 & Phase 11.1 Hardened - F-019)
- **Role**: Surveillance subnet scanning, device classification, multi-protocol CCTV diagnostics, continuous telemetry, security auditing, and automated root-cause fault isolation.
- **Components**:
  - `NetworkScanner` (`engines/network_engine/scanner.py`): Authorized CIDR block validation (/20 to /32, max 1024 hosts per pass), `compute_scan_scope()` with bounded enterprise batching, multi-threaded socket probing, ARP cache parsing & Windows IP Helper SendARP API (`ctypes.windll.iphlpapi.SendARP`), ping reachability, duplicate IP & MAC collision detection, IEEE OUI vendor database matching, operator confirmation prompts for non-local or large subnets, immutable audit logging (`storage/logs/scan_audit.jsonl`), and device classification (`IP_CAMERA`, `NVR`, `GATEWAY`, `SWITCH`, `HOST`).
  - `DeviceDiagnosticEngine` (`engines/network_engine/diagnostics.py`): RTSP OPTIONS/DESCRIBE handshake, ONVIF Profile S/T capabilities probe, HTTP/HTTPS web endpoints, ISAPI/CGI vendor queries, root-cause categorization (`CONNECTION_FAILURE`, `AUTHENTICATION_FAILURE`, `INVALID_RTSP_PATH`, `UNSUPPORTED_PROTOCOL`, `STREAM_TIMEOUT`, `PORT_CLOSED`, `DNS_GATEWAY_ERROR`), protocol-level encryption auditing (`rtsp_control_encrypted`, `rtp_media_encrypted`, `srtp_available`, `onvif_auth_enforced`), and strict zero plaintext credential logging (`mask_credentials`).
  - `NetworkPerformanceMonitor` (`engines/network_engine/monitor.py`): Continuous background telemetry tracking real-time measured bandwidth (`measured_bandwidth_bps` via active stream worker counters or network interface deltas) distinguished from estimated bitrate (`estimated_bitrate_bps`), true RFC 3550 Section 6.4.1 smoothed interarrival jitter calculation via RTP packet timestamps vs ping mean latency variation, packet loss (%), and uptime percentage in bounded history queues (`deque(maxlen=120)`). Dynamic congestion detection (`latency > 150ms` or `loss > 5.0%`).
  - `NetworkSecurityAuditor` (`engines/network_engine/security_audit.py`): Non-intrusive security posture inspection with transport encryption disaggregation (`SEC-001A` unencrypted RTSP control, `SEC-001B` unencrypted RTP video transport), plaintext HTTP management (SEC-002), exposed Telnet (SEC-003) and FTP (SEC-004), unauthenticated ONVIF access (SEC-005), and factory default credentials (SEC-006). Verified CVE database with authoritative NVD/CVE URLs and advisory publication dates (Hikvision CVE-2021-36260, Dahua CVE-2021-33044, Dahua CVE-2022-30563, D-Link CVE-2020-25078 password disclosure, CP PLUS KVMS Pro CVE-2023-1518; Pimcore removed). Strict confidence scoring (`CONFIRMED_VULNERABLE`, `POTENTIALLY_VULNERABLE` with `FIRMWARE VERSION UNKNOWN — EXPOSURE UNCONFIRMED`, `UNAFFECTED`) and composite posture scoring (0-100%, Grade A-F).
  - `AutomatedFaultAnalyzer` (`engines/network_engine/fault_analyzer.py`): Automated fault isolation matrix distinguishing `CAMERA_HARDWARE_FAILURE`, `NVR_FAILURE`, `NETWORK_DISCONNECTION`, `AUTHENTICATION_FAILURE`, `DNS_FAILURE`, `RTSP_STREAM_FAILURE`, and `BANDWIDTH_CONGESTION` with operator-gated remediation recommendations.
  - `InteractiveTopologyCanvas` (`modules/network_intelligence/topology_view.py`): Responsive dark surveillance QPainter canvas with hierarchical tier layout (Gateway -> Switches/NVRs -> Cameras & Hosts), glowing status rings, latency badges, zoom/pan, and node selection inspector.
  - `NetworkIntelligenceWidget` (`modules/network_intelligence/network_workspace_widget.py`): PySide6 Command Center workspace mounted at Stacked Index 8 ('Network Tools'). Features summary stat cards, inventory table with real-time text/type filtering, interactive topology canvas, telemetry table (8 columns), CCTV diagnostics & fault panel, security audit & CVE viewer (9 columns with confidence badges), and CSV/JSON export. Fully asynchronous via dedicated `QThread` workers.

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
