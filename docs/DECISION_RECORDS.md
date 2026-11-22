# Architecture Decision Records (ADRs)

## ADR-001: Architectural Pattern — Modular Monolith with Process/Thread Workers

### Context
A 64-channel CCTV AI surveillance platform requires high bandwidth, sub-second latency, and coordinated video streaming, AI inference, and database recording. A microservices architecture on a single Windows desktop introduces immense IPC overhead, serialization bottlenecks (especially for multi-megapixel video frames), and complicated local orchestration.

### Decision
Adopt a **Modular Monolith** architecture. Subsystems (Video Engine, AI Engine, Forensics, Alarms, UI) are structured as decoupled modules communicating via an in-process thread-safe Event Bus and bounded memory queues. Intensive tasks (RTSP decoding, AI inference) run in isolated background worker threads and multiprocessing pools, leaving the PySide6 UI event loop unblocked.

### Status
Accepted (2026-11-22).

---

## ADR-002: Dual PostgreSQL and SQLite WAL Mode Persistence

### Context
Enterprise surveillance environments often demand PostgreSQL for multi-site synchronization, centralized analytics, and concurrent relational reporting. However, standalone offline installations require zero configuration and immediate operation without requiring the operator to install, configure, or administer a separate database server.

### Decision
Implement a universal SQLAlchemy 2.0 ORM data layer that supports **PostgreSQL** when configured and available, but automatically and gracefully falls back to **SQLite with Write-Ahead Logging (WAL)** mode enabled. SQLite WAL mode provides concurrent read-while-writing capabilities, crash recovery, and 5000ms busy timeouts, meeting the requirements of offline surveillance workstations.

### Status
Accepted (2026-11-22).

---

## ADR-003: Hardware Acceleration — Intel OpenVINO™ with Automatic CPU Fallback

### Context
Surveillance workloads require continuous multi-stream AI inference. The target environment possesses an Intel 12th Gen Core i5-12400 CPU and integrated Intel UHD Graphics 730 GPU.

### Decision
Use **Intel OpenVINO™** (v2026.4.1) as the primary deep-learning inference backend, with ONNX Runtime as a secondary option. The hardware detector automatically targets the `GPU` plugin (`Intel(R) UHD Graphics 730`) with FP16 precision. If GPU initialization is unavailable or overloaded, the system automatically falls back to the `CPU` plugin with AVX2 vectorized execution. High-resolution main streams are decoded for viewing and storage, while lower-resolution substreams (e.g. 640x360) are routed to the AI engine to maximize throughput.

### Status
Accepted (2026-11-22).

---

## ADR-004: Desktop GUI Framework — PySide6 with Dark Surveillance Theme

### Context
The application is a Windows 11 desktop platform that requires responsive layout switching (1, 4, 9, 16, 25, 36, 64-channel grids), hardware-accelerated video rendering, and 24/7 command center visibility without eye fatigue.

### Decision
Use **PySide6** (Qt 6.12 for Python) styled with a custom high-contrast dark QSS theme (`#0d1117`, `#161b22`, `#58a6ff`, `#238636`, `#f85149`). All UI updates are dispatched asynchronously via Qt Signals/Slots and QTimer polling, preventing stream acquisition or AI processing from blocking the interface.

### Status
Accepted (2026-11-22).

---

## ADR-005: Security Baseline — Zero External Cloud Reliance & Credential Masking

### Context
Security cameras operate on secure networks and handle sensitive video data. Transmitting biometrics, credentials, or video feeds to third-party cloud services violates data sovereignty and security policies.

### Decision
All AI processing, video storage, user authentication, and forensics operate **100% locally and offline**. No outbound cloud network requests are initiated. All log records pass through a redacting formatter that strips camera passwords, database credentials, and session tokens before emitting to console or disk.

### Status
Accepted (2026-11-22).
