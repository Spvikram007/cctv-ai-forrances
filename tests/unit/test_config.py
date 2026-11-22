"""
Unit tests for Configuration Management.
"""

import os
from core.config.settings import PlatformSettings, DatabaseSettings, AISettings


def test_default_settings():
    settings = PlatformSettings()
    assert settings.app_name == "CCTV AI Intelligence Platform"
    assert settings.video.max_channels == 64
    assert settings.ai.detection_confidence_threshold == 0.50
    assert settings.database.engine_type in ["sqlite", "postgresql"]


def test_custom_settings_validation():
    db = DatabaseSettings(engine_type="sqlite", pool_size=5)
    assert db.engine_type == "sqlite"
    assert db.pool_size == 5

    ai = AISettings(preferred_device="GPU", detection_confidence_threshold=0.75)
    assert ai.preferred_device == "GPU"
    assert ai.detection_confidence_threshold == 0.75


def test_directory_creation(tmp_path):
    storage_dir = tmp_path / "custom_storage"
    settings = PlatformSettings(
        storage={"recordings_dir": str(storage_dir / "recs"), "logs_dir": str(storage_dir / "logs")}
    )
    settings.ensure_directories()
    assert (storage_dir / "recs").exists()
    assert (storage_dir / "logs").exists()
