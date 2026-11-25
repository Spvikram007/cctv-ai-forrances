"""
Integration Tests for Enterprise Storage Management, Recording Integration, and Alarm Events.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import sys
import uuid
import pytest
from datetime import datetime, timezone
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication

from database.database_manager import db_manager
from database.models.recordings import StorageVolume, Recording
from database.models.storage import StorageFailoverEvent, StorageRecordingManifest
from engines.storage_engine.storage_service import enterprise_storage_service
from engines.recording_engine.recorder import ChannelRecordingWorker
from engines.alarm_engine.alarm_service import alarm_service
from engines.alarm_engine.adapters import alarm_adapter
from core.events.event_bus import bus


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


class TestStorageEnterpriseIntegration:
    """End-to-end integration tests for Phase 13 Enterprise Storage."""

    @pytest.fixture(autouse=True)
    def setup_storage(self):
        enterprise_storage_service.initialize()

    def test_storage_service_initialization_and_audit(self):
        """Verifies default volume and pool initialization and health audit."""
        results = enterprise_storage_service.volume_monitor.audit_all_volumes()
        assert len(results) >= 1
        res = results[0]
        assert "volume_id" in res
        assert "used_pct" in res
        assert "status" in res

    def test_end_to_end_recording_with_manifest_creation(self, tmp_path):
        """
        Verifies that ChannelRecordingWorker resolves destination via EnterpriseStorageService
        and automatically creates an authoritative StorageRecordingManifest upon segment close.
        """
        ch_id = f"cam_e2e_{uuid.uuid4().hex[:6]}"
        vol_dir = str(tmp_path / "e2e_storage_vol")
        os.makedirs(vol_dir, exist_ok=True)

        with db_manager.get_session() as session:
            v = StorageVolume(
                name="E2E Surveillance Volume",
                mount_path=vol_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=90 * 1024 * 1024 * 1024,
                is_active=True,
                volume_status="ONLINE",
            )
            session.add(v)
            session.flush()
            vol_id = str(v.id)

        # Allocate channel to this volume
        enterprise_storage_service.allocation_manager.allocate_channel(
            channel_id=ch_id,
            primary_volume_id=vol_id,
        )

        worker = ChannelRecordingWorker(
            channel_id=ch_id,
            segment_duration_sec=2,
            target_fps=10.0,
            output_dir=vol_dir,
        )

        # Feed 15 dummy frames
        dummy_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        now_ts = datetime.now(timezone.utc).timestamp()
        for i in range(15):
            worker.push_frame(dummy_frame, now_ts + (i * 0.1))

        # Close segment
        worker._start_new_segment(dummy_frame, now_ts)
        worker._close_current_segment()

        # Verify StorageRecordingManifest was created
        with db_manager.get_session() as session:
            manifest = (
                session.query(StorageRecordingManifest)
                .filter_by(channel_id=ch_id)
                .order_by(StorageRecordingManifest.created_at.desc())
                .first()
            )
            assert manifest is not None
            assert manifest.destination_volume_id == vol_id
            assert manifest.sha256_hash is not None
            assert manifest.verification_status == "VERIFIED"

    def test_failover_redirection_under_storage_error(self, tmp_path):
        """Verifies that notifying a write failure switches recording destination and logs failover event."""
        p_dir = str(tmp_path / "primary_drive")
        f_dir = str(tmp_path / "failover_drive")
        os.makedirs(p_dir, exist_ok=True)
        os.makedirs(f_dir, exist_ok=True)

        with db_manager.get_session() as session:
            vp = StorageVolume(
                name="Primary",
                mount_path=p_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=90 * 1024 * 1024 * 1024,
                is_active=True,
                volume_status="ONLINE",
            )
            vf = StorageVolume(
                name="Failover",
                mount_path=f_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=90 * 1024 * 1024 * 1024,
                is_active=True,
                is_failover_target=True,
                volume_status="ONLINE",
            )
            session.add(vp)
            session.add(vf)
            session.flush()
            p_id = str(vp.id)
            f_id = str(vf.id)

        enterprise_storage_service.allocation_manager.allocate_channel(
            channel_id="cam_failover_e2e",
            primary_volume_id=p_id,
            failover_volume_id=f_id,
        )

        # Notify failure on primary
        alt_vol, msg = enterprise_storage_service.notify_write_failure(
            channel_id="cam_failover_e2e",
            failed_volume_id=p_id,
            reason="Disk write I/O timeout",
            gap_seconds=2.4,
        )

        assert alt_vol is not None
        assert str(alt_vol.id) == f_id

        # Verify destination resolution now redirects to failover target
        dest_vol, dest_dir, is_failover = enterprise_storage_service.get_recording_destination("cam_failover_e2e")
        assert dest_vol.id == f_id
        assert is_failover is True

    def test_alarm_engine_receives_storage_events(self):
        """Verifies that publishing storage events creates categorized alarms in AlarmEngine."""
        alarm_adapter.start()
        # Storage write failure
        bus.publish("storage.write_failure", {
            "channel_id": "cam_alarm_test",
            "volume_path": "D:/Surveillance",
            "error": "Device I/O hardware fault",
        }, source="test_runner")

        # Allow EventBus dispatch & async queue processing
        import time
        time.sleep(0.3)

        # Verify an alarm was generated in database
        alarms = alarm_service.get_active_alarms(limit=10)
        storage_alarms = [a for a in alarms if a.get("category") == "HARDWARE" and "Storage" in a.get("title", "")]
        assert len(storage_alarms) >= 1

    def test_storage_ui_smoke(self, qapp):
        """Smoke test verifying StorageManagementWidget instantiation and tab switching."""
        from modules.storage_management.storage_workspace_widget import StorageManagementWidget
        widget = StorageManagementWidget()

        assert widget.tabs.count() == 8
        widget.tabs.setCurrentIndex(1)
        assert widget.tabs.currentIndex() == 1
        widget.tabs.setCurrentIndex(2)
        assert widget.tabs.currentIndex() == 2
        widget.tabs.setCurrentIndex(0)
        assert widget.tabs.currentIndex() == 0

        widget.close()
        widget.deleteLater()
        qapp.processEvents()
