"""
Enterprise Storage, RAID, NAS, Failover, and Multi-Tier Archival Database Models.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import relationship
from database.models.base import Base


class StoragePool(Base):
    """Logical grouping of storage volumes into operational tiers (Hot, Warm, Cold, Archive)."""
    __tablename__ = "storage_pools"

    name = Column(String(100), nullable=False, unique=True)
    pool_tier = Column(String(20), nullable=False, default="HOT", index=True)
    description = Column(Text, nullable=True)
    min_free_space_gb = Column(Float, default=20.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    volumes = relationship("StorageVolume", back_populates="pool")
    policies = relationship("StoragePolicy", back_populates="pool", cascade="all, delete-orphan")
    allocations = relationship("StorageAllocation", back_populates="pool", cascade="all, delete-orphan")


class StorageDevice(Base):
    """Physical storage device (SATA, NVMe, SAS, USB disk) backing volumes or arrays."""
    __tablename__ = "storage_devices"

    volume_id = Column(String(36), ForeignKey("storage_volumes.id", ondelete="SET NULL"), nullable=True, index=True)
    device_path = Column(String(255), nullable=False, index=True)  # e.g. \\.\PhysicalDrive0
    model = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True, index=True)
    bus_type = Column(String(20), default="SATA", nullable=False)  # NVMe, SATA, SAS, USB, SCSI
    size_bytes = Column(BigInteger, default=0, nullable=False)
    smart_status = Column(String(20), default="HEALTHY", nullable=False)  # HEALTHY, WARNING, FAILING, UNKNOWN
    temperature_c = Column(Float, nullable=True)
    power_on_hours = Column(Integer, nullable=True)
    health_score = Column(Float, default=100.0, nullable=False)
    is_healthy = Column(Boolean, default=True, nullable=False)
    extra_metadata = Column(Text, nullable=True)  # JSON-encoded extra telemetry


class StoragePolicy(Base):
    """Storage allocation, safety reserves, retention periods, and failover policy."""
    __tablename__ = "storage_policies"

    name = Column(String(100), nullable=False)
    pool_id = Column(String(36), ForeignKey("storage_pools.id", ondelete="CASCADE"), nullable=True, index=True)
    warning_threshold_pct = Column(Float, default=85.0, nullable=False)
    critical_threshold_pct = Column(Float, default=95.0, nullable=False)
    min_free_gb = Column(Float, default=10.0, nullable=False)
    retention_days = Column(Integer, default=30, nullable=False)
    failover_enabled = Column(Boolean, default=True, nullable=False)
    failover_pool_id = Column(String(36), nullable=True)
    archival_enabled = Column(Boolean, default=False, nullable=False)
    archival_age_days = Column(Integer, default=14, nullable=False)

    pool = relationship("StoragePool", back_populates="policies")


class StorageAllocation(Base):
    """Maps cameras / channels or sites to primary and failover storage destinations."""
    __tablename__ = "storage_allocations"

    channel_id = Column(String(64), nullable=False, index=True)
    pool_id = Column(String(36), ForeignKey("storage_pools.id", ondelete="CASCADE"), nullable=False, index=True)
    primary_volume_id = Column(String(36), ForeignKey("storage_volumes.id"), nullable=False, index=True)
    failover_volume_id = Column(String(36), ForeignKey("storage_volumes.id"), nullable=True, index=True)
    quota_bytes = Column(BigInteger, default=0, nullable=False)  # 0 = unlimited
    priority = Column(String(20), default="NORMAL", nullable=False)  # CRITICAL, HIGH, NORMAL, LOW

    pool = relationship("StoragePool", back_populates="allocations")


class StorageHealthHistory(Base):
    """Historical time-series log of volume latency, throughput, and capacity."""
    __tablename__ = "storage_health_history"

    volume_id = Column(String(36), ForeignKey("storage_volumes.id", ondelete="CASCADE"), nullable=False, index=True)
    measured_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    read_latency_ms = Column(Float, default=0.0, nullable=False)
    write_latency_ms = Column(Float, default=0.0, nullable=False)
    throughput_mbps = Column(Float, default=0.0, nullable=False)
    used_pct = Column(Float, default=0.0, nullable=False)
    free_gb = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="HEALTHY", nullable=False)
    error_details = Column(Text, nullable=True)


class StorageFailoverEvent(Base):
    """Audit record of storage failover incidents, alternate redirection, and failback."""
    __tablename__ = "storage_failover_events"

    channel_id = Column(String(64), nullable=False, index=True)
    primary_volume_id = Column(String(36), ForeignKey("storage_volumes.id"), nullable=False, index=True)
    failover_volume_id = Column(String(36), ForeignKey("storage_volumes.id"), nullable=False, index=True)
    triggered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    failback_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String(255), nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False, index=True)  # ACTIVE, RECOVERED, FAILED_BACK
    gap_seconds = Column(Float, default=0.0, nullable=False)
    segments_redirected = Column(Integer, default=0, nullable=False)


class StorageRecordingManifest(Base):
    """Cryptographic manifest per recording segment guaranteeing end-to-end provenance and continuity."""
    __tablename__ = "storage_recording_manifests"

    recording_id = Column(String(36), nullable=True, index=True)
    segment_id = Column(String(36), nullable=True, index=True)
    channel_id = Column(String(64), nullable=False, index=True)
    stream_id = Column(String(20), default="MAIN", nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True, index=True)
    destination_volume_id = Column(String(36), nullable=False, index=True)
    file_path = Column(String(500), nullable=False, index=True)
    sha256_hash = Column(String(64), nullable=True, index=True)
    file_size_bytes = Column(BigInteger, default=0, nullable=False)
    duration_sec = Column(Integer, default=0, nullable=False)
    is_failover = Column(Boolean, default=False, nullable=False, index=True)
    failover_event_id = Column(String(36), nullable=True)
    verification_status = Column(String(20), default="VERIFIED", nullable=False)  # VERIFIED, UNVERIFIED, CORRUPT


class StorageArchivalJob(Base):
    """Lifecycle multi-tier archival migration batch jobs."""
    __tablename__ = "storage_archival_jobs"

    source_volume_id = Column(String(36), nullable=False, index=True)
    target_volume_id = Column(String(36), nullable=False, index=True)
    target_tier = Column(String(20), default="WARM", nullable=False)  # WARM, COLD
    status = Column(String(20), default="QUEUED", nullable=False, index=True)  # QUEUED, IN_PROGRESS, COMPLETED, FAILED, CANCELLED
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_files = Column(Integer, default=0, nullable=False)
    files_transferred = Column(Integer, default=0, nullable=False)
    bytes_transferred = Column(BigInteger, default=0, nullable=False)
    verification_failed_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    copies = relationship("StorageArchivalCopy", back_populates="job", cascade="all, delete-orphan")


class StorageArchivalCopy(Base):
    """Tracks verified secondary/cold archival copies of recording segments."""
    __tablename__ = "storage_archival_copies"

    recording_id = Column(String(36), nullable=False, index=True)
    segment_id = Column(String(36), nullable=True, index=True)
    job_id = Column(String(36), ForeignKey("storage_archival_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    target_volume_id = Column(String(36), nullable=False, index=True)
    archive_path = Column(String(500), nullable=False)
    tier = Column(String(20), default="WARM", nullable=False)
    sha256_hash = Column(String(64), nullable=False)
    verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    status = Column(String(20), default="VERIFIED", nullable=False)

    job = relationship("StorageArchivalJob", back_populates="copies")


class NASConnection(Base):
    """Secure profile for Network-Attached Storage connections (SMB/CIFS and NFS)."""
    __tablename__ = "nas_connections"

    name = Column(String(100), nullable=False, unique=True)
    protocol = Column(String(10), default="SMB", nullable=False)  # SMB, NFS
    host = Column(String(255), nullable=False)
    share_name = Column(String(255), nullable=False)
    mount_point = Column(String(255), nullable=False)
    username = Column(String(100), nullable=True)
    encrypted_password_envelope = Column(Text, nullable=True)  # DPAPI encrypted
    status = Column(String(20), default="DISCONNECTED", nullable=False)  # CONNECTED, DISCONNECTED, AUTH_FAILED, DEGRADED
    last_latency_ms = Column(Float, default=0.0, nullable=False)
    last_connected_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
