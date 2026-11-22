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
