"""
Recording, Storage, Playback, and Video Export Database Models.
Tracks video segments, storage volumes, retention policies, cryptographic hashes,
synchronized playback sessions, and evidence export jobs.
"""

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, ForeignKey, DateTime, Float, Text
from sqlalchemy.orm import relationship
from database.models.base import Base


class StorageVolume(Base):
    __tablename__ = "storage_volumes"

    name = Column(String(100), nullable=False)
    mount_path = Column(String(255), nullable=False, unique=True)
    total_bytes = Column(BigInteger, default=0, nullable=False)
    used_bytes = Column(BigInteger, default=0, nullable=False)
    available_bytes = Column(BigInteger, default=0, nullable=False)
    warning_threshold_pct = Column(Float, default=90.0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    # Phase 13 Enterprise Storage extensions
    pool_id = Column(String(36), ForeignKey("storage_pools.id", ondelete="SET NULL"), nullable=True, index=True)
    volume_type = Column(String(20), default="LOCAL", nullable=False)  # LOCAL, RAID, NAS_SMB, NAS_NFS
    filesystem = Column(String(20), default="NTFS", nullable=False)    # NTFS, ReFS, SMB, NFS, etc.
    volume_status = Column(String(20), default="ONLINE", nullable=False)  # ONLINE, DEGRADED, OFFLINE, READ_ONLY, FULL
    is_failover_target = Column(Boolean, default=False, nullable=False)
    reserved_bytes = Column(BigInteger, default=0, nullable=False)
    health_score = Column(Float, default=100.0, nullable=False)

    pool = relationship("StoragePool", back_populates="volumes")
    recordings = relationship("Recording", back_populates="volume")
    events = relationship("StorageEvent", back_populates="volume", cascade="all, delete-orphan")


class StorageEvent(Base):
    __tablename__ = "storage_events"

    volume_id = Column(String(36), ForeignKey("storage_volumes.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # WARNING_LOW_DISK, QUOTA_EXCEEDED, PRUNED_OLD_RECORDINGS, DISK_ERROR
    severity = Column(String(20), default="WARNING", nullable=False)  # INFO, WARNING, CRITICAL
    message = Column(String(255), nullable=False)
    bytes_freed = Column(BigInteger, default=0, nullable=False)

    volume = relationship("StorageVolume", back_populates="events")


class Recording(Base):
    __tablename__ = "recordings"

    channel_id = Column(String(64), nullable=False, index=True)
    volume_id = Column(String(36), ForeignKey("storage_volumes.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False, unique=True)
    recording_type = Column(String(30), default="CONTINUOUS", nullable=False)  # CONTINUOUS, MOTION, AI_EVENT, MANUAL
    stream_type = Column(String(20), default="MAIN", nullable=False)  # MAIN, SUB
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True, index=True)
    file_size_bytes = Column(BigInteger, default=0, nullable=False)
    duration_sec = Column(Integer, default=0, nullable=False)
    codec = Column(String(20), default="H264", nullable=False)
    resolution_width = Column(Integer, default=1920, nullable=False)
    resolution_height = Column(Integer, default=1080, nullable=False)
    fps = Column(Float, default=25.0, nullable=False)
    bitrate_kbps = Column(Integer, default=4096, nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False, index=True)  # ACTIVE, COMPLETED, CORRUPTED, RECOVERED
    sha256_hash = Column(String(64), nullable=True)  # Cryptographic chain of custody
    is_locked = Column(Boolean, default=False, nullable=False, index=True)  # Evidence protection flag (never auto-deleted)

    volume = relationship("StorageVolume", back_populates="recordings")
    segments = relationship("RecordingSegment", back_populates="recording", cascade="all, delete-orphan")
    health_logs = relationship("RecordingHealthLog", back_populates="recording", cascade="all, delete-orphan")


class RecordingSegment(Base):
    __tablename__ = "recording_segments"

    recording_id = Column(String(36), ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index = Column(Integer, default=0, nullable=False)
    file_path = Column(String(500), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True, index=True)
    duration_sec = Column(Integer, default=0, nullable=False)
    file_size_bytes = Column(BigInteger, default=0, nullable=False)
    sha256_hash = Column(String(64), nullable=True)
    keyframe_index_path = Column(String(500), nullable=True)

    recording = relationship("Recording", back_populates="segments")


class RecordingSchedule(Base):
    __tablename__ = "recording_schedules"

    channel_id = Column(String(64), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time_str = Column(String(8), nullable=False)  # "00:00:00"
    end_time_str = Column(String(8), nullable=False)    # "23:59:59"
    mode = Column(String(30), default="CONTINUOUS", nullable=False)  # CONTINUOUS, MOTION, AI_EVENT


class RecordingHealthLog(Base):
    __tablename__ = "recording_health_logs"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    recording_id = Column(String(36), ForeignKey("recordings.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(String(30), default="NORMAL", nullable=False)  # NORMAL, WRITE_SLOW, DISK_FULL, DROPPED_FRAMES, ERROR
    write_speed_mbps = Column(Float, default=0.0, nullable=False)
    dropped_frames = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    recording = relationship("Recording", back_populates="health_logs")


class PlaybackSession(Base):
    __tablename__ = "playback_sessions"

    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    channels_json = Column(Text, nullable=False)  # Serialized list of channel IDs
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    master_clock_timestamp = Column(DateTime(timezone=True), nullable=True)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    channel_id = Column(String(64), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)
    destination_path = Column(String(500), nullable=False)
    file_size_bytes = Column(BigInteger, default=0, nullable=False)
    sha256_hash = Column(String(64), nullable=True)
    status = Column(String(20), default="QUEUED", nullable=False, index=True)  # QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED
    progress_pct = Column(Float, default=0.0, nullable=False)
    is_evidence = Column(Boolean, default=False, nullable=False)
    created_by = Column(String(36), nullable=True)
    error_message = Column(Text, nullable=True)
