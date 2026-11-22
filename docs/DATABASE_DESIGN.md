# Database Design & Schema Specification

## 1. Relational Database Overview

The persistence architecture utilizes **SQLAlchemy 2.0** declarative models compatible with both **PostgreSQL** and **SQLite 3 (WAL mode)**.
All tables employ standard 36-character UUID string primary keys, UTC timestamp auditing, and soft-deletion tracking flags.

## 2. Table Specifications

### 2.1 Security & Users Domain
- **`roles`**: Defines user roles (`Administrator`, `Supervisor`, `Operator`, `Investigator`, `Viewer`).
- **`permissions`**: Granular capability tokens (e.g. `live:view`, `ptz:control`, `ai:configure`, `evidence:export`).
- **`role_permissions`**: Many-to-many relationship mapping roles to permissions.
- **`users`**: User identity, hashed passwords (SHA-256 / bcrypt), email, and active status.
- **`user_sessions`**: Active login sessions, session tokens, expiration timestamps, IP address, and revocation flags.
- **`audit_logs`**: Immutable security audit trail recording who performed which action on which resource.

### 2.2 Devices & Network Domain
- **`sites`**: Top-level geographical facility or campus definitions.
- **`locations`**: Specific floors, buildings, or perimeter zones within a site.
- **`devices`**: Physical hardware entries (IP cameras, NVRs, DVRs), manufacturer type (Hikvision, Dahua, CP PLUS, Generic ONVIF), IP, RTSP/ONVIF ports, online status.
- **`device_channels`**: Individual camera channels (1 up to 64 per device/NVR), PTZ capabilities, audio flags.
- **`stream_profiles`**: Stream URLs, resolutions, codecs (H.264/H.265), target FPS, and bitrates for Main and Sub streams.
- **`device_capabilities`**: Detected ONVIF profile compliance (S, G, T) and proprietary API flags (Hikvision ISAPI, Dahua CGI).
- **`device_status`**: Real-time network telemetry (latency ms, packet loss %, actual FPS, actual bitrate, last error).

### 2.3 Storage & Recordings Domain
- **`storage_volumes`**: Registered hard drive partitions or network shares with capacity quotas.
- **`recordings`**: High-level continuous or event recording entries, file paths, start/end timestamps, file sizes, SHA-256 hashes.
- **`recording_segments`**: Segmented media files with start offsets and duration in seconds.
- **`recording_schedules`**: Day-of-week and hourly recording rules (Continuous, Motion, AI-only).

### 2.4 AI & Analytics Domain
- **`ai_models`**: Registered model metadata (OpenVINO IR, ONNX, PyTorch), task types (Object Detection, Face, ANPR).
- **`ai_model_versions`**: Versioned model binaries, SHA-256 checksums, input tensor dimensions, and class labels.
- **`ai_jobs`**: Active inference pipelines binding a camera channel to a model version on a target hardware device.
- **`detections`**: Individual detected objects with bounding boxes (normalized 0.0-1.0), class names, confidence scores, and track IDs.
- **`object_tracks`**: Trajectories of tracked entities across frames with start and end timestamps.
- **`ai_events`**: High-priority security triggers (Intrusion, Line Crossing, Face Match, Plate Match) with snapshot paths and severity.

## 3. SQLite Configuration (Offline Local)
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
```
Ensures maximum read throughput and ACID transactional integrity during continuous background recording.
