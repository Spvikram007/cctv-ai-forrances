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

### 2.6 Phase 4 Recording & Playback Extensions
- **`storage_events`**: Volume threshold breach events and retention audit log (`volume_id`, `event_type`, `severity`, `message`, `bytes_freed`).
- **`playback_sessions`**: User historical playback queries and master clock tracking (`user_id`, `channels_json`, `started_at`, `ended_at`, `master_clock_timestamp`).
- **`export_jobs`**: Video clip extraction tasks (`channel_id`, `start_time`, `end_time`, `destination_path`, `file_size_bytes`, `sha256_hash`, `status`, `progress_pct`, `is_evidence`, `created_by`, `error_message`).
- **`recordings` Table Extended**: Added `codec`, `resolution_width`, `resolution_height`, `fps`, `bitrate_kbps`, `status` (`ACTIVE`, `COMPLETED`, `CORRUPTED`, `RECOVERED`), `is_locked` (forensic evidence lock preventing automated retention deletion). Decoupled `channel_id` to `String(64)` for logical channel independence.

### 2.7 Phase 5 AI Inference & Tracking Extensions
- **`ai_jobs` Table Extended**: Added `execution_device` (VARCHAR(20), default 'CPU') and `actual_fps` (FLOAT, default 0.0). Decoupled `channel_id` to `VARCHAR(64)` without device FK constraint to enable logical channel bindings.
- **`detections` Table Updated**: Decoupled `channel_id` to `VARCHAR(64)` without device FK constraint for logical channel persistence. Indexed on `channel_id`, `timestamp`, `class_name`, `track_id`.
- **`object_tracks` Table Updated**: Decoupled `channel_id` to `VARCHAR(64)` without device FK constraint. Indexed on `channel_id`, `track_id`, `start_time`.
- **`ai_events` Table Updated**: Decoupled `channel_id` to `VARCHAR(64)` without device FK constraint. Indexed on `channel_id`, `event_type`, `severity`, `timestamp`.

### 2.8 Phase 6 Video Analytics & Intelligent Surveillance Rules Extensions
- **`analytics_zones` Table Added**: Polygon definitions (`channel_id`, `name`, `zone_type`, `polygon_json`, `color_hex`, `is_active`). Indexed on `channel_id`, `zone_type`, `is_deleted`.
- **`tripwire_lines` Table Added**: Virtual lines (`channel_id`, `name`, `line_coords_json`, `direction`, `color_hex`, `is_active`). Indexed on `channel_id`, `is_deleted`.
- **`analytics_rules` Table Added**: Surveillance rules (`channel_id`, `name`, `rule_type`, `zone_id`, `tripwire_id`, `target_classes_json`, `confidence_threshold`, `min_dwell_time_sec`, `severity`, `schedule_json`, `trigger_recording`, `alarm_sound`, `is_active`). Indexed on `channel_id`, `rule_type`, `zone_id`, `tripwire_id`.
- **`analytics_events` Table Added**: Fired analytics events (`channel_id`, `rule_id`, `rule_name`, `rule_type`, `severity`, `track_id`, `class_name`, `confidence`, `dwell_time_sec`, `crossing_direction`, `details_json`, `snapshot_path`, `timestamp`, `is_acknowledged`). Indexed on `channel_id`, `rule_type`, `severity`, `timestamp`, `track_id`.
- **`object_counts` Table Added**: Directional counting logs (`channel_id`, `rule_id`, `line_or_zone_id`, `class_name`, `direction`, `count_delta`, `track_id`, `timestamp`). Indexed on `channel_id`, `timestamp`, `track_id`, `class_name`.
- **`occupancy_records` Table Added**: Real-time occupancy snapshots (`channel_id`, `zone_id`, `zone_name`, `current_occupancy`, `person_count`, `vehicle_count`, `max_capacity`, `is_over_capacity`, `timestamp`). Indexed on `channel_id`, `zone_id`, `timestamp`.
- **`heatmap_data` Table Added**: Serialized 2D movement density grids (`channel_id`, `time_window_start`, `time_window_end`, `grid_width`, `grid_height`, `density_matrix_json`, `total_points`). Indexed on `channel_id`, `time_window_start`, `time_window_end`.

### 2.9 Phase 7 Authorized Face Intelligence & ANPR Schema Extensions
- **`face_identities` Table Added**: Authorized enrolled identities (`name`, `identity_code`, `category`, `is_active`, `department`, `notes`). Indexed on `name`, `identity_code`, `category`, `is_active`.
- **`face_templates` Table Added**: Cryptographically sealed biometric feature templates (`identity_id`, `encrypted_template` [AES-256-GCM hex blob], `algorithm`, `vector_dim`, `quality_score`, `is_revoked`, `revoked_at`, `revocation_reason`). Indexed on `identity_id`, `is_revoked`.
- **`face_enrollments` Table Added**: Legal enrollment consent and compliance records (`identity_id`, `enrolled_by_user_id`, `status`, `authorization_ref`, `valid_until`). Indexed on `identity_id`, `enrolled_by_user_id`, `status`.
- **`face_match_events` Table Added**: Candidate match correlation events (`channel_id`, `identity_id`, `candidate_name`, `category`, `similarity_score`, `threshold_applied`, `snapshot_path`, `face_bbox_json`, `is_verified` [human confirmation required], `verified_by_user_id`, `verified_at`, `timestamp`). Indexed on `channel_id`, `identity_id`, `candidate_name`, `category`, `is_verified`, `timestamp`.
- **`anpr_detections` Table Added**: License plate detection records (`channel_id`, `track_id`, `vehicle_class`, `plate_text`, `confidence`, `character_confidences_json`, `plate_format`, `requires_manual_review`, `plate_crop_path`, `vehicle_snapshot_path`, `timestamp`). Indexed on `channel_id`, `track_id`, `vehicle_class`, `plate_text`, `requires_manual_review`, `timestamp`.
- **`anpr_plate_records` Table Added**: Unique vehicle plate sightings database (`plate_text_normalized`, `vehicle_class`, `first_seen`, `last_seen`, `total_sightings`, `is_watchlist`, `watchlist_category`, `owner_or_notes`). Indexed on `plate_text_normalized`, `first_seen`, `last_seen`, `is_watchlist`.
- **`vehicle_events` Table Added**: Vehicle event log (`channel_id`, `plate_text`, `event_type`, `severity`, `confidence`, `track_id`, `details_json`, `timestamp`). Indexed on `channel_id`, `plate_text`, `event_type`, `timestamp`.
- **`biometric_audit_logs` Table Added**: Immutable audit trail for all biometric operations (`user_id`, `action` [ENROLL, REVOKE, VERIFY, QUERY], `identity_id`, `template_id`, `details_json`, `ip_address`, `timestamp`). Indexed on `user_id`, `action`, `identity_id`, `timestamp`.

## 4. Migration History (Alembic)
- **`26108d74df4c`** (2026-11-22): `phase1_phase2_devices_and_streams`
  - Created tables: `device_credentials`, `device_discovery_records`, `nvr_channel_mappings`, `stream_health_logs`.
  - Added indexes on `device_id`, `channel_id`, `ip_address`, `mac_address`, and `is_deleted`.
- **`328e2912c14c`** (2026-11-22): `phase4_recordings_and_playback`
  - Created tables: `storage_events`, `playback_sessions`, `export_jobs`.
  - Added columns to `recordings`: `codec`, `resolution_width`, `resolution_height`, `fps`, `bitrate_kbps`, `status`, `is_locked`.
  - Added indexes on `is_locked`, `status`, `export_jobs.start_time`, `export_jobs.end_time`.
- **`49b81e4a112f`** (2026-11-22): `phase5_ai_inference_and_tracking`
  - Added columns to `ai_jobs`: `execution_device`, `actual_fps`.
  - Decoupled `channel_id` from strict `device_channels.id` foreign key on `ai_jobs`, `detections`, `object_tracks`, `ai_events` to support logical channel tracking.
  - Added indexes on `channel_id`, `timestamp`, `class_name`, `track_id`, `event_type`, `severity`.
- **`57a91c3e80ab`** (2026-11-24): `phase6_video_analytics_and_rules`
  - Created tables: `analytics_zones`, `tripwire_lines`, `analytics_rules`, `analytics_events`, `object_counts`, `occupancy_records`, `heatmap_data`.
  - Added indexes on `channel_id`, `zone_type`, `rule_type`, `track_id`, `timestamp`, `is_deleted`.
- **`62f4c08e921d`** (2026-11-24): `phase7_face_and_anpr`
  - Created tables: `face_identities`, `face_templates`, `face_enrollments`, `face_match_events`, `anpr_detections`, `anpr_plate_records`, `vehicle_events`, `biometric_audit_logs`.
  - Added indexes on `identity_code`, `is_active`, `is_revoked`, `plate_text`, `plate_text_normalized`, `is_watchlist`, `action`, `user_id`, `timestamp`.
