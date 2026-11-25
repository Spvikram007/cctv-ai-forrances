"""
Configuration Management Module for CCTV AI Intelligence Platform.
Uses Pydantic Settings V2 with .env file support and strong type validation.
"""

from pathlib import Path
from typing import Optional, Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration supporting PostgreSQL with resilient SQLite WAL fallback."""
    engine_type: Literal["sqlite", "postgresql"] = Field(
        default="sqlite",
        description="Active database backend. Automatically falls back to sqlite if postgresql is unavailable."
    )
    sqlite_path: str = Field(
        default="storage/cctv_metadata.db",
        description="Path to SQLite metadata database file."
    )
    postgresql_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL DSN e.g., postgresql+psycopg2://cctv_admin:pass@localhost:5432/cctv_db"
    )
    pool_size: int = Field(default=10, ge=1, le=50)
    max_overflow: int = Field(default=20, ge=0, le=50)
    pool_timeout: int = Field(default=30, ge=5, le=120)
    echo_sql: bool = Field(default=False)

    model_config = SettingsConfigDict(env_prefix="CCTV_DB_", extra="ignore")


class StorageSettings(BaseSettings):
    """Storage directories and retention policies."""
    recordings_dir: str = Field(default="storage/recordings")
    snapshots_dir: str = Field(default="storage/snapshots")
    evidence_dir: str = Field(default="storage/evidence")
    exports_dir: str = Field(default="storage/exports")
    enhanced_dir: str = Field(default="storage/enhanced")
    forensics_dir: str = Field(default="storage/forensics")
    backups_dir: str = Field(default="storage/backups")
    logs_dir: str = Field(default="storage/logs")
    retention_days: int = Field(default=30, ge=1)
    min_free_space_gb: float = Field(default=10.0, ge=1.0)

    model_config = SettingsConfigDict(env_prefix="CCTV_STORAGE_", extra="ignore")


class VideoSettings(BaseSettings):
    """Video engine and decoding parameters."""
    max_channels: int = Field(default=64, ge=1, le=128)
    default_fps: int = Field(default=25, ge=1, le=60)
    hardware_accel: str = Field(default="d3d11va", description="Windows hardware decode accelerator (d3d11va/dxva2)")
    rtsp_transport: Literal["tcp", "udp"] = Field(default="tcp")
    stream_buffer_frames: int = Field(default=30, ge=5, le=120)
    reconnect_interval_sec: int = Field(default=5, ge=1, le=60)

    model_config = SettingsConfigDict(env_prefix="CCTV_VIDEO_", extra="ignore")


class AISettings(BaseSettings):
    """AI engine and Intel OpenVINO / ONNX runtime configuration."""
    enabled: bool = Field(default=True)
    preferred_device: str = Field(default="AUTO", description="Target device: 'AUTO', 'CPU', 'GPU'")
    enable_openvino: bool = Field(default=True)
    enable_onnx: bool = Field(default=True)
    detection_confidence_threshold: float = Field(default=0.50, ge=0.1, le=1.0)
    iou_threshold: float = Field(default=0.45, ge=0.1, le=1.0)
    enable_substream_inference: bool = Field(default=True)
    max_concurrent_ai_streams: int = Field(default=16, ge=1, le=64)

    model_config = SettingsConfigDict(env_prefix="CCTV_AI_", extra="ignore")


class SecuritySettings(BaseSettings):
    """Local security, session management, and credential protection."""
    jwt_secret_key: str = Field(default="cctv-local-offline-secret-key-change-in-prod-2026")
    session_timeout_minutes: int = Field(default=120, ge=5)
    audit_logging_enabled: bool = Field(default=True)
    export_watermarking: bool = Field(default=True)

    model_config = SettingsConfigDict(env_prefix="CCTV_SEC_", extra="ignore")


class PlatformSettings(BaseSettings):
    """Master application configuration container."""
    app_name: str = "CCTV AI Intelligence Platform"
    app_version: str = "1.0.0-alpha"
    environment: Literal["development", "production", "testing"] = "development"
    debug: bool = False

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    ai: AISettings = Field(default_factory=AISettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def ensure_directories(self) -> None:
        """Ensures all configured storage folders exist on the local file system."""
        for path_attr in [
            self.storage.recordings_dir,
            self.storage.snapshots_dir,
            self.storage.evidence_dir,
            self.storage.exports_dir,
            self.storage.backups_dir,
            self.storage.logs_dir,
        ]:
            Path(path_attr).mkdir(parents=True, exist_ok=True)


# Global singleton settings instance
settings = PlatformSettings()
