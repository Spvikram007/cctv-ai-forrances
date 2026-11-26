# Phase 15 Implementation Plan: Optimization, Quality Assurance & Windows Packaging

**Project:** CCTV AI Intelligence Platform  
**Target Release:** `1.5.0-alpha` (Production Candidate)  
**Baseline Version:** `1.4.0-alpha` (Commit: `4650013c9574bfc4f91362fe63651420a811886c`)  
**Target Hardware Profile:**  
- **Processor:** Intel Core i5-12400 (6 Cores, 12 Threads, up to 4.40 GHz)  
- **Memory:** 16 GB DDR4/DDR5 RAM (System usable: ~15.75 GB)  
- **Graphics/Inference Accelerator:** Intel UHD Graphics 730 (OpenVINO GPU device)  
- **Operating System:** Windows 10 / Windows 11 64-bit  

---

## 1. Executive Objectives

Phase 15 represents the final hardening, optimization, quality assurance, and packaging phase of the native CCTV AI Intelligence Platform desktop application prior to any subsequent Web/LAN platform extensions.

The primary goals are:
1. **Target Hardware Tuning:** Profile and optimize CPU, RAM, and OpenVINO AI inference for the Intel Core i5-12400 and Intel UHD Graphics 730 iGPU.
2. **Video Stream Stability:** Verify multi-camera stability, backoff reconnection, and non-blocking RTSP packet handling under sustained load.
3. **Database Performance & Disaster Recovery:** Implement automated SQLite WAL checkpointing, scheduled VACUUM/PRAGMA optimize, hot database backups, and emergency recovery tooling.
4. **Standalone Windows Packaging (PyInstaller):** Package the full application into a standalone, portable Windows executable distribution bundling Python runtime, PySide6 Qt platform plugins, OpenVINO 2026.4 runtime DLLs, OpenCV, and ONNX models.
5. **Enterprise NSIS Installer:** Author an NSIS (Nullsoft Scriptable Install System) script providing clean installation, Start Menu / Desktop shortcuts, Visual C++ Redistributable prerequisites check, uninstallation, upgrade, and repair workflows.
6. **Production Documentation:** Deliver comprehensive operational, deployment, and troubleshooting documentation for CCTV operators and system administrators.

---

## 2. Milestones & Work Breakdown Structure (WBS)

### Milestone 15.1: Hardware-Specific Performance Optimization (i5-12400 + Intel UHD 730)
- **OpenVINO Inference Optimization:**
  - Leverage `ov.Core()` with explicit device selection: primary `GPU` (Intel UHD Graphics 730) for YOLO object detection and ByteTrack, secondary `CPU` with throughput streams (`PERFORMANCE_HINT=THROUGHPUT`) for face embedding and ANPR OCR.
  - Implement dynamic precision caching (`FP16` on Intel UHD 730, `FP32`/`INT8` on i5-12400 CPU).
- **CPU & Threading Architecture:**
  - Allocate 12 logical processor threads: 4 dedicated to RTSP ingest & decoding, 4 dedicated to AI inference pipelines, 2 dedicated to recording & storage I/O, 2 dedicated to PySide6 UI and event bus.
- **Memory Management & Zero-Copy Pipelines:**
  - Optimize memory footprint below 2.5 GB under 16 concurrent 1080p camera feeds.
  - Profile frame buffers using `psutil` and `tracemalloc` to eliminate leaked OpenCV `Mat` references.

### Milestone 15.2: Multi-Camera Video Pipeline Stability & Reconnection Testing
- **Stream Resilience Testing:**
  - Stress-test the unified `StreamManager` under simulated network drops, intermittent packet corruption, RTSP TCP/UDP timeout, and day/night transitions across 16 to 64 simulated camera channels.
  - Verify exponential backoff reconnection (1s, 2s, 4s, 8s, up to 30s cap) without leaking socket file descriptors or thread handles.
- **Backpressure & Frame Dropping Policy:**
  - Ensure real-time playback never stalls the recording engine if AI inference falls behind during heavy activity.

### Milestone 15.3: Database Performance, Maintenance & Automated Recovery
- **WAL Checkpoint Tuning:**
  - Configure `PRAGMA wal_autocheckpoint = 1000`, `PRAGMA journal_size_limit = 67108864` (64 MB), and `PRAGMA synchronous = NORMAL`.
- **Automated Backup & Maintenance Service:**
  - Implement SQLite online backup API (`sqlite3_backup`) to create hot snapshots in `storage/backups/` without locking live camera recordings or alarm writes.
  - Implement daily automated integrity check (`PRAGMA integrity_check`) and maintenance optimization (`PRAGMA optimize`).
- **Disaster Recovery CLI Tool:**
  - Create `tools/db_recovery.py` to verify, repair, restore, and re-index corrupted SQLite databases from latest verified backup.

### Milestone 15.4: Comprehensive Security, Regression & Soak Testing
- **Sustained Soak Test:**
  - Run a 10-minute continuous sustained simulation of 16 camera streams with AI detection, storage recording, and periodic alarm triage. Monitor RSS memory drift and CPU utilization.
- **Security Audit:**
  - Review DPAPI credentials vault, RBAC permission barriers, bcrypt hashing, and tamper-evident audit ledger under maximum stress.
- **Full Regression Suite:**
  - Execute all unit, integration, and performance tests with zero failures.

### Milestone 15.5: PyInstaller Standalone Windows Executable Packaging
- **PyInstaller Specification (`installer/cctv_ai.spec`):**
  - Bundle `app/main.py` entrypoint.
  - Include PySide6 Qt platform plugins (`qwindows.dll`), styles, and SVG icon libraries.
  - Include OpenVINO runtime libraries, TBB libraries, and OpenVINO GPU plugins (`openvino_intel_gpu_plugin.dll`).
  - Bundle ONNX model weights (`models/`), default configurations (`config/`), and DB migration scripts (`database/migrations/`).
  - Configure `--windowed` (no console popups in production mode, with optional debug console build).
  - Embed Windows application icon (`resources/icons/app_icon.ico`) and version resource metadata (`file_version_info.txt`).

### Milestone 15.6: NSIS Windows Installer Authoring
- **Installer Script (`installer/cctv_ai_setup.nsi`):**
  - Modern UI 2 (MUI2) styling with enterprise branding.
  - Architecture check: enforce 64-bit Windows OS.
  - Visual C++ 2015-2022 Redistributable x64 prerequisite detection and automated silent installation if missing.
  - Installation directory selection (default: `%LOCALAPPDATA%\Programs\CCTV AI` or `%ProgramFiles%\CCTV AI`).
  - Creation of Desktop shortcut and Start Menu program folder.
  - Registration with Windows "Add/Remove Programs" (Uninstall key in registry).
  - Uninstaller that cleanly stops running background services and removes binaries while preserving user video recordings and database evidence in `storage/`.
  - Upgrade and repair workflows that preserve database and credentials across version upgrades.

### Milestone 15.7: Production Deployment & Runbook Documentation
- **Deliverables:**
  - `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`: Step-by-step installation, hardware tuning, storage volume mounting, camera onboarding, and disaster recovery procedures.
  - `docs/HARDWARE_TUNING_I5_12400.md`: OS-level and BIOS-level optimizations for Intel Core i5-12400 and Intel UHD 730 surveillance workstations.
  - `docs/PHASE_15_IMPLEMENTATION_REPORT.md`: Comprehensive completion report with benchmark metrics, test results, and verified installer artifacts.

---

## 3. Controlled Execution Plan & Verification Criteria

| Milestone | Deliverable Files | Success Verification Criteria |
| :--- | :--- | :--- |
| **M 15.1** | `core/hardware/openvino_tuner.py`<br>`core/hardware/profiler.py` | OpenVINO selects GPU for YOLO and CPU for ANPR; CPU < 35% on i5-12400; RAM < 2.5 GB with 16 simulated streams. |
| **M 15.2** | `engines/stream_engine/resilience.py`<br>`tests/integration/test_stream_resilience_phase15.py` | 100% reconnection after network interruption within 30s; 0 leaked file descriptors or orphaned threads. |
| **M 15.3** | `database/backup_service.py`<br>`tools/db_recovery.py`<br>`tests/unit/test_db_recovery.py` | Hot backup creates valid snapshot during active writes; `PRAGMA integrity_check` passes; recovery restores snapshot cleanly. |
| **M 15.4** | `tests/performance/test_sustained_soak.py`<br>Full test suite | Full regression passes (484+ tests, 0 failures, exit code 0); memory growth < 50 MB over soak test. |
| **M 15.5** | `installer/cctv_ai.spec`<br>`installer/build_executable.py` | Standalone executable boots on Windows, loads PySide6 GUI, connects to DB, runs OpenVINO inference. |
| **M 15.6** | `installer/cctv_ai_setup.nsi`<br>`installer/build_installer.py` | NSIS builds `CCTV_AI_Setup_v1.5.0.exe`; installs cleanly; shortcuts work; uninstaller removes binary safely without deleting video data. |
| **M 15.7** | `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`<br>`docs/PHASE_15_IMPLEMENTATION_REPORT.md` | Complete documentation delivered; version updated to `1.5.0-alpha`. |
