"""
Recording and Storage Database Models.
Tracks continuous, scheduled, motion, and AI-triggered video segments,
storage volumes, keyframe indices, and cryptographic hashes.
"""

from sqlalchemy import Column, String, Integer, BigInteger, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database.models.base import Base


class StorageVolume(Base):
    __tablename__ = "storage_volumes"

    name = Column(String(100), nullable=False)
    mount_path = Column(String(255), nullable=False, unique=True)
    total_bytes = Column(BigInteger, default=0, nullable=False)
    used_bytes = Column(BigInteger, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    recordings = relationship("Recording", back_populates="volume")


class Recording(Base):
    __tablename__ = "recordings"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    volume_id = Column(String(36), ForeignKey("storage_volumes.id"), nullable=False, index=True)
    file_path = Column(String(500), nullable=False, unique=True)
    recording_type = Column(String(30), default="CONTINUOUS", nullable=False)  # CONTINUOUS, MOTION, AI_EVENT, MANUAL
    stream_type = Column(String(20), default="MAIN", nullable=False)  # MAIN, SUB
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True, index=True)
    file_size_bytes = Column(BigInteger, default=0, nullable=False)
    duration_sec = Column(Integer, default=0, nullable=False)
    sha256_hash = Column(String(64), nullable=True)  # Cryptographic chain of custody
    is_locked = Column(Boolean, default=False, nullable=False)  # Evidence protection flag

    volume = relationship("StorageVolume", back_populates="recordings")
    segments = relationship("RecordingSegment", back_populates="recording", cascade="all, delete-orphan")


class RecordingSegment(Base):
    __tablename__ = "recording_segments"

    recording_id = Column(String(36), ForeignKey("recordings.id", ondelete="CASCADE"), nullable=False, index=True)
    segment_index = Column(Integer, default=0, nullable=False)
    start_offset_sec = Column(Integer, default=0, nullable=False)
    duration_sec = Column(Integer, default=0, nullable=False)
    keyframe_index_path = Column(String(500), nullable=True)

    recording = relationship("Recording", back_populates="segments")


class RecordingSchedule(Base):
    __tablename__ = "recording_schedules"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time_str = Column(String(8), nullable=False)  # "00:00:00"
    end_time_str = Column(String(8), nullable=False)    # "23:59:59"
    mode = Column(String(30), default="CONTINUOUS", nullable=False)  # CONTINUOUS, MOTION, AI_EVENT
