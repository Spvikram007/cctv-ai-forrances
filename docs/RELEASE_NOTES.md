# Release Notes - v0.1.0-alpha

## Overview
Initial alpha milestone for the **CCTV AI Intelligence Platform** Windows 11 desktop application. This release establishes the core architectural foundation, PySide6 Command Center graphical interface, automated hardware and AI acceleration detection, thread worker pools, structured redacting logging, universal PostgreSQL and SQLite WAL data layer, and initial automated test harness.

## Key Inclusions
- **PySide6 Command Center Interface**:
  - High-contrast, dark surveillance command center theme.
  - 15 navigation views matching platform specifications.
  - Header with system health, Intel GPU acceleration badge, active alarms counter, and live UTC clock.
  - Interactive Command Center Dashboard with live hardware gauges (Intel CPU, RAM, Intel UHD 730 GPU, Storage).
  - 64-channel surveillance capacity overview.
- **Hardware & AI Acceleration Detection**:
  - Automatically identifies Intel Core i5-12400 (6C/12T) CPU.
  - Detects OpenVINO 2026.4.1 runtime and targets available devices: `['CPU', 'GPU']` (Intel UHD Graphics 730).
  - Assesses hardware acceleration tier and sets maximum recommended concurrent AI streams.
- **Resilient Persistence Layer**:
  - Universal SQLAlchemy 2.0 schema spanning Users, RBAC Roles, Sites, Locations, Devices, Channels, Stream Profiles, Storage Volumes, Recordings, AI Models, Detections, and Events.
  - PostgreSQL support with transparent automatic fallback to local SQLite in WAL mode.
  - Pre-seeded with 5 default roles (Administrator, Supervisor, Operator, Investigator, Viewer) and default local administrator account.
- **Zero-Cloud Local Security**:
  - Offline operation with zero external internet dependencies.
  - Sensitive credential redacting formatter for logs (RTSP passwords, tokens, auth headers).
- **Test Suite**:
  - 17 automated unit and integration tests passing with 100% success rate.

## Known Limitations
- Video stream acquisition and live grid rendering are scheduled for Phase 2 and Phase 3.
- Views 1 through 14 display phase-aligned module placeholders.
