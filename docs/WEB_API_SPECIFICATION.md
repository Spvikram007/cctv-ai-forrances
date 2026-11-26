# CCTV AI Intelligence Platform — Web REST API & WebSocket Specification

**Document Version:** 1.0.0  
**API Prefix:** `/api/v1`  
**WebSocket Prefix:** `/ws`  
**Standard Authentication:** HttpOnly Session Cookie (`cctv_session`) or `Authorization: Bearer <token>`  
**Classification:** Enterprise API Contract Specification  

---

## 1. Global API Standards & Conventions

### 1.1 Standard JSON Response Envelope
All non-streaming REST API responses follow a uniform Pydantic response envelope:

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "correlation_id": "req-20261125-9a8b7c",
  "timestamp": "2026-11-25T18:00:00.000000Z"
}
```

In the event of an error:
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ACCESS_DENIED",
    "message": "You do not possess the required permission 'camera:manage'.",
    "details": null
  },
  "correlation_id": "req-20261125-9a8b7c",
  "timestamp": "2026-11-25T18:00:00.000000Z"
}
```

### 1.2 HTTP Status Code Standards
- `200 OK`: Request succeeded.
- `201 Created`: Resource successfully created.
- `400 Bad Request`: Validation failure or malformed payload.
- `401 Unauthorized`: Missing, expired, or invalid session token.
- `403 Forbidden`: Authenticated user lacks required RBAC permission.
- `404 Not Found`: Requested device, stream, user, or resource does not exist.
- `409 Conflict`: Unique constraint violation (e.g. duplicate username or IP).
- `429 Too Many Requests`: Rate limit exceeded (brute-force defense).
- `500 Internal Server Error`: Unhandled server exception with redacted error details.

### 1.3 Pagination & Sorting Standards
All collection endpoints support standard query parameters:
- `page`: 1-based page index (default: `1`).
- `page_size`: Number of items per page (default: `50`, maximum: `500`).
- `sort_by`: Field name to sort on.
- `sort_order`: `asc` or `desc` (default: `desc`).

---

## 2. API Domain Routes & Endpoints

### 2.1 Authentication & Session Management (`/api/v1/auth`)
| Method | Endpoint | Description | Permission | Request Body |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Authenticate with username and password. Issues secure session cookie. | Public | `LoginRequest` |
| `POST` | `/api/v1/auth/logout` | Revoke active session token. | Authenticated | None |
| `GET` | `/api/v1/auth/me` | Retrieve profile, role, and permissions of current user. | Authenticated | None |
| `POST` | `/api/v1/auth/refresh` | Extends session idle timeout and updates `last_seen_at`. | Authenticated | None |
| `GET` | `/api/v1/auth/sessions` | List all active sessions for current user or all users. | `user:manage` | None |
| `DELETE`| `/api/v1/auth/sessions/{id}`| Revoke a specific active session. | `user:manage` | None |

### 2.2 User Administration & RBAC (`/api/v1/users`, `/api/v1/roles`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/users/` | List all user accounts with filtering. | `user:manage` |
| `POST` | `/api/v1/users/` | Create a new user with bcrypt password and role. | `user:manage` |
| `GET` | `/api/v1/users/{id}` | Retrieve user profile details. | `user:manage` |
| `PUT` | `/api/v1/users/{id}` | Update user details, role assignment, active status. | `user:manage` |
| `POST` | `/api/v1/users/{id}/unlock` | Manually clear failed attempts and unlock account. | `user:manage` |
| `POST` | `/api/v1/users/{id}/reset-password` | Administrative reset of user password. | `user:manage` |
| `GET` | `/api/v1/roles/` | List all standard and custom RBAC roles with permissions. | `role:manage` |
| `GET` | `/api/v1/permissions/` | List all 22 operational platform permissions. | `role:manage` |

### 2.3 Dashboard & System Telemetry (`/api/v1/dashboard`, `/api/v1/system`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/dashboard/summary` | High-level metrics: total cameras, online count, active alarms, storage used. | `dashboard:view` |
| `GET` | `/api/v1/system/telemetry` | Real-time CPU load, memory usage, GPU utilization, and platform uptime. | `dashboard:view` |
| `GET` | `/api/v1/system/health` | Subsystem health status (DB, StreamManager, OpenVINO, Storage). | `system:config` |

### 2.4 Device & Camera Management (`/api/v1/devices`, `/api/v1/cameras`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/devices/` | List all registered cameras, NVRs, and DVRs. | `live:view` |
| `POST` | `/api/v1/devices/` | Register a new camera or NVR manually. | `camera:manage` |
| `GET` | `/api/v1/devices/{id}` | Get full device metadata and stream profiles. | `camera:manage` |
| `PUT` | `/api/v1/devices/{id}` | Update device settings, IP, credentials, stream URLs. | `camera:manage` |
| `DELETE`| `/api/v1/devices/{id}` | Decommission device (soft delete). | `camera:manage` |
| `POST` | `/api/v1/devices/discover` | Trigger ONVIF WS-Discovery probe across local subnet. | `network:scan` |
| `POST` | `/api/v1/devices/test` | Test camera reachability, RTSP port, and ONVIF capabilities. | `camera:manage` |

### 2.5 Live Video Delivery & WebRTC (`/api/v1/live`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/live/webrtc/offer` | Negotiate WebRTC SDP offer/answer for real-time video track. | `live:view` |
| `POST` | `/api/v1/live/webrtc/candidate`| Exchange ICE candidates for WebRTC peer connection. | `live:view` |
| `GET` | `/api/v1/live/{channel_id}/snapshot.jpg` | Retrieve single instant high-res JPEG snapshot. | `live:view` |
| `GET` | `/api/v1/live/{channel_id}/stream.mjpg` | Low-overhead multipart MJPEG stream for mobile viewports. | `live:view` |
| `POST` | `/api/v1/live/{channel_id}/profile` | Switch stream profile between `MAIN` (1080p) and `SUB` (360p). | `live:view` |

### 2.6 Universal PTZ Control (`/api/v1/ptz`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/ptz/{channel_id}/move` | Execute continuous or relative pan, tilt, zoom move command. | `ptz:control` |
| `POST` | `/api/v1/ptz/{channel_id}/stop` | Stop all active PTZ motion. | `ptz:control` |
| `GET` | `/api/v1/ptz/{channel_id}/presets` | List all configured ONVIF/CGI camera presets. | `ptz:control` |
| `POST` | `/api/v1/ptz/{channel_id}/presets/{id}/goto` | Command camera to move to designated preset position. | `ptz:control` |

### 2.7 Playback & Historical Recordings (`/api/v1/playback`, `/api/v1/recordings`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/playback/{channel_id}/timeline` | Index recorded segments across date-time window. | `playback:view` |
| `GET` | `/api/v1/playback/{channel_id}/segment/{id}` | Stream historical MP4 video segment or HLS playlist. | `playback:view` |
| `POST` | `/api/v1/playback/export` | Request MP4 export clip across specified start/end range. | `playback:export` |
| `GET` | `/api/v1/recordings/schedules` | List active continuous and event recording schedules. | `playback:view` |

### 2.8 AI Video Analytics & Intelligence (`/api/v1/analytics`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/analytics/rules` | List all active tripwires, intrusion zones, and density rules. | `ai:view` |
| `POST` | `/api/v1/analytics/rules` | Create a new analytics rule or polygonal zone. | `ai:configure` |
| `PUT` | `/api/v1/analytics/rules/{id}` | Modify zone vertices, sensitivity, or alert conditions. | `ai:configure` |
| `GET` | `/api/v1/analytics/biometrics/faces` | Search recognized face candidate matches with filters. | `biometrics:view` |
| `GET` | `/api/v1/analytics/biometrics/anpr` | Search recognized vehicle license plates and plate crops. | `biometrics:view` |

### 2.9 Alarm Center & Incident Workflow (`/api/v1/alarms`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/alarms/` | Query active and historical alarms with pagination and filters. | `alarm:view` |
| `GET` | `/api/v1/alarms/{id}` | Retrieve full alarm details, source event, and history trail. | `alarm:view` |
| `POST` | `/api/v1/alarms/{id}/acknowledge`| Transition alarm to `ACKNOWLEDGED` with operator identity. | `alarm:manage` |
| `POST` | `/api/v1/alarms/{id}/resolve` | Transition alarm to `RESOLVED` with resolution notes. | `alarm:manage` |
| `POST` | `/api/v1/alarms/{id}/escalate`| Escalate alarm severity or assign to supervisor. | `alarm:manage` |

### 2.10 Digital Forensics & Cryptographic Evidence (`/api/v1/forensics`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/forensics/verify/{segment_id}` | Verify SHA-256 integrity and frame discontinuity of clip. | `forensic:view` |
| `GET` | `/api/v1/forensics/evidence/` | List sealed evidentiary packages in Evidence Locker. | `forensic:view` |
| `POST` | `/api/v1/forensics/evidence/package` | Package video, metadata, and ECDSA signature into court package. | `evidence:export` |
| `GET` | `/api/v1/forensics/evidence/{id}/download` | Download sealed forensic `.cctvev` package. | `evidence:export` |

### 2.11 Storage Pools & Failover Management (`/api/v1/storage`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/storage/pools` | List Hot, Warm, Cold logical pools with capacity meters. | `storage:manage` |
| `GET` | `/api/v1/storage/volumes` | Inspect physical disks, RAID arrays, and SMB/NFS NAS mounts. | `storage:manage` |
| `GET` | `/api/v1/storage/failover/events` | List storage failover and automatic redirection events. | `storage:manage` |

### 2.12 Reports & Compliance Audit (`/api/v1/reports`, `/api/v1/audit`)
| Method | Endpoint | Description | Permission |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/reports/audit` | Generate PDF or CSV audit report. | `audit:export` |
| `POST` | `/api/v1/reports/incident/{alarm_id}` | Generate formal Incident & Forensic Dossier PDF. | `alarm:view` |
| `GET` | `/api/v1/audit/logs` | Query rolling append-only audit ledger records. | `audit:view` |
| `GET` | `/api/v1/audit/verify` | Execute cryptographic Merkle hash chain verification. | `audit:view` |

---

## 3. Real-Time WebSocket Contract (`/ws/events`)

### 3.1 Handshake & Authentication
Web clients initiate a WebSocket connection to `wss://SERVER-IP:8443/ws/events?token=<session_token>`.
1. The server validates the session token via `user_service.validate_session()`. If invalid or expired, the socket closes with code `4401 Unauthorized`.
2. Upon connection, the client receives an initial handshake frame:
   ```json
   {
     "event": "connected",
     "session_id": "sess-uuid",
     "user_id": "usr-uuid",
     "server_time": "2026-11-25T18:00:00.000000Z"
   }
   ```

### 3.2 Downlink Event Types
The hub broadcasts messages formatted as:
```json
{
  "topic": "alarm.critical",
  "data": {
    "alarm_id": "alm-001",
    "channel_id": "cam_front_gate",
    "title": "Perimeter Intrusion Detected",
    "severity": "CRITICAL",
    "timestamp": "2026-11-25T18:00:01.000000Z"
  }
}
```
Supported Topics:
- `alarm.new`, `alarm.updated`, `alarm.resolved`
- `stream.started`, `stream.stopped`, `stream.telemetry`
- `analytics.detection` (AI bounding box updates)
- `device.status` (online/offline state)
- `storage.alert` (volume warning, failover active)
