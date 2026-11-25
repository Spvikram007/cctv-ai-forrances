"""
Unit Tests for Storage Policy Engine and Allocation Manager.
Phase 13 (F-047, Change ID: CHG-20261125-012).
"""

import os
import pytest
from database.database_manager import db_manager
from database.models.recordings import StorageVolume
from database.models.storage import StoragePool, StoragePolicy, StorageAllocation
from engines.storage_engine.policy_engine import StoragePolicyEngine
from engines.storage_engine.allocation_manager import StorageAllocationManager
from engines.storage_engine.enums import PoolTier, VolumeStatus


class TestStoragePolicyEngine:
    """Validates policy enforcement, write eligibility, and capacity thresholds."""

    @pytest.fixture
    def policy_engine(self):
        return StoragePolicyEngine()

    def test_eligible_volume(self, policy_engine):
        vol = StorageVolume(
            name="Healthy Vol",
            mount_path="D:/Healthy",
            total_bytes=100 * 1024 * 1024 * 1024,
            used_bytes=30 * 1024 * 1024 * 1024,
            available_bytes=70 * 1024 * 1024 * 1024,
            warning_threshold_pct=85.0,
            is_active=True,
            volume_status=VolumeStatus.ONLINE.value,
        )
        ok, reason = policy_engine.is_volume_eligible_for_write(vol, required_mb=50.0)
        assert ok is True
        assert reason == "Eligible"

    def test_ineligible_volume_critical_threshold(self, policy_engine):
        vol = StorageVolume(
            name="Full Vol",
            mount_path="D:/Full",
            total_bytes=100 * 1024 * 1024 * 1024,
            used_bytes=97 * 1024 * 1024 * 1024,
            available_bytes=3 * 1024 * 1024 * 1024,
            warning_threshold_pct=85.0,
            is_active=True,
            volume_status=VolumeStatus.ONLINE.value,
        )
        ok, reason = policy_engine.is_volume_eligible_for_write(vol, required_mb=50.0)
        assert ok is False
        assert "critical capacity" in reason or "free space below" in reason

    def test_ineligible_volume_offline(self, policy_engine):
        vol = StorageVolume(
            name="Offline Vol",
            mount_path="D:/Offline",
            total_bytes=100 * 1024 * 1024 * 1024,
            used_bytes=20 * 1024 * 1024 * 1024,
            available_bytes=80 * 1024 * 1024 * 1024,
            is_active=True,
            volume_status=VolumeStatus.OFFLINE.value,
        )
        ok, reason = policy_engine.is_volume_eligible_for_write(vol)
        assert ok is False
        assert "status is OFFLINE" in reason


class TestStorageAllocationManager:
    """Validates camera channel to storage pool and volume allocations."""

    @pytest.fixture
    def alloc_manager(self):
        return StorageAllocationManager()

    def test_default_pool_creation(self, alloc_manager):
        pool = alloc_manager.get_or_create_default_pool(tier=PoolTier.HOT)
        assert pool.id is not None
        assert pool.name == "Primary Surveillance Pool"
        assert pool.pool_tier == PoolTier.HOT.value

    def test_channel_allocation_and_resolution(self, alloc_manager, tmp_path):
        prim_dir = str(tmp_path / "primary")
        fail_dir = str(tmp_path / "failover")
        os.makedirs(prim_dir, exist_ok=True)
        os.makedirs(fail_dir, exist_ok=True)

        with db_manager.get_session() as session:
            v_prim = StorageVolume(
                name="Primary Test Vol",
                mount_path=prim_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=90 * 1024 * 1024 * 1024,
                is_active=True,
                volume_status="ONLINE",
            )
            v_fail = StorageVolume(
                name="Failover Test Vol",
                mount_path=fail_dir,
                total_bytes=100 * 1024 * 1024 * 1024,
                used_bytes=10 * 1024 * 1024 * 1024,
                available_bytes=90 * 1024 * 1024 * 1024,
                is_active=True,
                volume_status="ONLINE",
                is_failover_target=True,
            )
            session.add(v_prim)
            session.add(v_fail)
            session.flush()
            prim_id = str(v_prim.id)
            fail_id = str(v_fail.id)

        alloc = alloc_manager.allocate_channel(
            channel_id="cam_gate_01",
            primary_volume_id=prim_id,
            failover_volume_id=fail_id,
        )
        assert alloc.primary_volume_id == prim_id
        assert alloc.failover_volume_id == fail_id

        # Resolve destination while primary is healthy
        vol, dir_path, is_failover = alloc_manager.resolve_destination_for_channel("cam_gate_01")
        assert vol.id == prim_id
        assert is_failover is False
        assert "cam_gate_01" in dir_path

        # Simulate primary volume exhaustion/offline
        with db_manager.get_session() as session:
            db_prim = session.query(StorageVolume).filter_by(id=prim_id).first()
            db_prim.volume_status = VolumeStatus.OFFLINE.value

        # Resolve destination should now seamlessly redirect to failover volume!
        vol, dir_path, is_failover = alloc_manager.resolve_destination_for_channel("cam_gate_01")
        assert vol.id == fail_id
        assert is_failover is True
        assert "cam_gate_01" in dir_path
