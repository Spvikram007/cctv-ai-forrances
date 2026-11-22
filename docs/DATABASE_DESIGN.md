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

### 2.5 Phase 1 & Phase 2 Schema Extensions
- **`device_credentials`**: Stores device-bound AES-256 encrypted passwords (`encrypted_password`), usernames, and authentication types (`DIGEST`, `BASIC`), foreign-keyed to `devices.id`.
- **`device_discovery_records`**: Caches scan results (`ip_address`, `mac_address`, `manufacturer`, `model`, `firmware_version`, `onvif_port`, `rtsp_port`, `discovery_method`, `detected_capabilities`, `is_added`).
- **`stream_health_logs`**: Historical telemetry per channel (`status`, `fps_measured`, `bitrate_kbps`, `latency_ms`, `dropped_frames`, `error_message`).
- **`nvr_channel_mappings`**: Maps recorder channels to camera inputs for multi-channel NVRs and DVRs (`nvr_device_id`, `channel_number`, `mapped_camera_name`, `main_stream_url`, `sub_stream_url`).

## 4. Migration History (Alembic)
- **`26108d74df4c`** (2026-11-22): `phase1_phase2_devices_and_streams`
  - Created tables: `device_credentials`, `device_discovery_records`, `nvr_channel_mappings`, `stream_health_logs`.
  - Added indexes on `device_id`, `channel_id`, `ip_address`, `mac_address`, and `is_deleted`.
