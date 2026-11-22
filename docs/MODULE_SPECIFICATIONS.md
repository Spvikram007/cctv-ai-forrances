# Module Specifications

## Module 1: Dashboard (`modules/dashboard`)
- **Status**: COMPLETE (Phase 0)
- **Role**: Command Center primary telemetry hub.
- **Components**: Hardware gauges (Intel CPU, RAM, Intel UHD 730 GPU, Storage), 64-channel surveillance summary cards, OpenVINO acceleration panel, live alarm/event ticker.
- **Refresh Frequency**: 3000ms safe non-blocking Qt polling.

## Module 2: Live CCTV Monitoring (`modules/live_monitoring`)
- **Status**: PLANNED (Phase 3)
- **Role**: High-capacity multi-stream visual display.
- **Layouts**: 1, 4, 9, 16, 25, 36, 64-channel adaptive grids.
- **Features**: Substream/mainstream switching, PTZ controls, digital zoom, snapshot extraction, AI overlay rendering.

## Module 3: Playback Engine (`modules/video_playback`)
- **Status**: PLANNED (Phase 4)
- **Role**: Recorded video investigation and historical playback.
- **Features**: Synchronized multi-timeline scrubbing, frame stepping, variable playback speed (0.25x to 16x), MP4 clip export.

## Module 4: AI Object Detection (`engines/detection_engine`)
- **Status**: PLANNED (Phase 5)
- **Role**: Real-time object classification and bounding box generation.
- **Classes**: Person, car, motorcycle, bus, truck, bicycle, bag, animal, fire, smoke.
- **Acceleration**: Intel OpenVINO™ GPU/CPU execution.

## Module 5: Human Intelligence (`engines/face_engine`, `engines/detection_engine`)
- **Status**: PLANNED (Phase 7)
- **Role**: Person re-identification, clothing attribute analysis, authorized face matching.
- **Biometrics**: Strict candidate verification workflow; 512-d feature vectors from authorized enrolled identity database only.

## Module 6: Vehicle Intelligence (`engines/anpr_engine`)
- **Status**: PLANNED (Phase 7)
- **Role**: Vehicle classification, directional tracking, license plate localization and OCR.

## Module 7: Behaviour Analytics (`engines/event_engine`)
- **Status**: PLANNED (Phase 8)
- **Role**: Virtual perimeter monitoring, intrusion zones, line-crossing alarms, loitering detection, crowd density calculation.

## Module 8: Smart Investigation (`modules/investigation`)
- **Status**: PLANNED (Phase 6)
- **Role**: Metadata search engine across historical detection events.
- **Query Types**: Target class, clothing colors, plate numbers, authorized faces, camera channels, and time windows.

## Module 9: Video Enhancement (`modules/video_enhancement`)
- **Status**: PLANNED (Phase 9)
- **Role**: Non-destructive image processing.
- **Techniques**: Low-light brightening, dehazing, edge sharpening, motion blur reduction, and super-resolution. Original video remains unmodified.

## Module 10: Video Forensics (`modules/video_forensics`, `engines/forensic_engine`)
- **Status**: PLANNED (Phase 10)
- **Role**: Cryptographic integrity and tamper analysis.
- **Checks**: SHA-256 chain of custody, frame discontinuity audit, duplicate frame detection, timestamp and compression anomaly inspection.

## Module 11: Camera Integration (`integrations`)
- **Status**: PLANNED (Phase 2)
- **Role**: Hardware communication layer.
- **Adapters**: ONVIF (Profile S/G/T), RTSP, Hikvision ISAPI, Dahua CGI, CP PLUS, and generic IP cameras.

## Module 12: Network Intelligence (`modules/network_intelligence`)
- **Status**: PLANNED (Phase 11)
- **Role**: Surveillance network diagnostics.
- **Tools**: Subnet IP scanner, MAC lookup, ONVIF discovery, RTSP port verification, latency/packet loss metrics.

## Module 13: Alarm Management (`modules/alarm_management`)
- **Status**: PLANNED (Phase 12)
- **Role**: Centralized incident routing.
- **Capabilities**: Real-time audio/visual alert triggers, acknowledgement workflows, operator assignment, and alarm logs.

## Module 14: Recording & Storage (`modules/recording_storage`, `engines/recording_engine`)
- **Status**: PLANNED (Phase 4, Phase 13)
- **Role**: Storage volume quota management, retention policies, and segmented video writing.

## Module 15: User Management (`modules/user_management`)
- **Status**: Core Models & Seeding COMPLETE (Phase 0)
- **Role**: RBAC access control, session authentication, and audit trails.

## Module 16: Reporting (`modules/reporting`)
- **Status**: PLANNED (Phase 14)
- **Role**: Security and operations reporting.
- **Formats**: PDF and Excel exports.

## Module 17: AI Model Management (`modules/model_management`)
- **Status**: PLANNED (Phase 5)
- **Role**: Neural network model registry, verification, confidence tuning, and device scheduling.
