"""
Device, Camera, Site, and Stream Topology Models.
Supports IP Cameras, NVRs, DVRs, ONVIF profiles, RTSP stream metadata,
device discovery logs, encrypted credentials, and stream health history.
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Float, Text, DateTime
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
    credentials = relationship("DeviceCredential", uselist=False, back_populates="device", cascade="all, delete-orphan")
    nvr_mappings = relationship("NVRChannelMapping", back_populates="nvr_device", cascade="all, delete-orphan")


class DeviceCredential(Base):
    """Secure encrypted credential storage for cameras and NVRs."""
    __tablename__ = "device_credentials"

    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    username = Column(String(100), nullable=False)
    encrypted_password = Column(Text, nullable=False)  # Encrypted with AES-256 via CredentialVault
    auth_type = Column(String(20), default="DIGEST", nullable=False)  # DIGEST, BASIC

    device = relationship("Device", back_populates="credentials")


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
    health_logs = relationship("StreamHealthLog", back_populates="channel", cascade="all, delete-orphan")


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


class DeviceDiscoveryRecord(Base):
    """Discovered network devices awaiting registration."""
    __tablename__ = "device_discovery_records"

    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=True, index=True)
    manufacturer = Column(String(100), default="Generic", nullable=False)
    model = Column(String(100), default="Unknown", nullable=False)
    firmware_version = Column(String(100), nullable=True)
    onvif_port = Column(Integer, default=80, nullable=False)
    rtsp_port = Column(Integer, default=554, nullable=False)
    discovery_method = Column(String(30), default="WS_DISCOVERY", nullable=False)  # WS_DISCOVERY, SUBNET_SCAN, MANUAL
    detected_capabilities = Column(Text, nullable=True)  # JSON summary
    is_added = Column(Boolean, default=False, nullable=False, index=True)


class StreamHealthLog(Base):
    """Historical telemetry log for stream quality, reconnects, and FPS."""
    __tablename__ = "stream_health_logs"

    channel_id = Column(String(36), ForeignKey("device_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(30), default="ONLINE", nullable=False)  # ONLINE, OFFLINE, RECONNECTING, ERROR
    fps_measured = Column(Float, default=0.0, nullable=False)
    bitrate_kbps = Column(Integer, default=0, nullable=False)
    latency_ms = Column(Float, default=0.0, nullable=False)
    dropped_frames = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    channel = relationship("DeviceChannel", back_populates="health_logs")


class NVRChannelMapping(Base):
    """Maps recorder channels to camera inputs for NVR/DVR multi-channel units."""
    __tablename__ = "nvr_channel_mappings"

    nvr_device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_number = Column(Integer, nullable=False)
    mapped_camera_name = Column(String(100), nullable=False)
    main_stream_url = Column(String(500), nullable=False)
    sub_stream_url = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    nvr_device = relationship("Device", back_populates="nvr_mappings")
