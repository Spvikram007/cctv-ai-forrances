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
