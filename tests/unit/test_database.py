"""
Unit tests for Database Management and Core ORM Models.
"""

from database.database_manager import DatabaseManager
from database.models.users import Role, User, Permission
from database.models.devices import Site, Location, Device, DeviceChannel
from database.models.recordings import StorageVolume, Recording
from database.models.ai import AIModel, Detection


def test_database_health_check(test_db_manager: DatabaseManager):
    health = test_db_manager.health_check()
    assert health["status"] == "HEALTHY"
    assert health["backend"] == "sqlite"
    assert health["table_count"] > 0
    assert health["latency_ms"] >= 0.0


def test_role_and_user_creation(test_db_manager: DatabaseManager):
    with test_db_manager.get_session() as session:
        # Create Role
        role = Role(name="SecurityLead", description="Site security supervisor", is_system=False)
        session.add(role)
        session.flush()

        # Create User
        user = User(
            username="john_doe",
            email="john@cctv.local",
            password_hash="fakehash123",
            full_name="John Doe",
            role_id=role.id,
        )
        session.add(user)
        session.flush()

        assert user.id is not None
        assert len(user.id) == 36  # UUID string format
        assert user.role.name == "SecurityLead"


def test_device_and_channel_creation(test_db_manager: DatabaseManager):
    with test_db_manager.get_session() as session:
        site = Site(name="HQ Campus", code="HQ-01")
        session.add(site)
        session.flush()

        loc = Location(site_id=site.id, name="Main Gate", zone="Perimeter")
        session.add(loc)
        session.flush()

        dev = Device(
            site_id=site.id,
            location_id=loc.id,
            name="Front Gate PTZ",
            device_type="CAMERA",
            manufacturer="HIKVISION",
            ip_address="192.168.1.150",
            port=80,
            rtsp_port=554,
            is_online=True,
        )
        session.add(dev)
        session.flush()

        ch = DeviceChannel(
            device_id=dev.id,
            channel_number=1,
            name="Main Gate Cam 1",
            ptz_supported=True,
        )
        session.add(ch)
        session.flush()

        assert ch.id is not None
        assert ch.device.manufacturer == "HIKVISION"
        assert ch.device.site.code == "HQ-01"


def test_transaction_rollback_on_error(test_db_manager: DatabaseManager):
    try:
        with test_db_manager.get_session() as session:
            role = Role(name="TemporaryRole", description="Will fail", is_system=False)
            session.add(role)
            session.flush()
            # Intentionally cause an error
            raise ValueError("Forced test exception to verify rollback")
    except ValueError:
        pass

    with test_db_manager.get_session() as session:
        failed_role = session.query(Role).filter_by(name="TemporaryRole").first()
        assert failed_role is None
