"""
Device, Camera, Site, and Stream Topology Models.
Supports IP Cameras, NVRs, DVRs, ONVIF profiles, and RTSP stream metadata.
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from database.models.base import Base


class Site(Base):
    __tablename__ = "sites"

    name = Column(String(100), nullable=False, index=True)
    code = Column(String(30), unique=True, nullable=False, index=True)
    description = Column(String(255), nullable=True)
    address = Column(String(255), nullable=True)

    locations = relationship("Location", back_populates="site", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="site")


class Location(Base):
    __tablename__ = "locations"

    site_id = Column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    floor = Column(String(50), nullable=True)
    zone = Column(String(100), nullable=True)

    site = relationship("Site", back_populates="locations")
    devices = relationship("Device", back_populates="location")


class Device(Base):
    __tablename__ = "devices"

    site_id = Column(String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True, index=True)
    location_id = Column(String(36), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    device_type = Column(String(30), default="CAMERA", nullable=False)  # CAMERA, NVR, DVR
    manufacturer = Column(String(50), default="GENERIC_ONVIF", nullable=False)  # HIKVISION, DAHUA, CP_PLUS, ONVIF, RTSP
    ip_address = Column(String(45), nullable=False, index=True)
    port = Column(Integer, default=80, nullable=False)
    rtsp_port = Column(Integer, default=554, nullable=False)
    onvif_port = Column(Integer, default=80, nullable=True)
    mac_address = Column(String(17), nullable=True)
    total_channels = Column(Integer, default=1, nullable=False)
    is_online = Column(Boolean, default=False, nullable=False, index=True)

    site = relationship("Site", back_populates="devices")
    location = relationship("Location", back_populates="devices")
    channels = relationship("DeviceChannel", back_populates="device", cascade="all, delete-orphan")
    capabilities = relationship("DeviceCapability", uselist=False, back_populates="device", cascade="all, delete-orphan")
    status = relationship("DeviceStatus", uselist=False, back_populates="device", cascade="all, delete-orphan")


class DeviceChannel(Base):
    __tablename__ = "device_channels"

    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_number = Column(Integer, default=1, nullable=False)
    name = Column(String(100), nullable=False)
    ptz_supported = Column(Boolean, default=False, nullable=False)
    audio_supported = Column(Boolean, default=False, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)

    device = relationship("Device", back_populates="channels")
    stream_profiles = relationship("StreamProfile", back_populates="channel", cascade="all, delete-orphan")


class StreamProfile(Base):
    __tablename__ = "stream_profiles"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_type = Column(String(20), default="MAIN", nullable=False)  # MAIN, SUB
    rtsp_url = Column(String(500), nullable=False)
    codec = Column(String(20), default="H264", nullable=False)
    resolution_width = Column(Integer, default=1920, nullable=False)
    resolution_height = Column(Integer, default=1080, nullable=False)
    target_fps = Column(Integer, default=25, nullable=False)
    bitrate_kbps = Column(Integer, default=4096, nullable=False)

    channel = relationship("DeviceChannel", back_populates="stream_profiles")


class DeviceCapability(Base):
    __tablename__ = "device_capabilities"

    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    has_ptz = Column(Boolean, default=False, nullable=False)
    has_audio = Column(Boolean, default=False, nullable=False)
    onvif_profile_s = Column(Boolean, default=False, nullable=False)
    onvif_profile_g = Column(Boolean, default=False, nullable=False)
    onvif_profile_t = Column(Boolean, default=False, nullable=False)
    isapi_supported = Column(Boolean, default=False, nullable=False)
    dahua_cgi_supported = Column(Boolean, default=False, nullable=False)

    device = relationship("Device", back_populates="capabilities")


class DeviceStatus(Base):
    __tablename__ = "device_status"

    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    latency_ms = Column(Float, default=0.0, nullable=False)
    packet_loss_pct = Column(Float, default=0.0, nullable=False)
    fps_actual = Column(Float, default=0.0, nullable=False)
    bitrate_actual_kbps = Column(Integer, default=0, nullable=False)
    last_seen = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)

    device = relationship("Device", back_populates="status")
