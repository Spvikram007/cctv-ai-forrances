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

### 3.4 Video Streaming Pipeline & Bounded Queues
- **Decoupled Worker Architecture**: Each active camera channel runs an isolated `RTSPStreamWorker` thread. Decoding failures, network timeouts, or camera disconnects are handled through automated exponential backoff reconnection loops without impacting other streams or the Qt UI thread.
- **Bounded Frame Buffer**: A thread-safe bounded double-ended queue (`deque(maxlen=30)`) is maintained per channel. Under network latency or processing lag, the queue automatically discards the oldest frame in $O(1)$ time, maintaining low latency and preventing memory bloat.
- **In-Memory Frame Transport**: Video frames are transported as native numpy ndarrays within the process space directly to `VideoTileWidget` (via `QPainter.drawImage`) and AI inference queues, strictly avoiding raw video serialization through JSON or IPC bottlenecks.

### 3.5 Camera Discovery Subsystem
- **ONVIF WS-Discovery**: Sends standardized SOAP probe broadcasts to multicast group `239.255.255.250:3702` (Types: `dn:NetworkVideoTransmitter`). Responses are parsed to extract device service XAddrs, hardware models, and scopes.
- **Subnet IP Scanner**: Concurrently probes common surveillance ports (80, 554, 8000, 8080, 8899, 37777) across user-configurable CIDR blocks.
- **MAC Resolution & Brand Fingerprinting**: Local ARP tables map discovered IPs to MAC addresses. MAC OUI prefixes and scope strings automatically identify Hikvision, Dahua, CP PLUS, Uniview, and Axis devices.

### 3.6 ONVIF & Manufacturer Adapters
- **Pure-Python ONVIF Client**: Implements WS-Security UsernameToken authentication with SHA-1 `PasswordDigest`, Nonce, and Created timestamps. Exposes `GetDeviceInformation`, `GetCapabilities`, `GetProfiles`, `GetStreamUri`, and Profile S/T PTZ continuous move/stop.
- **NVR/DVR Adapters**: Dedicated HTTP/REST adapters for Hikvision ISAPI (`/ISAPI/ContentMgmt/InputProxy/channels`), Dahua CGI (`/cgi-bin/configManager.cgi`), and CP PLUS map recorder channels to individual camera streams.

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
