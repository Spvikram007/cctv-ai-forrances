"""
Pytest Configuration and Test Fixtures.
"""

import os
import pytest
from pathlib import Path
from core.config.settings import PlatformSettings, DatabaseSettings, StorageSettings
from database.database_manager import DatabaseManager
from database.models.base import Base


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory) -> PlatformSettings:
    """Provides isolated temporary settings for test runs."""
    tmp_dir = tmp_path_factory.mktemp("cctv_test_data")
    settings = PlatformSettings(
        environment="testing",
        debug=True,
        database=DatabaseSettings(
            engine_type="sqlite",
            sqlite_path=str(tmp_dir / "test_cctv.db"),
            echo_sql=False,
        ),
        storage=StorageSettings(
            recordings_dir=str(tmp_dir / "recordings"),
            snapshots_dir=str(tmp_dir / "snapshots"),
            evidence_dir=str(tmp_dir / "evidence"),
            exports_dir=str(tmp_dir / "exports"),
            backups_dir=str(tmp_dir / "backups"),
            logs_dir=str(tmp_dir / "logs"),
        ),
    )
    settings.ensure_directories()
    return settings


@pytest.fixture(scope="session")
def test_db_manager(test_settings: PlatformSettings) -> DatabaseManager:
    """Provides an isolated database manager with temporary SQLite backend."""
    manager = DatabaseManager(config=test_settings)
    manager.init_schema()
    yield manager
    manager.close()
