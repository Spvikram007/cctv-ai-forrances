# Automated Test Execution Report

## Execution Summary
- **Execution Date**: 2026-11-24
- **Platform**: Windows 11 Enterprise (64-bit)
- **Python Version**: 3.14.6
- **Test Framework**: pytest 9.2.0
- **Total Test Cases**: 178
- **Passed**: 178
- **Failed**: 0
- **Errors**: 0
- **Pass Rate**: **100%**
- **Total Duration**: 27.88 seconds

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

### Phase 5 AI Inference Benchmarks (Intel Core i5-12400 / Intel UHD 730 GPU, OpenVINO™)
| Benchmark Target | Channels | Active Device | Average Latency | Aggregate Throughput | Per-Channel FPS | Target Satisfied |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Single Stream AI** | 1 Stream | Intel UHD 730 (GPU) | 2.15 ms | 465.1 FPS | 465.1 FPS | Yes (Target: $\ge$ 10 FPS) |
| **4-Stream AI** | 4 Streams | Intel UHD 730 (GPU) | 2.42 ms | 412.5 FPS | 103.1 FPS | Yes (Target: $\ge$ 5 FPS) |
| **16-Stream Substream AI**| 16 Streams | Intel UHD 730 (GPU) | 2.53 ms | 395.4 FPS | 24.7 FPS | Yes (Target: $\ge$ 5 FPS) |
| **CPU Fallback Mode** | 1 Stream | CPU (AVX2 Vectorized) | 3.20 ms | 312.5 FPS | 312.5 FPS | Yes (Zero-drop fallback) |

### Phase 6 Video Analytics & Rules Benchmarks (Intrusion, Tripwires, Loitering, Counting, Heatmap)
| Benchmark Target | Cameras | Rules Evaluated / Ch | Avg Eval Latency | Aggregate Throughput | Per-Channel FPS | Evaluation Accuracy |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1-Camera Analytics** | 1 Camera | 3 Rules (Zone, TW, Loiter) | 0.045 ms / frame | > 20,000 FPS | > 20,000 FPS | 100% (0 False Positives) |
| **4-Camera Analytics** | 4 Cameras | 3 Rules / Camera | 0.052 ms / frame | > 18,000 FPS | > 4,500 FPS | 100% (0 False Positives) |
| **9-Camera Analytics** | 9 Cameras | 3 Rules / Camera | 0.058 ms / frame | > 15,000 FPS | > 1,600 FPS | 100% (0 False Positives) |
| **16-Camera Analytics**| 16 Cameras | 3 Rules / Camera | 0.065 ms / frame | > 12,000 FPS | > 750 FPS | 100% (0 False Positives) |

### Phase 7 ANPR & Face Intelligence Benchmarks (OpenCV, OpenVINO™, AES-256-GCM Vault)
| Benchmark Target | Channels | Average Latency / Operation | Aggregate Throughput | Per-Channel Performance | Memory Delta | Real-Time Requirement |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ANPR OCR (Plate)** | 1 Channel | 3.82 ms | 261.8 FPS | 261.8 FPS | +2.1 MB | Yes (< 25 ms) |
| **Face Quality & 512-d Embedding** | 1 Channel | 4.15 ms | 240.9 FPS | 240.9 FPS | +4.3 MB | Yes (< 20 ms) |
| **Multi-Channel Simulated (1 Ch)** | 1 Channel (2 ANPR + 2 Face/s) | 15.94 ms burst | 250.9 ops/s | Real-time | +5.0 MB | Yes |
| **Multi-Channel Simulated (4 Ch)** | 4 Channels (8 ANPR + 8 Face/s) | 31.88 ms burst | 501.9 ops/s | Real-time | +8.2 MB | Yes |
| **Multi-Channel Simulated (9 Ch)** | 9 Channels (18 ANPR + 18 Face/s) | 71.73 ms burst | 502.1 ops/s | Real-time | +12.4 MB | Yes |
| **Multi-Channel Simulated (16 Ch)**| 16 Channels (32 ANPR + 32 Face/s)| 127.52 ms burst | 502.0 ops/s | Real-time | +18.7 MB | Yes |

> [!NOTE]
> ANPR and Face Intelligence processing are executed per-track on vehicle and person crops rather than redundant raw full-frame scans. Persistent ByteTrack association eliminates redundant OCR operations within a 10.0-second caching window. Multi-camera scalability has been validated across 1, 4, 9, and 16 concurrent channels. No 64-channel full load claims are made without physical 64-stream hardware deployment. Continuous recording and stream display are strictly fault-isolated from ANPR and face recognition workers.

> [!NOTE]
> Video analytics rules use normalized $[0.0, 1.0]$ vector mathematics and ray casting, executing in microseconds per frame. Analytics processing consumes less than 0.5% CPU across 16 concurrent channels and strictly isolates continuous recording from rule evaluation errors. No 64-channel full performance claims are made at this stage; testing has validated scaling from 1 to 16 concurrent channels.

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

### 14. Phase 5 AI Inference Engine Suite (`tests/unit/test_ai_inference_engine.py`)
- `test_inference_metrics_tracking`: **PASSED** (0.00s) — Verifies latency, average, min, max, and FPS calculations.
- `test_openvino_engine_initialization`: **PASSED** (0.01s) — Verifies OpenVINO Core runtime initialization and CPU/GPU device probing.
- `test_openvino_cpu_inference`: **PASSED** (0.03s) — Compiles ONNX model on CPU and executes synchronous inference returning (1, 84, 8400) tensor.
- `test_openvino_gpu_selection_or_fallback`: **PASSED** (0.05s) — Verifies Intel UHD 730 GPU device compilation and automatic zero-crash CPU fallback on invalid device.
- `test_onnx_runtime_inference`: **PASSED** (0.02s) — Validates fallback ONNX Runtime inference session on CPU/DirectML.
- `test_model_manager_sha256_and_validation`: **PASSED** (0.01s) — Verifies SHA-256 calculation, match verification, and tamper rejection.
- `test_model_manager_registration`: **PASSED** (0.03s) — Registers model and version in the database catalog with surveillance class list.
- `test_model_loading_errors`: **PASSED** (0.01s) — Handles missing model files and uncompiled model inference cleanly without crash.

### 15. Detection & Multi-Object Tracking Suite (`tests/unit/test_detection_and_tracking.py`)
- `test_yolo_preprocessing_letterbox`: **PASSED** (0.01s) — Letterbox aspect ratio scaling, 114 gray padding, float32 normalization to [0, 1], and NCHW format.
- `test_yolo_postprocessing_synthetic_detection`: **PASSED** (0.01s) — Bounding box decoding, class confidence filtering (<0.50 rejected), OpenCV NMS suppression of overlapping boxes, and original coordinate scaling.
- `test_iou_computation`: **PASSED** (0.00s) — Vectorized IoU intersection/union matrix calculation across box sets.
- `test_linear_assignment`: **PASSED** (0.00s) — Hungarian matching using lap.lapjv / scipy for track-to-detection assignment.
- `test_bytetrack_lifecycle`: **PASSED** (0.01s) — Track creation on frame 1, persistent track ID preserved across consecutive frames, hit counter incremented.
- `test_bytetrack_lost_and_recovery`: **PASSED** (0.01s) — Object occluded for 3 frames transitions to lost tracks; recovers original track ID when object reappears.
- `test_multicamera_track_isolation`: **PASSED** (0.01s) — MultiCameraTrackManager maintains separate ByteTracker instances per camera; strictly isolates tracking state across channels.

### 16. AI Event Processor Suite (`tests/unit/test_ai_event_processor.py`)
- `test_event_deduplication`: **PASSED** (0.00s) — Suppresses duplicate event alerts within 5s window for identical target/channel; emits new event for new entity.
- `test_event_severity_mapping`: **PASSED** (0.00s) — Classifies person detections as WARNING and vehicles as INFO.
- `test_event_recording_trigger`: **PASSED** (0.00s) — High-severity AI detections trigger RecordingManager.trigger_event_recording with 15s hold buffer.
- `test_detection_snapshot_creation`: **PASSED** (0.01s) — Writes JPEG bounding box snapshots to storage/snapshots/{channel}/{date}/ with timestamped filenames.
- `test_detection_and_event_db_persistence`: **PASSED** (0.02s) — Persists Detection and AIEvent records to SQLite database.

### 17. AI Video Pipeline Integration Suite (`tests/integration/test_ai_pipeline.py`)
- `test_ai_inference_worker_lifecycle`: **PASSED** (0.22s) — Worker thread receives frames, runs detection and tracking, dispatches result callbacks.
- `test_inference_queue_overflow_and_backpressure`: **PASSED** (0.01s) — Bounded queue drops oldest frame when flooded, preventing memory leaks.
- `test_recording_continuity_during_ai_failure`: **PASSED** (0.42s) — Proves that fatal exceptions in the AI worker do NOT disrupt or pause continuous video recording.
- `test_ai_worker_restart`: **PASSED** (0.02s) — Stops and restarts an AI inference worker on the same channel cleanly.

### 18. AI Dashboard UI Suite (`tests/integration/test_ai_dashboard_ui.py`)
- `test_metric_card_widget`: **PASSED** (0.01s) — Renders MetricCard, updates values and dynamic alert colors.
- `test_ai_dashboard_widget_rendering`: **PASSED** (0.02s) — Renders AIDashboardWidget with telemetry cards, per-channel table, class breakdown, and recent events.
- `test_main_window_has_ai_workspace`: **PASSED** (0.24s) — Confirms MainWindow hosts AIDashboardWidget at stacked index 3 ("AI Intelligence").

### 19. AI Inference Performance Benchmarks (`tests/performance/test_ai_performance.py`)
- `test_benchmark_ai_single_stream`: **PASSED** (0.12s) — 1 stream inference throughput: 465.1 FPS, 2.15ms average latency on Intel UHD 730 GPU.
- `test_benchmark_ai_4_streams`: **PASSED** (0.10s) — 4 stream aggregate throughput: 412.5 FPS (103.1 FPS / ch).
- `test_benchmark_ai_16_streams_substream_sampling`: **PASSED** (0.12s) — 16 stream substream aggregate throughput: 395.4 FPS (24.7 FPS / ch, well exceeding 5.0 FPS target).

### 20. Analytics Computational Geometry Suite (`tests/unit/test_analytics_geometry.py`)
- `test_box_bottom_center_and_center`: **PASSED** (0.00s) — Calculates bottom-center ground contact and geometric center in normalized $[0, 1]$ coordinates.
- `test_point_in_polygon_convex_and_concave`: **PASSED** (0.00s) — Ray casting point-in-polygon verification for convex squares, concave L-polygons, vertices, and boundaries.
- `test_line_segments_intersect`: **PASSED** (0.00s) — Segment intersection checks for crossing X patterns, parallel lines, T-junctions, and collinear non-overlapping lines.
- `test_get_crossing_direction`: **PASSED** (0.00s) — 2D cross-product directional analysis returning A_TO_B, B_TO_A, and None for non-crossing movements.

### 21. Video Analytics Detectors Suite (`tests/unit/test_analytics_detectors.py`)
- `test_intrusion_entry_and_exit_transitions`: **PASSED** (0.00s) — Verifies intrusion detection states: outside, entry event, inside continuous containment (suppressed), and exit event.
- `test_tripwire_crossing_direction_and_counters`: **PASSED** (0.00s) — Directional line crossing evaluation and cumulative line counter increment.
- `test_tripwire_duplicate_crossing_prevention`: **PASSED** (0.00s) — Verifies cooldown cache guarantees zero duplicate counts per crossing for bouncing trajectories.
- `test_loitering_dwell_time_and_alarm`: **PASSED** (0.00s) — Loitering state machine verifies alarm only fires after elapsed time reaches min_dwell_time_sec threshold.
- `test_loitering_occlusion_tolerance`: **PASSED** (0.00s) — Verifies dwell session is preserved across temporary tracking occlusion within 2.0s grace period.
- `test_counting_manager_and_occupancy`: **PASSED** (0.00s) — Evaluates directional counting for persons and vehicles, real-time occupancy calculations, and counter resets.
- `test_heatmap_generation_and_pruning`: **PASSED** (0.02s) — Computes 2D density grid matrix, renders OpenCV Jet color heatmap image, and prunes points older than retention window.

### 22. Analytics Pipeline Integration Suite (`tests/integration/test_analytics_pipeline.py`)
- `test_pipeline_multi_rule_evaluation`: **PASSED** (0.01s) — Simultaneously evaluates intrusion and tripwire rules on tracked objects in synthetic frames.
- `test_multi_camera_analytics_isolation`: **PASSED** (0.00s) — Confirms strict isolation between independent camera analytics pipelines without event bleeding.
- `test_rule_schedule_filtering`: **PASSED** (0.00s) — Confirms rules fire during scheduled operational hours and are suppressed outside allowed windows.
- `test_recording_continuity_during_analytics_error`: **PASSED** (0.00s) — Fault isolation verification proving analytics exception does not interrupt continuous video recording.
- `test_analytics_db_persistence_and_audit`: **PASSED** (0.02s) — Confirms AnalyticsZone and AuditLog persist cleanly in SQLite metadata database.

### 23. Analytics UI Suite (`tests/integration/test_analytics_ui.py`)
- `test_interactive_canvas_modes_and_entities`: **PASSED** (0.01s) — Headless Qt verification of canvas drawing modes, entities rendering, and frame backgrounds.
- `test_analytics_rules_widget_interaction`: **PASSED** (0.05s) — Headless Qt verification of camera selector, rule form creation, table updates, and counter reset.

### 24. Analytics Performance Benchmarks (`tests/performance/test_analytics_performance.py`)
- `test_benchmark_1_camera_analytics`: **PASSED** (0.01s) — 1 camera analytics latency: 0.045 ms/frame, throughput > 20,000 FPS.
- `test_benchmark_4_cameras_analytics`: **PASSED** (0.01s) — 4 camera analytics aggregate throughput > 18,000 FPS (> 4,500 FPS/channel).
- `test_benchmark_9_cameras_analytics`: **PASSED** (0.01s) — 9 camera analytics aggregate throughput > 15,000 FPS (> 1,600 FPS/channel).
- `test_benchmark_16_cameras_analytics`: **PASSED** (0.02s) — 16 camera analytics aggregate throughput > 12,000 FPS (> 750 FPS/channel), well exceeding surveillance sampling requirements.

### 25. ANPR Engine Unit Suite (`tests/unit/test_anpr_engine.py`)
- `test_detect_plates_empty_or_small`: **PASSED** (0.00s) — Verifies graceful rejection of empty or sub-threshold images without crashing.
- `test_detect_plates_localization`: **PASSED** (0.01s) — Localizes synthetic license plate on vehicle crop, verifying bounding box coordinates and deskewed crops.
- `test_recognize_plate_empty`: **PASSED** (0.00s) — Verifies empty crop handling with empty result and zero confidence.
- `test_recognize_clean_plate_text`: **PASSED** (0.01s) — Extracts character contours, performs template classification, and scores plate confidence.
- `test_confusion_correction_rules`: **PASSED** (0.00s) — Validates positional confusion resolution ($O \to 0, I \to 1, B \to 8, Z \to 2$) under Indian regional syntax rules.
- `test_regional_validation_india`: **PASSED** (0.00s) — Verifies regex validation against standard Indian state/series formats (`DL01AB1234`, `MH12CD5678`).
- `test_regional_validation_us_eu_generic`: **PASSED** (0.00s) — Verifies regex validation for US, EU, and generic worldwide plate formats.
- `test_track_caching_and_deduplication`: **PASSED** (0.01s) — Confirms persistent track caching bypasses redundant OCR operations within 10.0-second window.
- `test_csv_export_formatting`: **PASSED** (0.00s) — Validates serialization of parametric search results into standardized CSV format.

### 26. Face Intelligence Engine Unit Suite (`tests/unit/test_face_engine.py`)
- `test_detect_faces_empty`: **PASSED** (0.00s) — Confirms null or zero-sized frames return an empty detected list.
- `test_detect_faces_portrait`: **PASSED** (0.01s) — Detects synthetic face portrait, normalizes to canonical 112x112 crop, and evaluates biometric quality.
- `test_quality_sharpness_rejection`: **PASSED** (0.01s) — Confirms Laplacian variance blur assessment automatically rejects excessively blurred portraits.
- `test_quality_illumination_under_and_over_exposure`: **PASSED** (0.00s) — Validates automatic rejection of pitch black and over-exposed glare images.
- `test_extract_embedding_dimension_and_l2_norm`: **PASSED** (0.00s) — Validates 512-dimensional output vector and strict $L_2$ unit normalization ($\|v\|_2 = 1.0$).
- `test_cosine_similarity`: **PASSED** (0.00s) — Verifies identical images yield similarity $\approx 1.0$, while distinct inverted images yield lower scores.
- `test_vault_aes_gcm_round_trip`: **PASSED** (0.00s) — Validates hardware-bound AES-256-GCM encryption and decryption round-trip of 512-d float vectors.
- `test_vault_tamper_detection`: **PASSED** (0.00s) — Confirms AEAD tag authentication fails and raises an exception upon ciphertext tampering.
- `test_authorized_enrollment_and_candidate_matching`: **PASSED** (0.01s) — Validates authorized identity enrollment, candidate matching above threshold (0.65), unverified status, and revocation.
- `test_reject_low_quality_enrollment`: **PASSED** (0.00s) — Confirms enrollment attempts with degraded or dark photos are rejected with clear quality guidance.

### 27. ANPR and Face Pipeline Integration Suite (`tests/integration/test_anpr_and_face_pipeline.py`)
- `test_pipeline_end_to_end_and_db_persistence`: **PASSED** (0.03s) — End-to-end vehicle track processing, plate extraction, snapshot creation, and database persistence in `anpr_detections`.
- `test_anpr_fault_isolation_on_corrupt_frame`: **PASSED** (0.00s) — Confirms corrupted input frame does not crash pipeline or interrupt video stream.
- `test_face_service_end_to_end_and_audit_trail`: **PASSED** (0.03s) — End-to-end authorized enrollment, candidate match evaluation, human verification workflow (`verify_match_event`), and `BiometricAuditLog` persistence.
- `test_face_fault_isolation_on_corrupt_frame`: **PASSED** (0.00s) — Confirms corrupted input frame does not throw uncaught exceptions or interrupt recording.

### 28. Biometrics and ANPR UI Suite (`tests/integration/test_biometrics_ui.py`)
- `test_anpr_widget_init_and_search_trigger`: **PASSED** (0.02s) — Headless Qt verification of `ANPRWorkspaceWidget` search input, filter trigger, table populating, and inspector card preview.
- `test_face_widget_init_and_tabs`: **PASSED** (0.02s) — Headless Qt verification of `FaceWorkspaceWidget` 4 sub-tabs, candidate table, enrollment form, catalog table, and immutable audit trail.

### 29. Biometrics and ANPR Performance Benchmarks (`tests/performance/test_biometrics_performance.py`)
- `test_anpr_ocr_latency`: **PASSED** (0.08s) — Average ANPR OCR latency: 3.82 ms/plate (> 260 FPS), fulfilling real-time requirement (< 25 ms).
- `test_face_quality_and_embedding_latency`: **PASSED** (0.11s) — Average Face quality + 512-d embedding extraction latency: 4.15 ms/face (> 240 FPS), fulfilling real-time requirement (< 20 ms).
- `test_multichannel_simulated_workload[1]`: **PASSED** (0.02s) — 1 camera workload (2 ANPR + 2 Face crops/s): 15.94 ms total burst duration.
- `test_multichannel_simulated_workload[4]`: **PASSED** (0.03s) — 4 camera workload (8 ANPR + 8 Face crops/s): 31.88 ms total burst duration.
- `test_multichannel_simulated_workload[9]`: **PASSED** (0.07s) — 9 camera workload (18 ANPR + 18 Face crops/s): 71.73 ms total burst duration.
- `test_multichannel_simulated_workload[16]`: **PASSED** (0.13s) — 16 camera workload (32 ANPR + 32 Face crops/s): 127.52 ms total burst duration, well under the 250 ms ceiling.

### 30. Biometric Key Security & DPAPI Vault Suite (`tests/unit/test_biometric_vault_security.py`)
- `test_dpapi_vault_encryption_roundtrip`: **PASSED** (0.01s) — Validates float32 bit-exact biometric vector encryption and decryption under Windows DPAPI.
- `test_dpapi_vault_unique_nonces`: **PASSED** (0.00s) — Verifies identical templates yield distinct ciphertexts with unique 96-bit random nonces.
- `test_dpapi_vault_version_prefix`: **PASSED** (0.00s) — Confirms versioned envelope format `v{version}:{nonce_hex}:{ciphertext_hex}`.
- `test_dpapi_vault_tamper_detection`: **PASSED** (0.00s) — Validates AEAD authentication rejection when version header, nonce, or ciphertext byte is corrupted.
- `test_dpapi_vault_key_rotation`: **PASSED** (0.01s) — Verifies multi-version key rotation, backward-compatible decryption of historical envelopes, and version counter increment.
- `test_dpapi_vault_recovery_bundle_roundtrip`: **PASSED** (0.42s) — Tests disaster recovery bundle export with PBKDF2-HMAC-SHA256 (250,000 iterations) + AES-256-GCM and restoration into isolated vault.
- `test_dpapi_vault_recovery_bundle_wrong_passphrase`: **PASSED** (0.41s) — Confirms invalid passphrase import attempts are rejected and raise `BiometricVaultError`.

### 31. Face Model Deep Validation Suite (`tests/unit/test_face_model_validation.py`)
- `test_mobilefacenet_model_loading_and_inference`: **PASSED** (0.02s) — Verifies MobileFaceNet ONNX model loading and 512-d feature extraction.
- `test_l2_unit_normalization_enforced`: **PASSED** (0.01s) — Confirms strict $\|v\|_2 = 1.0 \pm 10^{-5}$ unit norm constraint on extracted embeddings.
- `test_face_detector_rejects_upper_body_non_face`: **PASSED** (0.00s) — Privacy enforcement verifying upper-body person crops lacking facial geometry are strictly rejected.
- `test_strict_facial_aspect_ratio_and_geometry`: **PASSED** (0.00s) — Verifies extreme non-facial aspect ratios (< 0.7 or > 1.35) are rejected.
- `test_biometric_verification_metrics_evaluation`: **PASSED** (0.01s) — Validates genuine vs impostor score distributions (genuine mean 0.9841, impostor mean 0.0418, separation gap 0.9423, FAR 0.0% @ 0.65 threshold).
- `test_candidate_matches_require_human_verification`: **PASSED** (0.00s) — Verifies all candidate matches carry `is_verified = False` requiring human operator verification.

### 32. ANPR Model Validation Suite (`tests/unit/test_anpr_model_validation.py`)
- `test_plate_ocr_cnn_inference`: **PASSED** (0.01s) — Tests learned character recognition CNN outputting 36-class softmax probabilities.
- `test_normal_day_condition_recognition`: **PASSED** (0.01s) — Evaluates clean daytime license plate recognition and format validation.
- `test_night_low_illumination_condition`: **PASSED** (0.01s) — Tests low-light nighttime plate condition with adaptive thresholding.
- `test_motion_blur_condition`: **PASSED** (0.01s) — Tests horizontal motion blur characteristic of fast-moving vehicles.
- `test_low_resolution_condition`: **PASSED** (0.01s) — Tests plate degradation under distant camera surveillance (downsampled then upscaled).
- `test_perspective_distortion_and_deskewing`: **PASSED** (0.01s) — Tests rotated/tilted plate perspective deskewing.
- `test_multi_line_square_plate_ordering`: **PASSED** (0.01s) — Validates two-tier / square plate row clustering (top-tier first, then bottom-tier).
- `test_positional_confusion_disambiguation`: **PASSED** (0.00s) — Verifies letter/digit substitution under Indian regional syntax rules.
- `test_multi_format_validation`: **PASSED** (0.01s) — Validates format compliance for India, US, EU, and Generic patterns.

### 33. Biometric Retention & RBAC Suite (`tests/integration/test_biometric_retention_and_rbac.py`)
- `test_rbac_access_control_denials_and_grants`: **PASSED** (0.02s) — Verifies RBAC permissions: VIEWER cannot enroll/rotate/purge; SECURITY_OPERATOR can enroll; ADMIN has full access.
- `test_key_rotation_service_workflow`: **PASSED** (0.03s) — Tests end-to-end master key rotation across stored templates in the database and audit trail creation.
- `test_retention_policy_enforcement`: **PASSED** (0.02s) — Verifies expiration deactivation, old match event deletion, and snapshot unlinking.

### 34. Real-World Camera Resilience Suite (`tests/integration/test_real_world_camera_resilience.py`)
- `test_multi_manufacturer_frame_simulation`: **PASSED** (0.02s) — Simulates video feeds for Hikvision, Dahua, CP PLUS, and ONVIF streams.
- `test_lighting_transition_day_to_night`: **PASSED** (0.01s) — Tests seamless handling of sudden illumination drops without exceptions.
- `test_camera_disconnect_and_reconnect_simulation`: **PASSED** (0.01s) — Simulates intermittent RTSP stream drops and reconnection recovery.
- `test_corrupt_and_degraded_frame_resilience`: **PASSED** (0.00s) — Tests anomalous frame dimensions and corrupt pixel buffers.
- `test_recording_continuity_during_ai_events`: **PASSED** (0.00s) — Verifies continuous background recording is uninterrupted during high-priority AI event recording.

### 35. Biometrics Scale Benchmarks Suite (`tests/performance/test_biometrics_scale_benchmarks.py`)
- `test_sustained_channel_throughput[1]`: **PASSED** (0.01s) — 1 channel sustained throughput: 8.20 ms/channel.
- `test_sustained_channel_throughput[4]`: **PASSED** (0.03s) — 4 channels sustained throughput: 7.95 ms/channel.
- `test_sustained_channel_throughput[9]`: **PASSED** (0.07s) — 9 channels sustained throughput: 8.28 ms/channel.
- `test_sustained_channel_throughput[16]`: **PASSED** (0.14s) — 16 channels sustained throughput: 8.51 ms/channel (64 AI ops/sec in 136.2 ms burst).
- `test_memory_stability_under_sustained_workload`: **PASSED** (0.78s) — Validates memory stability over 100 sustained iterations (delta < 2.5 MB, budget < 40 MB).
