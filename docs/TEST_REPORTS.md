# Automated Test Execution Report

## Execution Summary
- **Execution Date**: 2026-11-22
- **Platform**: Windows 11 (64-bit)
- **Python Version**: 3.14.6
- **Test Framework**: pytest 9.2.0
- **Total Test Cases**: 17
- **Passed**: 17
- **Failed**: 0
- **Errors**: 0
- **Pass Rate**: **100%**
- **Total Duration**: 1.08 seconds

---

## Detailed Test Suite Results

### 1. Integration UI Smoke Suite (`tests/integration/test_ui_smoke.py`)
- `test_main_window_smoke`: **PASSED** (0.24s)
  - Verified `QApplication` headless initialization using `offscreen` Qt platform.
  - Verified window title and geometry constraints.
  - Verified existence of 15 primary navigation views in `QStackedWidget`.
  - Verified sidebar navigation button state and active view switching.
  - Verified telemetry timer updates.
  - Verified clean graceful shutdown of window, timers, and workers.

### 2. Configuration Unit Suite (`tests/unit/test_config.py`)
- `test_default_settings`: **PASSED** (0.01s)
- `test_custom_settings_validation`: **PASSED** (0.01s)
- `test_directory_creation`: **PASSED** (0.01s)

### 3. Database Unit Suite (`tests/unit/test_database.py`)
- `test_database_health_check`: **PASSED** (0.02s)
  - Verified SQLite WAL mode connectivity, query latency measurement (< 2ms), and table schema presence.
- `test_role_and_user_creation`: **PASSED** (0.02s)
  - Verified UUID primary key generation (36 characters), foreign key relationship between User and Role.
- `test_device_and_channel_creation`: **PASSED** (0.02s)
  - Verified Site -> Location -> Device -> DeviceChannel cascading relationships.
- `test_transaction_rollback_on_error`: **PASSED** (0.02s)
  - Verified that database transaction correctly aborts and rolls back on unhandled exceptions.

### 4. Hardware Probing Unit Suite (`tests/unit/test_hardware.py`)
- `test_detect_cpu`: **PASSED** (0.01s)
  - Successfully detected 12th Gen Intel Core i5-12400 (6 cores, 12 logical threads).
- `test_detect_ram`: **PASSED** (0.01s)
  - Successfully detected host system RAM and utilization metrics.
- `test_detect_storage`: **PASSED** (0.01s)
  - Successfully detected disk drive capacity and free space.
- `test_detect_openvino`: **PASSED** (0.01s)
  - Verified OpenVINO 2026.4.1 runtime detection and target device discovery: `['CPU', 'GPU']`.
- `test_generate_full_report`: **PASSED** (0.02s)
  - Verified complete hardware report serialization and classification into `INTEL_GPU_OPENVINO` acceleration tier.

### 5. Logging & Redaction Unit Suite (`tests/unit/test_logging.py`)
- `test_redact_sensitive_text`: **PASSED** (0.01s)
  - Verified masking of RTSP passwords (`rtsp://admin:******@ip:port/stream`).
  - Verified masking of HTTP basic auth credentials and JSON secrets.
- `test_logging_setup_and_output`: **PASSED** (0.03s)
  - Verified creation and output of rotating human-readable log file and JSONL structured log file.

### 6. Worker Pool Unit Suite (`tests/unit/test_workers.py`)
- `test_task_pool_execution`: **PASSED** (0.01s)
  - Verified asynchronous task execution and future resolution via managed ThreadPool.
- `test_background_worker_lifecycle`: **PASSED** (0.22s)
  - Verified registration, thread startup, periodic work cycles, heartbeat tracking, and clean stop.
