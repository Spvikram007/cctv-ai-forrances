"""
AI Intelligence, Object Detection, Tracking, and Analytics Models.
Stores model registries, detections, tracked objects, and security event triggers.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from database.models.base import Base


class AIModel(Base):
    __tablename__ = "ai_models"

    name = Column(String(100), unique=True, nullable=False, index=True)
    task_type = Column(String(50), nullable=False, index=True)  # OBJECT_DETECTION, FACE, ANPR, BEHAVIOUR
    framework = Column(String(30), default="OPENVINO", nullable=False)  # OPENVINO, ONNX, TORCH
    description = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    versions = relationship("AIModelVersion", back_populates="model", cascade="all, delete-orphan")


class AIModelVersion(Base):
    __tablename__ = "ai_model_versions"

    model_id = Column(String(36), ForeignKey("ai_models.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(30), nullable=False)
    file_path = Column(String(500), nullable=False)
    weights_sha256 = Column(String(64), nullable=True)
    target_device = Column(String(20), default="AUTO", nullable=False)  # AUTO, CPU, GPU
    input_width = Column(Integer, default=640, nullable=False)
    input_height = Column(Integer, default=640, nullable=False)
    classes_json = Column(Text, nullable=False)  # Serialized list of class labels
    is_default = Column(Boolean, default=False, nullable=False)

    model = relationship("AIModel", back_populates="versions")
    jobs = relationship("AIJob", back_populates="model_version")


class AIJob(Base):
    __tablename__ = "ai_jobs"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    model_version_id = Column(String(36), ForeignKey("ai_model_versions.id"), nullable=False, index=True)
    status = Column(String(20), default="STOPPED", nullable=False)  # RUNNING, STOPPED, ERROR
    target_device = Column(String(20), default="AUTO", nullable=False)
    inference_fps = Column(Float, default=0.0, nullable=False)
    total_inferences = Column(Integer, default=0, nullable=False)

    model_version = relationship("AIModelVersion", back_populates="jobs")


class Detection(Base):
    __tablename__ = "detections"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    class_name = Column(String(50), nullable=False, index=True)  # person, car, truck, etc.
    confidence = Column(Float, nullable=False)
    bbox_x = Column(Float, nullable=False)
    bbox_y = Column(Float, nullable=False)
    bbox_w = Column(Float, nullable=False)
    bbox_h = Column(Float, nullable=False)
    track_id = Column(Integer, nullable=True, index=True)
    attributes_json = Column(Text, nullable=True)  # color, clothing, plate, etc.


class ObjectTrack(Base):
    __tablename__ = "object_tracks"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id = Column(Integer, nullable=False, index=True)
    class_name = Column(String(50), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    trajectory_json = Column(Text, nullable=True)


class AIEvent(Base):
    __tablename__ = "ai_events"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # INTRUSION, LINE_CROSS, LOITER, FACE_MATCH
    severity = Column(String(20), default="WARNING", nullable=False)  # INFO, WARNING, CRITICAL
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    rule_name = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=True)
    snapshot_path = Column(String(500), nullable=True)
    is_acknowledged = Column(Boolean, default=False, nullable=False)
