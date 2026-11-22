# CCTV AI Intelligence Platform - User Manual

## 1. System Requirements & Setup

### 1.1 Minimum System Specifications
- **Operating System**: Windows 11 64-bit
- **Processor**: Intel Core i5 (11th Gen or newer recommended)
- **Graphics**: Intel Integrated UHD 730 / Iris Xe or discrete Intel Arc GPU
- **RAM**: 16 GB minimum
- **Storage**: Minimum 20 GB free disk space for OS/metadata; dedicated storage for surveillance video
- **Environment**: Python 3.13 or 3.14 (64-bit)

### 1.2 Running the Application
From the project root directory in PowerShell:
```powershell
python -m app.main
```
The Command Center will open maximized in dark surveillance mode.

---

## 2. Interface Navigation

### 2.1 Top Header
- **Branding**: CCTV AI Intelligence Platform indicator.
- **Site Selector**: Switch between monitored geographical facilities (Default HQ, Branch 1, Branch 2).
- **Intel UHD GPU Active Badge**: Confirms Intel OpenVINO hardware acceleration is engaged.
- **System Health Badge**: Real-time operational status.
- **Active Alarms Badge**: Displays count of unacknowledged high-severity events.
- **UTC Clock**: Real-time synchronized timestamp for legal audit consistency.

### 2.2 Navigation Sidebar
Clicking any icon/button in the left sidebar instantly switches the active workspace:
1. **Dashboard**: Live system telemetry, hardware metrics, 64-channel overview, and AI event logs.
2. **Live View**: Multi-camera grid (1, 4, 9, 16, 25, 36, 64 channels).
3. **Playback**: Synchronized recorded video timeline.
4. **AI Intelligence**: Deep-learning analytics and zone configuration.
5. **Investigation**: Metadata search engine for persons, vehicles, and events.
6. **Video Forensics**: File hash validation, tampering and discontinuity analysis.
7. **Video Enhancement**: Low-light brightening, sharpening, and super-resolution.
8. **Devices**: IP camera, NVR, and DVR configuration.
9. **Network Tools**: Subnet scanner and connection diagnostics.
10. **Alarms**: Incident response and alert inbox.
11. **Storage**: Hard disk quotas, retention rules, and backups.
12. **Reports**: PDF and Excel security report generator.
13. **AI Models**: Model registry and confidence threshold tuning.
14. **Administration**: User accounts, RBAC permissions, and audit logs.
15. **Settings**: Application preferences and network timeouts.

### 2.3 Status Bar
Displays active database backend (`SQLite WAL` or `PostgreSQL`), active worker thread count, storage I/O state, and cumulative application uptime.

---

## 3. Live Surveillance View Operation

### 3.1 Layout Switching
In the **Live View** workspace, use the layout toolbar buttons to dynamically switch display grids:
- `[1x1 (Single)]`: Displays 1 camera full size.
- `[2x2 (4-Cam)]`: 4-camera split screen (default).
- `[3x3 (9-Cam)]`: 9-camera perimeter overview.
- `[4x4 (16-Cam)]`: 16-camera command matrix.

### 3.2 Maximizing a Camera Tile
- **Double-click** on any camera tile to immediately maximize it to full screen (1-up).
- Double-clicking the tile again instantly restores your previous multi-camera grid layout.

### 3.3 Snapshot Extraction
- Click the **SNAP** button located at the bottom-right of any camera tile to extract the current full-resolution frame.
- Snapshots are saved automatically to `storage/snapshots/` with exact UTC microsecond timestamps and indexed in the metadata database.

### 3.4 Starting Simulated Test Streams
- Click the **Start Simulated Test Streams (1-4)** button in the Live View toolbar to immediately launch 4 realistic synthetic surveillance video feeds. Useful for system verification and training when offline or when physical cameras are not connected.

---

## 4. Camera Discovery & Device Registration

1. Click **Discover Cameras** in the top header bar to open the discovery dialog.
2. **ONVIF WS-Discovery**: Click `ONVIF WS-Discovery (Multicast)` to broadcast a network probe across the local LAN. Compliant ONVIF Profile S/T/G cameras respond within seconds with their IP, ONVIF port, hardware model, and manufacturer.
3. **Subnet Scan**: Enter your local IP range (e.g. `192.168.1.0/24`) and click `Scan IP Range` to concurrently probe surveillance ports (80, 554, 8000, 8080, 37777).
4. **Registration**:
   - Highlight any discovered camera in the table and click **Add Selected Camera to System**.
   - Alternatively, use the **Manual Camera Addition** tab to register any custom camera, NVR, or RTSP stream by specifying the manufacturer (Hikvision, Dahua, CP PLUS, Generic), IP address, and credentials.
   - All passwords are encrypted locally using AES-256 before being committed to the database. Passwords are never stored in plaintext.
