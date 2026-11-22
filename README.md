# CCTV AI Intelligence Platform

A professional-grade universal CCTV surveillance and video intelligence Windows desktop application engineered for high-performance offline multi-camera monitoring, playback, deep-learning video analytics, forensic analysis, and evidence management.

## Key Capabilities

- **High-Capacity Monitoring**: Supports up to 64 camera streams with adaptive layouts (1, 4, 9, 16, 25, 36, 64), substream/mainstream switching, and hardware-accelerated rendering.
- **Hardware-Accelerated AI**: Intel OpenVINO™ and ONNX Runtime acceleration with automatic Intel UHD/Iris Xe GPU offloading and CPU fallback.
- **Dual Pipeline Inference**: Unified detection and tracking framework servicing both live RTSP/ONVIF streams and historical playback recordings.
- **Computer Vision & Intelligence**: Real-time human intelligence, vehicle classification, ANPR, facial verification (authorized local database), and behavioral zone monitoring.
- **Digital Video Forensics & Enhancement**: Cryptographic SHA-256 chain of custody, frame discontinuity auditing, compression anomaly inspection, low-light enhancement, dehazing, and super-resolution.
- **Enterprise Storage & Privacy**: Zero cloud dependency. Complete local storage with PostgreSQL relational metadata engine and resilient SQLite WAL mode fallback.

## System Architecture

```
CCTV_AI_INTELLIGENCE/
├── app/               # Application bootstrap, state, configuration & entry points
├── core/              # Foundational logging, config, workers, hardware, events
├── modules/           # Functional domain UI & controller modules
├── engines/           # Low-level video, AI inference, tracking, forensics engines
├── integrations/      # Camera vendor adapters (ONVIF, RTSP, Hikvision, Dahua, CP PLUS)
├── database/          # PostgreSQL/SQLite models, repositories, and migrations
├── models/            # Neural network model descriptors & manifests
├── storage/           # Evidence, recordings, snapshots, and exports
├── tests/             # Unit, integration, and performance test suites
└── docs/              # Comprehensive technical documentation & registers
```

## Hardware Requirements

- **Operating System**: Windows 11 (64-bit)
- **Processor**: Intel® Core™ i5 / i7 / i9 (11th Gen or newer recommended; AVX2 support)
- **Graphics**: Intel® UHD Graphics 730 / Iris® Xe / Intel Arc™ or compatible GPU
- **RAM**: 16 GB minimum (32 GB recommended for 32+ channels)
- **Storage**: Fast NVMe SSD for OS & metadata; dedicated High-Endurance Surveillance HDD/NAS for video recordings
- **Media Engine**: Native FFmpeg 7+ / 9+ with DXVA2/D3D11VA hardware acceleration

## Quick Start

1. Install dependencies:
   ```powershell
   pip install -r requirements/base.txt
   ```
2. Verify hardware & environment:
   ```powershell
   python -m pytest tests/unit/test_hardware.py
   ```
3. Launch the platform:
   ```powershell
   python -m app.main
   ```

## Development & Testing

Run all automated smoke and unit tests:
```powershell
python -m pytest tests/ -v
```

## Documentation

Full architectural specifications and development registers are located in the `docs/` directory:
- [Architecture Blueprint](file:///c:/xampp/htdocs/cctv%20ai/docs/ARCHITECTURE.md)
- [Feature Register](file:///c:/xampp/htdocs/cctv%20ai/docs/FEATURE_REGISTER.md)
- [Changelog](file:///c:/xampp/htdocs/cctv%20ai/docs/CHANGELOG.md)
- [Decision Records](file:///c:/xampp/htdocs/cctv%20ai/docs/DECISION_RECORDS.md)
- [Development Status](file:///c:/xampp/htdocs/cctv%20ai/docs/DEVELOPMENT_STATUS.md)
