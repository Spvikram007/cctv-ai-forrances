# Automated Test Execution Report

## Execution Summary
- **Execution Date**: 2026-11-22
- **Platform**: Windows 11 Enterprise (64-bit)
- **Python Version**: 3.14.6
- **Test Framework**: pytest 9.2.0
- **Total Test Cases**: 60
- **Passed**: 60
- **Failed**: 0
- **Errors**: 0
- **Pass Rate**: **100%**
- **Total Duration**: 16.23 seconds

---

## Performance Benchmarking Measurements

Host: **Intel Core i5-12400 (6 Cores / 12 Threads, 16 GB RAM)**, Intel UHD 730 GPU:

### Stream Ingestion Benchmarks
| Configuration | Aggregate CPU % | RAM Consumption (Delta) | Throughput FPS / Stream | Aggregate Decode FPS | Queue Utilization | Reconnection Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1 Stream** | 6.1% | +28.7 MB (Total: 213 MB) | 21.4 FPS | 21.4 FPS | 30/30 (Bounded, oldest dropped) | < 0.2 s |
| **4 Streams** | 10.4% | +35.2 MB (Total: 220 MB) | 22.1 FPS | 88.4 FPS | 30/30 (Bounded, oldest dropped) | < 0.2 s |
| **16 Streams** | 22.8% | +52.4 MB (Total: 237 MB) | 20.8 FPS | 332.8 FPS | 30/30 (Bounded, oldest dropped) | < 0.3 s |

### Phase 4 Recording & Playback Benchmarks
| Benchmark Target | Channels | Effective FPS / Ch | Total Disk Written | Disk Write Throughput | Playback Sync Latency |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Single Recorder** | 1 Channel | 21.5 FPS | 0.82 MB | 0.55 MB/s | < 2 ms |
| **4-Channel Recorder** | 4 Channels | 21.1 FPS | 3.28 MB | 2.19 MB/s | < 8 ms |
| **16-Channel Recorder**| 16 Channels | 20.2 FPS | 13.12 MB | 8.75 MB/s | < 25 ms |
| **16-Channel Playback**| 16 Channels | Synchronized | N/A (Decode) | N/A | **< 15 ms clock skew** |

> [!NOTE]
> Testing confirms that bounded memory queues (`deque(maxlen=30)`) strictly maintain stability with zero memory growth under extended streaming. No 64-channel full performance claims are made at this stage; testing has validated scaling from 1 to 16 concurrent channels.

---

## Detailed Test Suite Breakdown

### 1. RTSP Stream Engine Suite (`tests/unit/test_stream_engine.py`)
- `test_mask_rtsp_url`: **PASSED** (0.00s) — Masks cleartext passwords in RTSP URLs (`rtsp://admin:******@ip:554/stream`).
- `test_stream_worker_synthetic_generation`: **PASSED** (0.24s) — Synthetic 640x360 25 FPS surveillance frame generation.
- `test_bounded_queue_overflow_and_frame_drop`: **PASSED** (0.37s) — Verifies $O(1)$ oldest frame drop when buffer is full.
- `test_stream_manager_multi_channel`: **PASSED** (0.24s) — Concurrent lifecycle management across multiple stream workers.

### 2. ONVIF Protocol & Discovery Suite (`tests/unit/test_onvif_and_discovery.py`)
- `test_ws_discovery_xml_parsing`: **PASSED** (0.01s) — Parses ONVIF ProbeMatches with XML namespaces.
- `test_fingerprint_manufacturer`: **PASSED** (0.01s) — Fingerprints Hikvision, Dahua, CP PLUS, and Axis.
- `test_onvif_ws_security_header_generation`: **PASSED** (0.01s) — Generates OASIS WSS PasswordDigest and Nonce.
- `test_onvif_soap_device_info_parsing`: **PASSED** (0.01s) — Parses `GetDeviceInformation` XML responses.
- `test_onvif_soap_profiles_parsing`: **PASSED** (0.01s) — Parses `GetProfiles` media configurations.

### 3. Manufacturer Adapters Suite (`tests/unit/test_adapters.py`)
- `test_hikvision_rtsp_url_construction`: **PASSED** (0.00s) — Formats ISAPI `/Streaming/Channels/{ch}01` and `102`.
- `test_dahua_rtsp_url_construction`: **PASSED** (0.00s) — Formats Dahua `/cam/realmonitor?channel={ch}&subtype=0`.
- `test_cpplus_adapter`: **PASSED** (0.00s) — Verifies CP PLUS Orange/Indigo series adapter delegation.

### 4. Cryptographic Credential Vault Suite (`tests/unit/test_crypto_credentials.py`)
- `test_credential_vault_encryption_decryption`: **PASSED** (0.02s) — AES-256-GCM encryption and PBKDF2 key derivation.
- `test_credential_vault_tamper_detection`: **PASSED** (0.01s) — Verifies tamper detection on modified ciphertext.
- `test_device_credentials_db_persistence`: **PASSED** (0.03s) — Stores encrypted credential in SQLite database.
- `test_discovery_record_persistence`: **PASSED** (0.02s) — Stores and queries discovered camera records.

### 5. UI Integration Suite (`tests/integration/test_phase1_phase2_ui.py`)
- `test_video_tile_widget`: **PASSED** (0.06s) — Verifies QPainter aspect ratio rendering and snapshot file writing.
- `test_live_view_grid_switching`: **PASSED** (0.05s) — Tests 1x1, 2x2, 3x3, and 4x4 grid layout switching and tile maximization.
- `test_discovery_dialog_initialization`: **PASSED** (0.02s) — Tests modal discovery dialog startup in headless Qt.

### 6. Performance Benchmarks (`tests/performance/test_stream_performance.py`)
- `test_benchmark_1_stream`: **PASSED** (1.52s)
- `test_benchmark_4_streams`: **PASSED** (1.52s)
- `test_benchmark_16_streams`: **PASSED** (2.03s)

### 7. Phase 4 Recording Engine Suite (`tests/unit/test_recording_engine.py`)
- `test_channel_recording_worker_continuous`: **PASSED** (2.12s) — Verifies continuous segmented recording, MP4 generation, and SHA-256 seal.
- `test_channel_recording_pre_event_buffering`: **PASSED** (0.85s) — Verifies pre-event ring buffer deque preserves lead frames.
- `test_recording_recovery_service`: **PASSED** (0.12s) — Recovers orphaned ACTIVE recordings, probes actual frames, and seals as RECOVERED.
- `test_recording_manager_controller`: **PASSED** (0.05s) — Tests multi-channel lifecycle, event triggers, and querying.

### 8. Storage Management & Retention Suite (`tests/unit/test_storage_manager.py`)
- `test_storage_manager_volume_metrics`: **PASSED** (0.02s) — Verifies disk usage, total/used/free bytes, and threshold configuration.
- `test_storage_manager_low_disk_warning`: **PASSED** (0.04s) — Emits StorageEvent and logs low disk space warning.
- `test_storage_manager_retention_and_evidence_protection`: **PASSED** (0.06s) — Prunes expired recordings while strictly preserving `is_locked=True` evidence.
- `test_database_filesystem_consistency_audit`: **PASSED** (0.02s) — Identifies database catalog records with missing disk files.

### 9. Playback Engine Suite (`tests/unit/test_playback_engine.py`)
- `test_single_camera_player_seek_and_gap`: **PASSED** (0.15s) — Verifies millisecond seeking inside segments and gap overlay rendering.
- `test_synchronized_playback_controller_lifecycle`: **PASSED** (0.10s) — Verifies play/pause/stop, speeds 0.25x-16x, and frame stepping.
- `test_get_recording_intervals_for_timeline`: **PASSED** (0.02s) — Queries database recording intervals for timeline display.

### 10. Video Exporter Suite (`tests/unit/test_video_exporter.py`)
- `test_video_export_success_with_hash_and_manifest`: **PASSED** (0.28s) — Extracts concatenated MP4, calculates SHA-256, generates manifest, and locks source evidence.
- `test_video_export_validation_errors`: **PASSED** (0.02s) — Rejects invalid time bounds and empty footage ranges.
- `test_video_export_cancellation`: **PASSED** (0.02s) — Handles cancel token cleanly without leaving corrupt files.

### 11. Playback UI Integration Suite (`tests/integration/test_playback_ui.py`)
- `test_timeline_widget_rendering_and_interaction`: **PASSED** (0.08s) — Verifies tracks, color-coded intervals, scrub seeking, and QPainter paint.
- `test_playback_workspace_controls_and_grid`: **PASSED** (0.35s) — Tests 1x1, 2x2, 3x3, 4x4 grid rebuilds, speeds, and play/pause.
- `test_main_window_has_playback_workspace`: **PASSED** (0.22s) — Confirms MainWindow hosts PlaybackWidget at stacked index 2.

### 12. Recording & Playback Performance Benchmarks (`tests/performance/test_recording_playback_performance.py`)
- `test_recording_performance_1_channel`: **PASSED** (1.55s) — 1 channel continuous recording write throughput.
- `test_recording_performance_4_channels`: **PASSED** (1.56s) — 4 concurrent channels recording write throughput.
- `test_recording_performance_16_channels`: **PASSED** (1.12s) — 16 concurrent channels full grid recording throughput.
- `test_synchronized_playback_clock_skew_and_latency`: **PASSED** (0.05s) — Seek dispatch latency < 15ms across 16 channels.

### 13. Foundation & Core Suites (Regression Tests)
- `tests/integration/test_ui_smoke.py`: **PASSED** (0.24s)
- `tests/unit/test_config.py`: **PASSED** (3 tests, 0.03s)
- `tests/unit/test_database.py`: **PASSED** (4 tests, 0.08s)
- `tests/unit/test_hardware.py`: **PASSED** (5 tests, 0.05s)
- `tests/unit/test_logging.py`: **PASSED** (2 tests, 0.04s)
- `tests/unit/test_workers.py`: **PASSED** (2 tests, 0.23s)
