"""
Unit Tests for Local, RAID, and NAS Storage Adapters.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import pytest
from pathlib import Path

from engines.storage_engine.enums import (
    StorageType,
    RAIDLevel,
    RAIDStatus,
    HealthStatus,
    TelemetrySource,
)
from engines.storage_engine.adapters.local import LocalStorageAdapter
from engines.storage_engine.adapters.raid import RAIDMonitoringAdapter, RAIDArrayInfo
from engines.storage_engine.adapters.nas import NASStorageAdapter
from core.security.crypto import credential_vault


class TestLocalStorageAdapter:
    """Validates LocalStorageAdapter functionality and security controls."""

    @pytest.fixture
    def local_adapter(self):
        return LocalStorageAdapter()

    def test_local_adapter_type(self, local_adapter):
        assert local_adapter.adapter_type == StorageType.LOCAL

    def test_local_adapter_metrics(self, local_adapter, tmp_path):
        metrics = local_adapter.get_metrics(str(tmp_path))
        assert metrics.total_bytes > 0
        assert metrics.free_bytes > 0
        assert 0.0 <= metrics.used_percent <= 100.0
        assert metrics.total_gb > 0.0
        assert metrics.free_gb > 0.0
        assert metrics.status in [HealthStatus.HEALTHY, HealthStatus.WARNING]

    def test_local_adapter_read_write_probe(self, local_adapter, tmp_path):
        ok, latency_ms, err = local_adapter.test_read_write(str(tmp_path))
        assert ok is True
        assert latency_ms > 0.0
        assert err is None

    def test_local_adapter_path_traversal_protection(self, local_adapter, tmp_path):
        """Verifies that attempts to escape the storage root with '..' raise PermissionError."""
        safe_path = local_adapter.resolve_path(str(tmp_path), "cam_01/20261125/rec_001.mp4")
        assert Path(safe_path).is_relative_to(tmp_path.resolve())

        with pytest.raises(PermissionError):
            local_adapter.resolve_path(str(tmp_path), "../../../Windows/System32/cmd.exe")

    def test_local_adapter_volume_discovery(self, local_adapter):
        volumes = local_adapter.discover_local_volumes()
        assert len(volumes) >= 1
        v0 = volumes[0]
        assert "mount_path" in v0
        assert "total_gb" in v0
        assert "free_gb" in v0
        assert v0["total_gb"] > 0.0

    def test_local_adapter_capability_detection(self, local_adapter, tmp_path):
        caps = local_adapter.get_capabilities(str(tmp_path))
        assert "filesystem" in caps
        assert "is_read_only" in caps
        assert caps["is_read_only"] is False


class TestRAIDMonitoringAdapter:
    """Validates RAIDMonitoringAdapter health checks, degradation, and rebuild controls."""

    @pytest.fixture
    def raid_adapter(self):
        adapter = RAIDMonitoringAdapter()
        # Register a mock RAID-5 array for controlled testing
        arr = RAIDArrayInfo(
            array_id="raid5_surveillance_arr0",
            name="Surveillance RAID-5 Array",
            raid_level=RAIDLevel.RAID5,
            status=RAIDStatus.OPTIMAL,
            total_bytes=16 * 1024 * 1024 * 1024 * 1024,  # 16 TB
            used_bytes=4 * 1024 * 1024 * 1024 * 1024,
            free_bytes=12 * 1024 * 1024 * 1024 * 1024,
            member_disks=["Disk0", "Disk1", "Disk2", "Disk3"],
            missing_disks=[],
            rebuild_progress_pct=0.0,
            telemetry_source=TelemetrySource.SIMULATED,
            controller_model="LSI MegaRAID SAS 9361-8i",
            is_degraded=False,
        )
        adapter.register_simulated_array(arr)
        return adapter

    def test_raid_adapter_optimal_state(self, raid_adapter, tmp_path):
        assert raid_adapter.adapter_type == StorageType.RAID
        arrays = raid_adapter.get_all_arrays()
        assert len(arrays) >= 1
        arr = arrays[0]
        assert arr.status == RAIDStatus.OPTIMAL
        assert arr.is_degraded is False

    def test_raid_adapter_degraded_state(self, raid_adapter, tmp_path):
        arr = raid_adapter.get_all_arrays()[0]
        arr.status = RAIDStatus.DEGRADED
        arr.is_degraded = True
        arr.missing_disks = ["Disk2"]

        metrics = raid_adapter.get_metrics(str(tmp_path))
        assert metrics.status == HealthStatus.WARNING
        assert "DEGRADED" in (metrics.error_message or "")

    def test_raid_rebuild_authorization_and_gate(self, raid_adapter):
        arr = raid_adapter.get_all_arrays()[0]
        arr.status = RAIDStatus.DEGRADED

        # Non-admin role must be rejected
        ok, msg = raid_adapter.execute_rebuild(arr.array_id, operator="operator1", role="OPERATOR")
        assert ok is False
        assert "Permission denied" in msg

        # Admin role succeeds
        ok, msg = raid_adapter.execute_rebuild(arr.array_id, operator="admin1", role="ADMIN")
        assert ok is True
        assert arr.status == RAIDStatus.REBUILDING
        assert arr.rebuild_progress_pct > 0.0


class TestNASStorageAdapter:
    """Validates NASStorageAdapter SMB/NFS integration, DPAPI protection, and disconnect handling."""

    @pytest.fixture
    def nas_adapter(self):
        return NASStorageAdapter()

    def test_nas_profile_registration_and_dpapi_encryption(self, nas_adapter):
        profile = nas_adapter.register_connection(
            name="Synology_RackStation",
            protocol="SMB",
            host="192.168.1.200",
            share_name="surveillance_bulk",
            mount_point="\\\\192.168.1.200\\surveillance_bulk",
            username="nas_service_acct",
            plaintext_password="SuperSecretPassword2026!",
        )

        assert profile["name"] == "Synology_RackStation"
        assert profile["encrypted_password_envelope"] is not None
        assert profile["encrypted_password_envelope"] != "SuperSecretPassword2026!"

        # Decrypt via vault to confirm reversible DPAPI protection
        decrypted = credential_vault.decrypt_password(profile["encrypted_password_envelope"])
        assert decrypted == "SuperSecretPassword2026!"

    def test_nas_disconnection_simulation(self, nas_adapter, tmp_path):
        mount_path = str(tmp_path)
        assert nas_adapter.check_availability(mount_path) is True

        # Simulate network drop
        nas_adapter.simulate_disconnection(mount_path, disconnected=True)
        assert nas_adapter.check_availability(mount_path) is False

        metrics = nas_adapter.get_metrics(mount_path)
        assert metrics.status == HealthStatus.CRITICAL
        assert "unreachable" in (metrics.error_message or "").lower()

        # Simulate network restoration
        nas_adapter.simulate_disconnection(mount_path, disconnected=False)
        assert nas_adapter.check_availability(mount_path) is True
