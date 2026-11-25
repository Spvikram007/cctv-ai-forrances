# System Architecture Blueprint

## 1. High-Level Architecture Overview

The **CCTV AI Intelligence Platform** is built as a high-performance, modular monolith desktop application engineered specifically for Windows 11. It is designed to handle up to **64 concurrent camera channels** with real-time video decoding, offline deep learning AI inference, multi-channel synchronized playback, cryptographic forensic analysis, and comprehensive alarm routing without relying on external cloud APIs or internet connectivity.

```
+---------------------------------------------------------------------------------------+
|                                PySide6 Desktop UI Layer                               |
|  [Header & Telemetry]  [15-View Sidebar Navigation]  [Stacked Dynamic Workspaces]     |
|  - 64-Channel Grid      - Multi-Timeline Playback    - Live AI Overlay Engine         |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
|                               Core Application Layer                                  |
|  [ApplicationState]  [EventBus Pub/Sub]  [WorkerManager Thread/Process Pool]          |
|  [Pydantic Settings] [Structured Redacting Logger] [Hardware Probing Engine]          |
+---------------------------------------------------------------------------------------+
         |                                |                               |
         v                                v                               v
+------------------+           +----------------------+          +----------------------+
|   Video Engine   |           |      AI Engine       |          |   Storage & Forensics|
| - FFmpeg D3D11VA |           | - Intel OpenVINO™    |          | - Segment Writer     |
| - RTSP Streamers | <-------> | - ONNX Runtime       | <------> | - Keyframe Indexer   |
| - Substream Dist |           | - Intel UHD 730 GPU  |          | - SHA-256 Hasher     |
| - OpenCV Decoders|           | - CPU AVX2 Fallback  |          | - Evidence Locker    |
+------------------+           +----------------------+          +----------------------+
         |                                |                               |
         +--------------------------------+-------------------------------+
                                          |
                                          v
+---------------------------------------------------------------------------------------+
|                             Database & Persistence Layer                              |
|  [SQLAlchemy 2.0 ORM] - Universal Relational Abstraction                              |
|  - Enterprise Target: PostgreSQL (High-capacity metadata, multi-site deployments)     |
|  - Local Offline Target: SQLite with WAL Mode, Foreign Keys & 5000ms Busy Timeout    |
|  - File System: Local Non-Relational Bounded Video & Evidence Chunk Stores            |
+---------------------------------------------------------------------------------------+
```

## 2. Hardware Acceleration Pipeline

Surveillance systems processing 64 channels cannot execute deep learning inference on uncompressed 4K or 1080p main streams without saturating host compute and memory bus. The platform implements a **dual-resolution distribution architecture**:

1. **Main Stream (High Resolution - 1080p to 4K)**:
   - Dedicated to primary display views (1-up, 4-up) and direct-to-disk recording.
   - Hardware accelerated decode using Windows DirectX 11 Video Acceleration (`d3d11va`) or `dxva2`.
2. **Substream (Low Resolution - 640x360 / 640x480)**:
   - Fed into the shared AI Inference Engine.
   - Ingested directly into Intel OpenVINO™ optimized model topologies.
3. **Execution Devices**:
   - Primary: `Intel(R) UHD Graphics 730` (`GPU` OpenVINO plugin) with FP16 precision.
   - Automatic Fallback: `12th Gen Intel(R) Core(TM) i5-12400` (`CPU` OpenVINO plugin) utilizing AVX2 vectorized execution.
   - Inference Scheduler: Adaptive frame sampling (e.g. 5-10 FPS sampling for detection with byte-tracking across skipped frames).

## 3. Core Subsystems

### 3.1 Worker Process & Thread Management
Long-running camera network streams, FFmpeg decoders, and AI inference runners are completely decoupled from the PySide6 UI event loop. Worker pools with thread isolation, health monitoring heartbeats, error boundaries, and auto-restart policies prevent a broken camera RTSP stream from freezing the desktop interface.

### 3.2 Database Strategy
The database architecture employs an abstract repository model via SQLAlchemy 2.0:
- **PostgreSQL**: Used for enterprise networked environments, external reporting servers, and multi-NVR sync.
- **SQLite with WAL Mode**: Used as an instant, zero-configuration local fallback for standalone Windows workstations. Write-Ahead Logging (WAL) ensures non-blocking concurrent readers while background threads log detection events.
- **No Blob Storage in Relational DB**: Video chunks, snapshots, and raw keyframes are strictly stored on the file system with path indexing and SHA-256 hashes recorded in the database.

### 3.3 Security & Zero-Cloud Guarantee
- All network operations are strictly local. No outbound network requests are initiated.
- Credential protection: Passwords, tokens, and RTSP authorization strings are scrubbed by a redacting logging formatter prior to output.
- Role-Based Access Control (RBAC): Administrators, Supervisors, Operators, Investigators, and Viewers have granular permissions enforced at the controller and UI levels.

### 3.4 Video Streaming Pipeline, Reliability & Dynamic Profile Switching
- **Decoupled Worker Architecture**: Each active camera channel runs an isolated `RTSPStreamWorker` thread. Decoding failures, network timeouts, or camera disconnects are handled through automated exponential backoff reconnection loops with randomized jitter, preventing connection storms without impacting other streams or the Qt UI thread.
- **Stream Reliability & Failover**:
  - *Frozen Frame Detection*: Rapid perceptual difference hashing downsamples consecutive frames to $32 \times 18$ grayscale and calculates mean absolute pixel difference ($\le 0.5$ threshold). Frozen streams trigger automated worker reconnection and `stream.frozen` EventBus notifications.
  - *Stale Timestamp Detection*: Detects decoder stalls when timestamp delta exceeds 5.0 seconds.
  - *Corrupt Frame & Decoder Recovery*: Automatically recovers from consecutive frame decode errors with counter-based resets.
  - *Dynamic Profile Switching*: Seamlessly switches between `MAIN` (full resolution for focus/recording) and `SUB` (low bitrate/resolution for multi-channel grids and AI inference) without restarting worker threads.
- **Bounded Frame Buffer**: A thread-safe bounded double-ended queue (`deque(maxlen=30)` for main, `maxlen=5` for substreams) is maintained per channel. Under network latency or processing lag, the queue automatically discards the oldest frame in $O(1)$ time, maintaining low latency and preventing memory bloat.
- **In-Memory Frame Transport**: Video frames are transported as native numpy ndarrays within the process space directly to `VideoTileWidget` (via `QPainter.drawImage`) and AI inference queues, strictly avoiding raw video serialization through JSON or IPC bottlenecks.

### 3.5 Camera Discovery Subsystem
- **ONVIF WS-Discovery**: Sends standardized SOAP probe broadcasts to multicast group `239.255.255.250:3702` (Types: `dn:NetworkVideoTransmitter`). Responses are parsed to extract device service XAddrs, hardware models, and scopes.
- **Subnet IP Scanner**: Concurrently probes common surveillance ports (80, 554, 8000, 8080, 8899, 37777) across user-configurable CIDR blocks.
- **MAC Resolution & Brand Fingerprinting**: Local ARP tables map discovered IPs to MAC addresses. MAC OUI prefixes and scope strings automatically identify Hikvision, Dahua, CP PLUS, Uniview, and Axis devices.

### 3.6 ONVIF, Manufacturer Adapters & Universal PTZ
- **Pure-Python ONVIF Client**: Implements WS-Security UsernameToken authentication with SHA-1 `PasswordDigest`, Nonce, and Created timestamps. Exposes `GetDeviceInformation`, `GetCapabilities`, `GetProfiles`, `GetStreamUri`, Profile S/T PTZ continuous, relative, and absolute move, 8-directional pan/tilt + zoom, preset management (set, goto, get, remove), home position control, and ONVIF system date and time synchronization (`get_system_date_and_time`, `set_system_date_and_time`).
- **NVR/DVR & Vendor Adapters**: Dedicated HTTP/REST adapters for Hikvision ISAPI (`/ISAPI/ContentMgmt/InputProxy/channels`, `/ISAPI/PTZCtrl/channels/{ch}/continuous`), Dahua CGI (`/cgi-bin/configManager.cgi`, `/cgi-bin/ptz.cgi`), and CP PLUS map recorder channels to individual camera streams and execute vendor-native PTZ commands.
- **Connection Testing Interface (`CameraConnectionTester`)**: Multi-phase diagnostic tool testing TCP socket reachability, RTSP handshake validation, and ONVIF capability discovery prior to camera registration.

### 3.7 Local Credential Vault
- **AES-256-GCM Encryption**: Device passwords and authentication credentials are encrypted using `CredentialVault` before being written to the database. Master keys are derived using PBKDF2HMAC (100,000 iterations) salted and bound to local machine hardware identity. Passwords are never stored or logged in plaintext.

### 3.8 Recording Engine & Storage Management
- **Dedicated Channel Recording Workers**: Each channel can run an independent `ChannelRecordingWorker` thread decoupled from live stream rendering and Qt UI loops. Supports CONTINUOUS, MANUAL, MOTION, and AI_EVENT modes.
- **Pre-Event & Post-Event Ring Buffering**: In-memory ring buffer (`deque(maxlen=pre_sec * fps)`) stores uncompressed frames prior to event triggers. When motion or AI events fire, buffered pre-event frames are flushed at the head of the event segment, ensuring zero lead-time data loss.
- **Segmentation & SHA-256 Sealing**: Continuous footage is automatically segmented into standard intervals (configurable from 60s to 900s). Each completed MP4 segment is hashed with SHA-256 and sealed in the database catalog with size and millisecond timestamps.
- **Storage Quota & Retention Pruning**: `StorageManager` tracks volume capacity, free disk space, and emits `WARNING_LOW_DISK` alerts when thresholds (85% warning, 95% critical) are crossed. Automatic retention pruning cleans up expired unlocked recordings while strictly guaranteeing that files flagged as evidence (`is_locked == True`) are never deleted.
- **Crash & Power-Loss Recovery**: `RecordingRecoveryService` automatically scans for unfinalized `ACTIVE` segments at startup, probes actual video duration and frame counts via OpenCV, computes cryptographic hashes, and updates records to `RECOVERED` status.

### 3.9 Synchronized Playback & Forensic Video Export
- **Master Playback Clock**: `SynchronizedPlaybackController` drives multi-camera synchronized playback via a high-precision master UTC clock. Supports variable playback speeds (0.25x, 0.5x, 1x, 2x, 4x, 8x, 16x) and single-frame stepping (+/-1 frame at 25 FPS).
- **SingleCameraPlayer & Gap Handling**: Decodes segment MP4 files on demand and uses `CAP_PROP_POS_MSEC` for millisecond-level timestamp seeking. When a channel has no footage at a given timestamp, the player automatically identifies the recording gap and renders a standardized standby gap graphic with timestamp telemetry.
- **Interactive Timeline Widget**: Custom `QPainter` widget rendering 24-hour channel tracks with color-coded recording modes (green for continuous, amber for motion, cyan for AI events, purple for manual). Supports mouse drag scrubbing, click seeking, and mouse wheel zoom (from 24 hours down to 5 minutes).
- **Video Export Engine (`VideoExporter`)**: Extracts time-bounded MP4 clips across single or multiple recording segments, computes SHA-256 file checksums, generates sidecar audit JSON manifests, and automatically locks source recordings as protected evidence when requested.

### 3.10 AI Inference Pipeline & OpenVINO Hardware Acceleration
- **Decoupled Worker Architecture**: Each active camera channel can be bound to an isolated `AIInferenceWorker` thread operating completely outside the Qt UI event loop and video recording threads.
- **Hardware Acceleration Tiering**: Automatically detects host compute resources via `OpenVINOInferenceEngine`. Targets `Intel(R) UHD Graphics 730` (`GPU` OpenVINO plugin) with FP16 precision, with automatic zero-disruption fallback to `12th Gen Intel(R) Core(TM) i5-12400` (`CPU` plugin) using AVX2 vectorized execution. Secondary fallback to `ONNXRuntime` CPU/DirectML engine is supported.
- **Adaptive Frame Sampling & Backpressure**: Incoming 25/30 FPS video frames are sampled at a configurable inference rate (default 5.0 FPS) to conserve compute bandwidth. Bounded frame queues (`deque(maxlen=30)`) ensure that lagging inference threads discard oldest frames in $O(1)$ time without memory growth.
- **Fault-Isolation Guarantee**: Video stream decoding and continuous recording workers execute in separate threads from AI inference workers. If an AI inference worker encounters an unhandled model error, GPU driver fault, or crash, the stream decoding and continuous recording workers continue capturing and writing video frames without interruption.

### 3.11 Object Detection & Multi-Object Tracking (ByteTrack)
- **YOLO Detection Engine**: Preprocessing implements aspect-ratio letterboxing to 640x640 with 114 gray fill, float32 normalization to $[0, 1]$, and NCHW tensor formatting. Postprocessing applies confidence thresholding (default $\ge 0.50$), class filtering for surveillance classes (person, car, bus, truck, motorcycle, bicycle), and OpenCV Non-Maximum Suppression (NMS, IoU threshold $0.45$). Bounding boxes are decoded back into original video resolution and normalized $[0, 1]$ coordinates.
- **ByteTrack Tracking Algorithm**: Multi-object tracking associates every detection box using a two-stage Hungarian assignment algorithm. High-confidence detections are matched first against active Kalman filter tracks. Unmatched active tracks are then associated with low-confidence detections ($0.10 \le \text{conf} < 0.50$) to maintain tracks through occlusion and motion blur. Lost tracks are maintained for up to 30 frames and recovered upon reappearance.
- **Strict Per-Camera Tracker Isolation**: Tracking state is maintained by `MultiCameraTrackManager` using isolated `ByteTracker` instances per channel. Track IDs are strictly scoped to individual cameras to prevent false identity sharing across distinct geographical views.
- **AI Event Processor & Deduplication**: High-severity detections (person, vehicle entry) generate `DETECTION_*` events routed to `EventBus` and trigger automatic event-based video recording via `RecordingManager.trigger_event_recording()`. `EventDeduplicator` enforces a configurable suppression window (default 5.0s) to prevent alarm flooding for persistent entities. Snapshots are sealed to local disk with timestamped paths.

### 3.12 Video Analytics Architecture & Intelligent Surveillance Rules
- **Computational Geometry Engine (`engines/analytics_engine/geometry.py`)**: Normalized coordinate space $[0.0, 1.0]$. Implements robust ray-casting point-in-polygon tests with boundary inclusivity, line segment intersection based on signed 2D cross-product orientation, and directional vector analysis ($A \to B$ vs $B \to A$).
- **Intrusion Detection (`IntrusionDetector`)**: Evaluates track ground contact points against polygon zones. Tracks entry and exit transition events with configurable class filtering, confidence thresholds, and suppression windows.
- **Tripwire & Line Crossing (`TripwireDetector`)**: Evaluates trajectory segment intersections across virtual lines. Determines crossing direction ($A \to B$, $B \to A$, or bidirectional) and enforces a per-track crossing cache guaranteeing zero duplicate counts per crossing.
- **Loitering Detection (`LoiteringDetector`)**: Tracks continuous dwell time of objects inside defined polygon zones. Features temporary occlusion tolerance (2.0s grace period) so that transient tracking dropouts do not reset dwell timers.
- **People & Vehicle Counting & Occupancy (`CountingManager`)**: Maintains directional entry/exit counters categorized by person vs vehicle classes. Calculates real-time occupancy ($\max(0, \text{Total\_In} - \text{Total\_Out})$) and per-zone instantaneous occupancy. Aggregates stats into hourly and daily summary buckets.
- **Movement Heatmaps (`HeatmapGenerator`)**: Accumulates trajectory points from active tracks into a 2D density matrix ($64 \times 36$ or configurable). Renders OpenCV Jet color contour images with optional Gaussian smoothing. Supports time-window filtering and automatic privacy retention pruning.
- **Analytics Management & UI (`AnalyticsManager`, `AnalyticsRulesWidget`)**: Centralized pipeline orchestration per camera stream. Exposes interactive drawing canvas (`InteractiveAnalyticsCanvas`) for on-video polygon and tripwire authoring, rule scheduling, parameter configuration, counter resets, and audit trail logging. Fault-isolated from video decoding and continuous recording.

### 3.13 Authorized Face Intelligence, Cryptographic Biometric Vault & ANPR Engine
- **Dedicated Local ANPR Engine (`engines/anpr_engine`)**: Fully local offline license plate recognition with deep learned character classification and multi-line plate support.
  - *Plate Localization (`PlateDetector`)*: Preprocessing applies bilateral filtering, Sobel vertical gradient extraction to isolate high-density character strokes, dual rectangular morphological fusion (`17x3` horizontal and `7x7` square kernels to capture both single-line and two-tier square plates, aspect ratio $1.1 \le AR \le 6.0$, area bounds). Perspective correction deskews angled plates, followed by CLAHE contrast equalization and standardization to $200 \times 50$.
  - *Offline OCR Recognition (`PlateOCRRecognizer`)*: Character segmentation extracts bounding boxes and performs vertical line clustering to accurately handle multi-line / two-tier plates. Each character crop is aspect-ratio scaled into a centered $20 \times 20$ region inside a standard $28 \times 28$ canvas (`_normalize_character_crop`). Inference executes via a learned 36-class Softmax CNN (`models/anpr/plate_character_recognizer.onnx`) or calibrated correlation fallback. Positional character confusion disambiguation resolves alphanumeric ambiguities ($O \leftrightarrow 0$, $I \leftrightarrow 1$, $B \leftrightarrow 8$, $Z \leftrightarrow 2$) based on regional syntax templates (India, US, EU, Generic).
  - *Track Association & Deduplication (`ANPRPipeline`)*: Associates recognized plates with persistent ByteTrack vehicle `track_id`s, caching results for 10.0 seconds to bypass redundant OCR operations on continuous vehicle tracks. Dispatches watchlist alerts (`WATCHLIST_ALERT`), saves cropped plate and vehicle snapshots to disk, and triggers event-based recording.
  - *ANPR Search Engine (`ANPRSearchEngine`)*: Provides parametric wildcard searching (`*`, `?`), channel filtering, confidence thresholds, and review status flags with CSV intelligence export.
- **Authorized Face Intelligence & Privacy Architecture (`engines/face_engine`)**: Strictly restricted to authorized enrolled identities. Un-enrolled individuals are never identified. Mathematical similarity scores are explicitly treated as correlation metrics, requiring human operator confirmation (`is_verified = False` by default).
  - *Strict Facial Detection & Quality (`FaceDetector`)*: Locates genuine facial geometry using Haar cascades. Upper-body person crop fallback is strictly eliminated. Enforces facial aspect ratio bounds ($0.7 \le w/h \le 1.35$), eye-band contrast symmetry, and canonical $112 \times 112$ roll tilt alignment. Strict `FaceQuality` assessment evaluates illumination mean ($40 \le \mu \le 230$) and sharpness via Laplacian variance ($\sigma^2 \ge 35.0$), automatically rejecting non-faces or degraded images.
  - *Deep Biometric Feature Extraction (`FaceEmbedder`)*: Generates 512-dimensional feature vectors using **MobileFaceNet** ONNX model (`models/face_recognition/mobilefacenet.onnx`) compiled via Intel OpenVINO™ with Intel UHD 730 GPU offload and CPU fallback (or ONNX Runtime). Enforces strict unit normalization ($\|v\|_2 = 1.0 \pm 10^{-5}$). Operates at a calibrated cosine similarity threshold of $0.65$ (separation gap $0.9423$, FAR $0.0\%$, FRR $0.0\%$).
  - *Hardware-Backed Biometric Vault (`FaceBiometricVault`)*: Enforces native Windows Data Protection API (**Windows DPAPI**, `CryptProtectData` / `CryptUnprotectData` via `ctypes.windll.crypt32`) with custom application entropy. Generates random 256-bit AES master keys serialized into versioned envelopes (`v{ver}:{nonce_hex}:{ciphertext_tag_hex}`). Supports master key rotation (`rotate_biometric_keys`) archiving historical keys in an encrypted keystore, tamper detection via AEAD authentication tags, and disaster recovery bundles (`export_recovery_bundle`, `import_recovery_bundle`) encrypted via PBKDF2-HMAC-SHA256 (250,000 iterations) + AES-256-GCM.
  - *Biometric RBAC, Retention & Audit Trail (`FaceIntelligenceService`)*: Enforces 4-tier Role-Based Access Control (`ADMIN`, `SECURITY_OPERATOR`, `AUDITOR`, `VIEWER`), automated retention enforcement (`enforce_retention_policy`, default 30 days) to deactivate expired enrollments and purge old match events/snapshots from disk, and maintains immutable `biometric_audit_logs`.
  - *Surveillance Workspace Integration (`modules/anpr_intelligence`, `modules/face_intelligence`)*: PySide6 `ANPRWorkspaceWidget` mounted at stacked index 4 ('Investigation') and AI dashboard sub-tab; `FaceWorkspaceWidget` mounted in AI dashboard sub-tab.

### 3.14 Universal PTZ, Multi-Layout Live Monitoring (1-64 Channels) & Stream Diagnostics
- **Universal PTZ Controller (`engines/video_engine/ptz_controller.py`)**:
  - *Unified Dispatcher*: Abstracts ONVIF Profile S/T, Hikvision ISAPI, Dahua CGI, and simulated devices behind a uniform API. Supports 8 directional vectors (`UP`, `DOWN`, `LEFT`, `RIGHT`, `UP_LEFT`, `UP_RIGHT`, `DOWN_LEFT`, `DOWN_RIGHT`), zoom in/out, and discrete stops.
  - *Preset & Home Management*: Provides preset creation, naming, navigation, deletion, and home position return.
  - *Asynchronous Non-Blocking Execution*: Dispatches PTZ network calls on background threads via `dispatch_async`, guaranteeing zero UI thread freezes during network timeouts. Emits telemetry events over `EventBus` (`ptz.moved`, `ptz.stopped`, `ptz.preset_saved`, etc.).
- **Scalable 64-Channel Monitoring Grid (`modules/live_monitoring/live_view_widget.py`)**:
  - *Layout Support*: Implements 1, 4, 9, 16, 25, 36, and 64 channel matrix layouts ($1 \times 1$ through $8 \times 8$). Employs lazy tile instantiation ensuring optimal startup performance and backward test compatibility.
  - *Tile Maximization & Restoration*: Double-click tile maximization with single-key/double-click restoration to previous layout geometry.
  - *Interactive Digital Zoom & Pan*: Mouse-wheel driven continuous zoom ($1.0\times$ to $5.0\times$) with left-click drag panning, bounding viewport clamping, and one-click reset badge.
  - *Drag-and-Drop Camera Assignment*: Reassigns camera channels directly to video tiles using native Qt drag-and-drop.
  - *Multi-Monitor Support*: `DetachedGridWindow` detaches the live view matrix into a standalone borderless or maximized window for dedicated multi-monitor security consoles.
  - *Keyboard Accelerators*: Fast-switching shortcuts (keys `1` to `7` for 1 to 64 channel grids, `Space` to maximize/restore, `Escape` to reset zoom or maximize).
- **Stream Diagnostics & Telemetry (`engines/video_engine/stream_metrics.py`, `stream_manager.py`)**:
  - *Comprehensive Real-Time Metrics*: Measures active FPS, resolution, end-to-end latency, packet loss %, reconnect counters, decoder error counters, frame drop rates, and bounded queue utilization.
  - *Rolling Health Event Log*: Maintains sliding event histories (`StreamHealthHistory`) with timestamped anomaly records.
  - *Credential-Redacted Export*: Structured diagnostics logs (`export_diagnostics_log`) scrub credentials and RTSP passwords prior to export.

### 3.15 Advanced Behaviour Analytics Subsystem (Phase 8)
- **Behaviour Detectors Engine (`engines/analytics_engine/behaviour_detectors.py`)**:
  - *Crowd Density & Occupancy (F-035)*: Evaluates person track bounding-box spatial clustering using single-linkage distance graph partitioning. Calculates physical or normalized surface area density ($\text{people}/\text{m}^2$). Classifies severity (NORMAL, WARNING $\ge 3\text{ people}/\text{m}^2$, CRITICAL $\ge 5\text{ people}/\text{m}^2$) and enforces an alert persistence timer ($10\text{s}$) to filter transient crowd flurries.
  - *Stationary, Abandoned & Removed Objects (F-036)*: Identifies candidate stationary objects (backpacks, suitcases, packages, vehicles). Associates depositing person tracks as owners within proximity. Monitors owner separation distance ($> 3\text{m}$ / $0.15$ norm); triggers `UNATTENDED_OBJECT` after $30\text{s}$ separation and `ABANDONED_OBJECT` after $60\text{s}$ stationary dwell. Confirms `REMOVED_OBJECT` (theft/removal) when a previously confirmed stationary object disappears for $\ge 5\text{s}$.
  - *Human Fall Detection & Posture Analysis (F-037)*: Geometric posture analysis combining downward vertical centroid velocity ($\Delta y \ge 0.08$ in $\le 1.5\text{s}$), aspect-ratio inversion ($w/h \ge 1.2$, detecting prone horizontal alignment), and sustained prone dwell confirmation ($\ge 3.0\text{s}$). Rejects gentle sitting or transient shoe-tying. Flags all alerts with `requires_human_review = True` and explicit disclaimers.
  - *Directional Trajectory & Wrong-Way Analysis (F-038)*: Calculates trajectory heading angle ($\theta \in [0^\circ, 360^\circ)$) over recent motion vectors. Computes angular deviation against permitted corridor flow with circular wrap-around handling ($\Delta \theta \le \pm 30^\circ$). Filters stationary jitter via minimum displacement thresholds ($1.5\text{m}$). Confirms sustained wrong-way travel ($\ge 2.0\text{s}$) before firing alarms.
  - *Behaviour Rule Coordinator & UI (F-039)*: `BehaviourAnalyticsManager` provides composite multi-condition rule evaluation with `AND` / `OR` Boolean logic, rule scheduling, and duplicate alert suppression ($30\text{s}$). Integrated with PySide6 `BehaviourAnalyticsWidget` featuring interactive drawing canvas (`InteractiveBehaviourCanvas`), real-time alert metrics, and operator incident confirmation / false-positive dismissal workflows.

### 3.16 Video Enhancement Engine & Non-Destructive Forensic Workspace Subsystem (Phase 9)
- **Mathematical & Algorithmic Foundations (`engines/enhancement_engine`)**:
  - *Low-Light Enhancement (F-040, `low_light.py`)*: Multi-Scale Retinex with Color Restoration (MSRCR) computes weighted logarithmic luminance ratios over Gaussian blur scales ($\sigma \in \{15, 80, 250\}$). Adaptive Contrast Limited Histogram Equalization (CLAHE) operates strictly on the $L^*$ channel in CIE $L^*a^*b^*$ color space, preserving chromatic channels ($a^*, b^*$) to prevent unnatural color shifts. Intensity-dependent adaptive gamma correction stretches dark tones without blowing out bright highlights. Near-black noise-floor gating employs a sigmoid attenuation transfer function around $\tau = 18.0$ to suppress noise amplification in deep sensor shadows.
  - *Dehazing & Atmospheric Clarity (F-041, `dehazing.py`)*: Restores visibility in foggy, smoky, or dusty footage using Dark Channel Prior (DCP) with $15 \times 15$ minimum filtering. Atmospheric light $A$ is robustly estimated from the top $0.1\%$ brightest dark-channel pixels. Transmission map estimation ($\omega = 0.95, t_0 = 0.10$) is refined via edge-preserving Box-Filter Guided Filtering ($r=40, \epsilon=10^{-3}$) using grayscale guidance, eliminating depth halo artifacts prior to scene radiance recovery.
  - *Denoising & Image Restoration (F-042, `denoiser.py`)*: Suppresses high-ISO sensor noise and compression artifacts using Fast Non-Local Means (NL-Means) color filtering ($h \in [2, 25]$) and Bilateral edge-preserving filtering ($d=9, \sigma_{\text{color}}=75, \sigma_{\text{space}}=75$). Employs Sobel gradient edge blending to preserve fine optical boundaries.
  - *Motion Blur Reduction & Sharpening (F-043, `sharpening.py`)*: Clarifies optical softening using unsharp masking gated by Sobel gradient magnitude thresholds to prevent noise grain amplification. Supports Laplacian second-derivative high-pass filtering and directional deblurring using oriented Point Spread Functions (PSF). Strictly contrast and acutance restoration; guaranteed zero generative detail hallucination.
  - *AI Super-Resolution & Forensic Watermarking (F-044, `super_resolution.py`)*: Deep learned $2\times$ and $4\times$ resolution scaling targeting Intel OpenVINO™ GPU offload (`Intel UHD 730`) with CPU AVX2 fallback and 8-tap Lanczos-4/Bicubic deterministic fallback. Enforces mandatory forensic watermarking: `[AI ENHANCED - NOT ORIGINAL EVIDENCE]` burned at bottom-right with high-contrast backing box to preserve legal evidentiary integrity.
- **Non-Destructive Storage Architecture & Provenance (F-045, `enhancement_pipeline.py`)**:
  - *Immutability Guarantee*: Raw surveillance recordings in `storage/recordings/` are opened read-only and are strictly immutable.
  - *Isolated Enhanced Repository*: All enhanced snapshots and video clips are stored separately in `storage/enhanced/snapshots/` and `storage/enhanced/recordings/`.
  - *Cryptographic Audit Manifests (`EnhancementManifest`)*: Every exported file generates a sidecar `.manifest.json` capturing the source SHA-256 hash, enhanced SHA-256 hash, input/output resolutions, complete filter configuration, processing latency, timestamp, operator ID, and explicit legal disclaimers.
- **Asynchronous Execution & Comparative UI (`modules/video_enhancement`)**:
  - *Decoupled Execution*: `EnhancementWorker` executes frame and clip processing in dedicated background threads, decoupling heavy matrix operations from the PySide6 UI and live RTSP streaming threads.
  - *Interactive Comparative Canvas (`ComparisonSplitView`)*: Provides a 60 FPS QPainter interactive split-screen viewer with a draggable vertical divider slider ($0\%-100\%$) and side-by-side comparative views.
  - *Command Center Integration*: PySide6 `VideoEnhancementWidget` wired at navigation index 6 in `MainWindow.stack`, equipped with preset profiles ("Night Vision", "Fog Penetration", "Plate Clarity", "Face Detail"), real-time parameter controls, and export dialogs.

### 3.17 Digital Forensics, Cryptographic Evidence Locker & Authenticity Subsystem (Phase 10 & 10.1)
- **Video Authenticity & Frame Integrity Engine (`engines/forensic_engine/authenticity.py`)**:
  - *Chunked Cryptographic Hashing*: Calculates 64KB-buffered binary SHA-256 digests ensuring high-speed streaming calculation on large gigabyte-scale surveillance footage without memory exhaustion.
  - *Perceptual Frame Difference & Discontinuity Analysis*: Computes normalized grayscale mean absolute difference $D$ over downsampled $64 \times 36$ frames. Detects duplicate/frozen sequences ($D < 0.002$), abrupt visual splicing transitions ($D > 0.65$), and missing timeline sequences.
  - *Timestamp Cadence & Presentation Time Stamp (PTS) Analysis*: Inspects frame timestamps; identifies frame omission gaps ($\Delta PTS > 1.5 \times \Delta t_{\text{nom}}$), timestamp reversals ($\Delta PTS < -0.005\text{s}$, indicating spliced edits or corrupt multiplexing), and framerate drift.
  - *Container & Atom Structure Inspection*: Parses container signatures (`ftyp`, `moov`, `mdat`, `EBML_HEADER`, `RIFF`), codec profiles, bitrates, and keyframe indexes. Detects truncated metadata or post-acquisition binary modifications.
  - *Judicial Disclaimer Enforcement*: Enforces standardized forensic integrity notice distinguishing digital file authenticity from physical scene veracity.
- **Trusted Public-Key Infrastructure & Signing Engine (`engines/forensic_engine/crypto_signer.py`)**:
  - *Windows DPAPI Asymmetric Signing*: ECDSA (NIST P-256 / SECP256R1) asymmetric keypairs. Private signing keys are sealed using Windows Data Protection API (`CryptProtectData` with application entropy `b"CCTV_AI_FORENSIC_SIGNING_ENTROPY_V1"`) in `storage/evidence/.keys/forensic_signing_key.dpapi`.
  - *Authoritative Trusted KeyStore (`TrustedKeyStore`)*: Authoritative trust store (`storage/evidence/trust_store/trusted_keys.json`) maintaining standardized SHA-256 key fingerprints ($\text{"SHA256:"} + \text{SHA256}(\text{DER}(\text{SubjectPublicKeyInfo}))$), operator identities, and lifecycle status (`ACTIVE`, `REVOKED`, `EXPIRED`).
  - *Self-Trust Injection Neutralization*: Prevents exported packages from establishing trust in self-supplied public keys. Verification strictly validates that candidate key fingerprints match an authorized root entry in the trust store.
  - *Key Rotation & Revocation*: Supports atomic key rotation with automated status updates, revocation timestamping, and justification logging.
- **Controlled Evidence Locker & Independent Signed Checkpoints (`engines/forensic_engine/evidence_locker.py`)**:
  - *Secure Evidence Vaulting*: Centralized locker storage at `storage/evidence/locker/<evidence_id>/`. Ingested evidence files are protected with Windows filesystem read-only locks (`FILE_ATTRIBUTE_READONLY`).
  - *Storage Immutability Architecture*: Explicitly recognizes the limits of OS-level file attributes against privileged processes. For judicial and high-assurance environments, integrates recommendations for Hardware WORM (Write Once, Read Many) optical/NAS storage and AWS S3 Object Lock in Compliance Mode.
  - *Active Locker Integrity Scanner (`scan_locker_integrity`)*: Continuously audits all vaulted evidence items, cross-verifies media SHA-256, manifest signatures, key trust, ledger hash chains, and external checkpoints. Dispatches tamper alarms upon any violation.
  - *Append-Only Merkle Hash-Chained Custody Ledger (`ChainOfCustodyLedger`)*: Every access, view, verification, export, or unauthorized attempt is recorded in `chain_of_custody.jsonl` where $H_i = \text{SHA256}(H_{i-1} + \text{canonical}(event_i))$.
  - *Periodic Signed Custody Checkpoints (`CustodyCheckpoint`)*: Checkpoints are digitally signed and stored in an **independent directory outside the evidence locker** (`storage/evidence/checkpoints/<evidence_id>_checkpoints.json`). Defeats malicious administrator attacks where an attacker with filesystem access attempts to rewrite past ledger records and recalculate Merkle hashes.
  - *5-Tier Forensic Role-Based Access Control (RBAC)*: Enforces granular permissions across 5 distinct roles: Tier 1 (`ADMIN`), Tier 2 (`INVESTIGATOR`), Tier 3 (`SUPERVISOR`), Tier 4 (`OPERATOR`), and Tier 5 (`VIEWER`). Unauthorized attempts raise `ForensicAccessDeniedError` and are permanently logged to the custody ledger.
  - *Derived Enhancement Provenance (Phase 9 Integration)*: Automatically detects Phase 9 derived outputs, assigns `DERIVED_ENHANCEMENT` classification, retains source SHA-256, pipeline settings, software version, and legal warnings.
- **Standalone Judicial Packaging & Verification (`engines/forensic_engine/evidence_packager.py`, `tools/verify_evidence.py`)**:
  - *Structured Export Containers*: Assembles self-contained `.cctvevid` (zip archives) containing the evidence media, signed `manifest.json`, detached `manifest.sig`, public verification key (`public_key.pem`), chain of custody ledger, signed checkpoints, and court instructions.
  - *Mandatory Signature Verification & Four-State Results*: `tools/verify_evidence.py` enforces mandatory cryptographic checks. Distinguishes 4 clean exit states: `0 = VERIFIED`, `1 = FAILED` (tamper detected), `2 = UNTRUSTED SIGNING IDENTITY` (self-signed / unrecognized key), and `3 = VERIFICATION INCOMPLETE` (missing `cryptography` dependency). Never reports PASS if cryptographic verification was skipped.
  - *Space-Safe CLI Tooling*: CLI documentation and execution examples enforce quoted string handling for Windows directory paths with spaces.
- **Command Center Workspace Integration (`modules/video_forensics`)**:
  - PySide6 `VideoForensicsWidget` mounted at stacked index 5 ('Video Forensics'). Features evidence locker browser, detail tabs (Integrity Audit, Custody Ledger & Checkpoints, Digital Signature & Key Trust, Legal Notice & 5-Tier RBAC), one-click verification, locker integrity scanning, and package export dialogs.
- **Network Intelligence & Security Audit Engine (`engines/network_engine`) (Phase 11 & Phase 11.1 Hardened)**:
  - *Authorized Subnet Scanning (`scanner.py`)*: Multi-threaded scanner strictly enforcing authorized IPv4 CIDR blocks (/20 to /32, max 1024 hosts per single pass). Partitioned enterprise batching via `compute_scan_scope()`, operator confirmation prompts for subnets outside local interfaces or > 256 hosts, and immutable audit logging to `storage/logs/scan_audit.jsonl`. Rejects loopback, multicast, and 0.0.0.0/0 global Internet ranges.
  - *ARP & MAC Resolution*: Dual-mode resolution via local ARP cache table parsing and Windows IP Helper SendARP API (`ctypes.windll.iphlpapi.SendARP`).
  - *Hardware OUI Identification & Classification*: Database of surveillance and infrastructure vendors (Hikvision, Dahua, CP PLUS, Axis, Hanwha, Uniview, Cisco, etc.). Multi-factor classification into `IP_CAMERA`, `NVR`, `GATEWAY`, `SWITCH`, and `HOST`.
  - *Duplicate IP & MAC Collision Detection*: Real-time collision analyzer flagging IP-to-multiple-MAC collisions and shared physical MAC anomalies.
  - *Multi-Protocol CCTV Diagnostics (`diagnostics.py`)*: Probes RTSP (OPTIONS/DESCRIBE handshake), ONVIF Profile S/T discovery, HTTP/HTTPS web endpoints, and ISAPI/CGI vendor adapters. Classifies root causes into `CONNECTION_FAILURE`, `AUTHENTICATION_FAILURE`, `INVALID_RTSP_PATH`, `UNSUPPORTED_PROTOCOL`, `STREAM_TIMEOUT`, `PORT_CLOSED`, and `DNS_GATEWAY_ERROR`. Assesses protocol-level encryption (`rtsp_control_encrypted`, `rtp_media_encrypted`, `srtp_available`, `onvif_auth_enforced`).
  - *Zero Plaintext Credential Logging*: Strictly masks passwords in all connection strings, URLs, and diagnostic logs (`rtsp://user:***@host:port/path`).
  - *Performance Telemetry & Bounded History (`monitor.py`)*: Continuous background telemetry tracking real-time measured bandwidth (`measured_bandwidth_bps` via active stream worker counters or network interface deltas) distinguished from estimated stream bitrates (`estimated_bitrate_bps`), true RFC 3550 Section 6.4.1 smoothed interarrival jitter calculation via RTP packet timestamps vs ping mean latency variation, packet loss (%), and uptime percentage within bounded queues (`deque(maxlen=120)`). Automatic congestion detection based on latency (>150ms) and packet drop (>5.0%) thresholds.
  - *Security Posture & Confidence-Scored CVE Auditing (`security_audit.py`)*: Non-intrusive inspection for unencrypted RTSP control channel (`SEC-001A`), unencrypted RTP media transport (`SEC-001B`), plaintext HTTP management (SEC-002), exposed Telnet (SEC-003) and FTP (SEC-004), unauthenticated ONVIF access (SEC-005), and factory default credentials (SEC-006). Verified CVE database with authoritative NVD/CVE URLs and publication dates (Hikvision CVE-2021-36260, Dahua CVE-2021-33044, Dahua CVE-2022-30563, D-Link CVE-2020-25078 password disclosure, CP PLUS KVMS Pro CVE-2023-1518; Pimcore removed). Strict confidence scoring (`CONFIRMED_VULNERABLE`, `POTENTIALLY_VULNERABLE` with `FIRMWARE VERSION UNKNOWN — EXPOSURE UNCONFIRMED`, `UNAFFECTED`) and composite posture scoring (0-100%, Grade A-F). Vendor profile alone never triggers vulnerability matching on unknown models.
  - *Automated Root-Cause Diagnostic Engine (`fault_analyzer.py`)*: Automated fault isolation matrix distinguishing `CAMERA_HARDWARE_FAILURE`, `NVR_FAILURE`, `NETWORK_DISCONNECTION`, `AUTHENTICATION_FAILURE`, `DNS_FAILURE`, `RTSP_STREAM_FAILURE`, and `BANDWIDTH_CONGESTION` with operator-gated remediation recommendations.
- **Network Intelligence Command Center Workspace (`modules/network_intelligence`)**:
  - PySide6 `NetworkIntelligenceWidget` mounted at stacked index 8 ('Network Tools'). Features summary statistics cards, searchable device inventory table, interactive tier-based topology canvas (`InteractiveTopologyCanvas`), real-time telemetry table (8 columns), CCTV diagnostics & fault panel, security posture & CVE tab (9 columns with confidence badges), and CSV/JSON report exports. Asynchronous execution via dedicated `QThread` workers ensuring zero UI thread blocking.

### 3.18 Unified Alarm Management Engine Subsystem (Phase 12 & 12.1)
- **Central Ingestion & Normalization (`engines/alarm_engine/adapters.py`, `normalizer.py`)**:
  - *Heterogeneous Event Adapters*: `AlarmEventBusAdapter` subscribes to 15 platform EventBus topics across Analytics, Behaviour, AI Detection, ANPR, Face, Streams, Camera, Recording, Storage, Network, and Forensics. Asynchronously decouples subsystem publishers via a thread-safe bounded queue (`queue.Queue(maxsize=10000)`).
  - *Canonical Contract (`NormalizedAlarmEvent`)*: Standardizes raw payloads into a common contract with event ID, source subsystem, category (`SECURITY`, `SAFETY`, `OPERATIONAL`, `HARDWARE`, `FORENSIC`), severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL`), priority (`P1_URGENT` to `P4_LOW`), camera/site/zone IDs, UTC timestamp, confidence score, deduplication key, and parsed evidence references (snapshots, segment IDs, bounding boxes, plate text, evidence packages).
  - *Sensitive Biometric Sanitization*: Automatically strips raw 512-dimensional float feature vectors and raw embedding arrays from metadata. Standardizes Face and ANPR candidate matches with status `UNCONFIRMED_CANDIDATE_MATCH`.
- **Deduplication, Correlation & SLA Escalation Core (`engines/alarm_engine`)**:
  - *Persistent Hybrid Deduplicator (`deduplicator.py`)*: High-performance in-memory cache backed by SQLite recovery on startup (`recover_from_database`) and database fallback query (`idx_alarm_dedup_status`). Atomically increments `occurrence_count` via SQL expressions without split alarms across concurrent workers.
  - *Root-Cause & Recovery Correlator (`correlator.py`)*: Real-time causal analyzer linking downstream camera stream offline symptoms to upstream network switch or gateway faults. Automatically clears offline alarms upon receipt of `stream.recovered`.
  - *Policy & Classification Engine (`policy_engine.py`)*: Rule-based policy matrix providing default category, severity, priority, and SLA deadlines, with per-camera policy overrides and automated handling for hardware, camera auth, recording, and storage failure events.
  - *Dynamic SLA Escalator (`escalator.py`)*: Recovers pending escalation deadlines on startup (`recover_pending_escalations`). Background watchdog runs every 10 seconds evaluating deadlines, capping escalations at Tier 3 with duplicate suppression, and appending audit entries to `alarm_history`.
  - *Non-Blocking Notification Dispatcher (`notification.py`)*: Dispatches in-app ticker, desktop popup, and audio chime alerts with cooldown suppression; isolates delivery channels to ensure network timeouts never block ingestion.
- **Cryptographic Hash-Chained Audit Trail & Service RBAC (`alarm_service.py`)**:
  - *Rolling SHA-256 Hash Chain*: Upgraded `alarm_history` ledger with sequential cryptographic hash chaining (`entry_index`, `prev_hash`, `entry_hash`). Provides `verify_history_integrity(alarm_id)` detecting history tampering or omissions with 100% accuracy.
  - *Evidence Access Auditing*: Routes biometric snapshot and plate viewing through `audit_evidence_access()` with RBAC `ACCESS_EVIDENCE` checks and append-only hash-chained logging.
  - *6-State Lifecycle Machine*: Enforces deterministic lifecycle transitions (`NEW` $\to$ `ACKNOWLEDGED` $\to$ `IN_PROGRESS` $\to$ `RESOLVED` $\to$ `CLOSED` $\to$ `REOPENED`).
  - *Non-Bypassable Service RBAC*: Strict authorization checks at the service layer across 5 roles: `ADMIN`, `SUPERVISOR`, `INVESTIGATOR`, `OPERATOR`, and `VIEWER`.
  - *Relational Persistence (6 Tables)*: Managed via SQLAlchemy models in `database/models/alarms.py` with composite indexes (`idx_alarm_dedup_status`, `idx_alarm_deadline_status`, `idx_alarm_status_sev_time`).
- **Command Center Workspace (`modules/alarm_management/alarm_workspace_widget.py`)**:
  - PySide6 desktop command center mounted at View 9 (`AlarmManagementWidget`).
  - Features 5 operational tabs: *Incident Monitor* (multi-filter alarm feeds, color-coded severity badges, search), *Detail & Evidence* (raw JSON payload inspector, evidence references, chronological audit history), *Policy Administration* (SLA timeouts, deduplication windows), *SLA & Shift Metrics* (MTTA, MTTR, top-camera alarm counts), and *Live Event Simulator* (operator testing).
  - *Synchronized Playback Seek*: Emits `request_playback_seek(camera_id, timestamp_iso)` to automatically switch `MainWindow` to View 2 (Playback) and jump directly to the incident timestamp.
  - *Headless Safety*: Automatically suppresses modal blocking dialogs in offscreen testing mode (`QT_QPA_PLATFORM=offscreen`).
