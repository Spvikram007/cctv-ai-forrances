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

---

## 5. Playback & Video Investigation Workspace

### 5.1 Date & Channel Selection
1. Click **Playback** in the left navigation sidebar.
2. In the top toolbar, select the desired investigation date using the **Date** calendar picker.
3. Select your desired multi-camera playback layout: `1x1 (Single)`, `2x2 (4 Cameras)`, `3x3 (9 Cameras)`, or `4x4 (16 Cameras)`.
4. Click **Refresh Footage** to load all recording segments from the catalog into the timeline tracks.

### 5.2 Synchronized Multi-Camera Playback Controls
- **Play / Pause (`▶ Play` / `⏸ Pause`)**: Starts or pauses synchronous playback across all loaded cameras driven by the master UTC clock.
- **Stop (`⏹ Stop`)**: Halts playback and closes active video file decoders.
- **Frame Stepping (`⏮ -1f` / `⏭ +1f`)**: Steps playback backward or forward by exactly 1 frame (1/25th of a second), essential for forensic scene investigation.
- **Speed Selector**: Adjust playback speed smoothly between `0.25x`, `0.5x`, `1.0x`, `2.0x`, `4.0x`, `8.0x`, and `16.0x`.
- **Gap Indication**: When a camera has no footage for a specific timestamp, the tile displays an informational standby overlay indicating `NO RECORDING AVAILABLE` with the current UTC timestamp, without interrupting playback of other cameras.

### 5.3 Interactive Timeline Scrubbing & Zooming
- **Scrub Seeking**: Click or drag anywhere along the timeline ruler or camera tracks to instantly seek all cameras to that timestamp.
- **Color-Coded Recording Density**:
  - **Green**: Continuous scheduled recording.
  - **Amber / Orange**: Motion-triggered recording.
  - **Cyan / Blue**: AI event-triggered recording (Person, Vehicle, Intrusion).
  - **Purple**: Operator manual recording.
  - **Dark / Blank**: Recording gap.
- **Zooming**: Scroll your **mouse wheel** over the timeline to zoom smoothly between a broad 24-hour perspective down to a detailed 5-minute window centered around your cursor.

### 5.4 Exporting Video Clips (MP4 + SHA-256)
1. Click the **Export Clip (MP4)** button in the top toolbar to open the forensic export dialog.
2. Specify the camera channel, Start UTC timestamp, and End UTC timestamp.
3. Choose the destination `.mp4` file path.
4. Check **Flag as Protected Evidence**: This guarantees that the original source footage in the storage vault is locked and will **never be deleted by automatic retention routines**.
5. Enter case notes or investigation justification.
6. Click **Start Export**: The exporter generates a standard MP4 file, computes its cryptographic SHA-256 checksum, and writes an adjacent forensic `{filename}_manifest.json` file for legal chain-of-custody.

---

## 6. AI Intelligence & Analytics Workspace

### 6.1 Accessing the AI Workspace
1. Click **AI Intelligence** in the left navigation sidebar (item 4).
2. The AI Intelligence Command Dashboard displays real-time telemetry across all active inference pipelines.

### 6.2 Telemetry Gauges & Hardware Status
- **Inference Device**: Displays active compute backend (`Intel UHD 730 (GPU)` or `CPU (AVX2)`).
- **Active AI Channels**: Count of camera streams currently being processed by AI workers.
- **Total Detections**: Aggregate counter of detected objects across all cameras.
- **Average Latency**: Average inference duration in milliseconds. Color-coded: Green ($< 50\text{ms}$), Amber ($50\text{--}100\text{ms}$), Red ($> 100\text{ms}$).
- **Aggregate FPS**: Real-time processed frames per second across all camera streams.
- **AI Events Generated**: Total count of security triggers emitted to the event bus.

### 6.3 Per-Channel Inference Status Table
- Lists each monitored channel with:
  - **Channel**: Camera identifier.
  - **Device**: Active inference execution device (`GPU` or `CPU`).
  - **FPS**: Per-channel inference frame rate (target: 5.0 FPS).
  - **Latency**: Per-frame processing time.
  - **Detections**: Total objects identified on this channel.

### 6.4 Detection Classes & Severity
- **Person**: Classified as `WARNING` severity; triggers automatic event recording and snapshot capture.
- **Vehicles (Car, Bus, Truck, Motorcycle, Bicycle)**: Classified as `INFO` severity; tracked with persistent ByteTrack IDs.

### 6.5 Multi-Object Tracking & Camera Isolation
- Each camera channel runs an independent ByteTrack tracker with Kalman filter prediction.
- Tracking IDs are strictly isolated per camera to prevent cross-camera ID pollution.
- Lost tracks are maintained through brief occlusions (up to 30 frames) and automatically reacquired.

### 6.6 Snapshot Storage & Event Deduplication
- High-severity detection snapshots are automatically stored under `storage/snapshots/{channel_id}/{YYYYMMDD}/`.
- Event deduplication prevents repetitive alarm flooding by suppressing duplicate triggers for the same object within 5 seconds.
