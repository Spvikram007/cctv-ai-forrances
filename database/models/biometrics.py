"""
Authorized Face Intelligence and Automatic Number Plate Recognition (ANPR) Database Models.
Implements privacy-preserving encrypted biometric templates, authorized enrollments,
human verification workflows, license plate detections, vehicle history, and biometric audit logs.
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database.models.base import Base


class FaceIdentity(Base):
    __tablename__ = "face_identities"

    name = Column(String(100), nullable=False, index=True)
    identity_code = Column(String(50), unique=True, nullable=False, index=True)  # Employee ID, Badge, etc.
    category = Column(String(50), default="AUTHORIZED_STAFF", nullable=False, index=True)  # AUTHORIZED_STAFF, VIP, WATCHLIST_ALERT
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    department = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    templates = relationship("FaceTemplate", back_populates="identity", cascade="all, delete-orphan")
    enrollments = relationship("FaceEnrollment", back_populates="identity", cascade="all, delete-orphan")
    match_events = relationship("FaceMatchEvent", back_populates="identity")


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    identity_id = Column(String(36), ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False, index=True)
    encrypted_template = Column(Text, nullable=False)  # AES-256-GCM encrypted 512-d embedding
    algorithm = Column(String(50), default="MobileFaceNet-512", nullable=False)
    vector_dim = Column(Integer, default=512, nullable=False)
    quality_score = Column(Float, default=1.0, nullable=False)  # Quality & illumination score
    is_revoked = Column(Boolean, default=False, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revocation_reason = Column(String(255), nullable=True)

    identity = relationship("FaceIdentity", back_populates="templates")


class FaceEnrollment(Base):
    __tablename__ = "face_enrollments"

    identity_id = Column(String(36), ForeignKey("face_identities.id", ondelete="CASCADE"), nullable=False, index=True)
    enrolled_by_user_id = Column(String(36), nullable=True, index=True)
    status = Column(String(30), default="APPROVED", nullable=False, index=True)  # PENDING, APPROVED, REJECTED, EXPIRED, REVOKED
    authorization_ref = Column(String(100), nullable=True)  # Consent form / policy reference
    valid_until = Column(DateTime(timezone=True), nullable=True)

    identity = relationship("FaceIdentity", back_populates="enrollments")


class FaceMatchEvent(Base):
    __tablename__ = "face_match_events"

    channel_id = Column(String(64), nullable=False, index=True)
    identity_id = Column(String(36), ForeignKey("face_identities.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_name = Column(String(100), nullable=False, index=True)
    category = Column(String(50), default="AUTHORIZED_STAFF", nullable=False, index=True)
    similarity_score = Column(Float, nullable=False)  # Cosine similarity score [0.0, 1.0]
    threshold_applied = Column(Float, default=0.65, nullable=False)
    snapshot_path = Column(String(500), nullable=True)
    face_bbox_json = Column(Text, nullable=True)  # Normalized [x, y, w, h]
    is_verified = Column(Boolean, default=False, nullable=False, index=True)  # Human verification status
    verified_by_user_id = Column(String(36), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    identity = relationship("FaceIdentity", back_populates="match_events")


class ANPRDetection(Base):
    __tablename__ = "anpr_detections"

    channel_id = Column(String(64), nullable=False, index=True)
    track_id = Column(Integer, nullable=True, index=True)
    vehicle_class = Column(String(50), default="car", nullable=False, index=True)
    plate_text = Column(String(30), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    character_confidences_json = Column(Text, nullable=True)  # List of per-char confidences
    plate_format = Column(String(30), default="STANDARD", nullable=False)
    requires_manual_review = Column(Boolean, default=False, nullable=False, index=True)
    plate_crop_path = Column(String(500), nullable=True)
    vehicle_snapshot_path = Column(String(500), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)


class ANPRPlateRecord(Base):
    __tablename__ = "anpr_plate_records"

    plate_text_normalized = Column(String(30), unique=True, nullable=False, index=True)
    vehicle_class = Column(String(50), default="car", nullable=False)
    first_seen = Column(DateTime(timezone=True), nullable=False, index=True)
    last_seen = Column(DateTime(timezone=True), nullable=False, index=True)
    total_sightings = Column(Integer, default=1, nullable=False)
    is_watchlist = Column(Boolean, default=False, nullable=False, index=True)
    watchlist_category = Column(String(50), nullable=True)  # STOLEN, VIP, BANNED, VISITOR
    owner_or_notes = Column(String(255), nullable=True)


class VehicleEvent(Base):
    __tablename__ = "vehicle_events"

    channel_id = Column(String(64), nullable=False, index=True)
    plate_text = Column(String(30), nullable=False, index=True)
    event_type = Column(String(50), default="PLATE_DETECTED", nullable=False, index=True)  # PLATE_DETECTED, WATCHLIST_ALERT
    severity = Column(String(20), default="INFO", nullable=False)
    confidence = Column(Float, nullable=False)
    track_id = Column(Integer, nullable=True)
    details_json = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)


class BiometricAuditLog(Base):
    __tablename__ = "biometric_audit_logs"

    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)  # ENROLL, REVOKE, MATCH_QUERY, TEMPLATE_DECRYPT
    identity_id = Column(String(36), nullable=True, index=True)
    template_id = Column(String(36), nullable=True)
    details_json = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
