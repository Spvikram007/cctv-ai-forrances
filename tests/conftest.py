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


@pytest.fixture(scope="session", autouse=True)
def isolate_test_database(test_settings: PlatformSettings):
    """
    Guarantees strict isolation of the test database.
    Prevents tests from ever reading, writing, or appending audit records
    to the production database at 'storage/cctv_metadata.db'.
    """
    from database.database_manager import db_manager
    from core.config.settings import settings
    from core.security.rbac import rbac_service

    # Save original production db path
    orig_path = settings.database.sqlite_path

    # Point global settings to temporary test database
    test_db_path = test_settings.database.sqlite_path
    settings.database.sqlite_path = test_db_path

    # Close existing connection to production DB and initialize on isolated test DB
    db_manager.close()
    db_manager.config = test_settings
    db_manager._initialize_engine()
    db_manager.init_schema()

    # Guard: Verify that db_manager is NOT pointing to the production database
    active_db = str(db_manager.engine.url) if db_manager.engine else ""
    prod_target = "storage/cctv_metadata.db"
    if prod_target in active_db or "cctv_metadata.db" in active_db:
        raise RuntimeError(
            f"SECURITY GUARD VIOLATION: Test suite attempted to run against production database: {active_db}"
        )

    # Seed default RBAC permissions and standard roles into the isolated test DB
    with db_manager.get_session() as session:
        rbac_service.seed_permissions_and_roles(session)

    yield test_db_path

    # Teardown: close test database and restore production path configuration
    db_manager.close()
    settings.database.sqlite_path = orig_path
    db_manager.config = settings


@pytest.fixture(scope="session")
def test_db_manager(isolate_test_database):
    """Provides the isolated global db_manager singleton."""
    from database.database_manager import db_manager
    return db_manager


@pytest.fixture(scope="session", autouse=True)
def ensure_test_models_exist():
    """Ensures local offline test model files exist for AI inference testing."""
    model_path = Path("models/yolov8n_surveillance.onnx")
    if not model_path.exists():
        model_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import onnx
            from onnx import helper, TensorProto
            input_tensor = helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 640, 640])
            output_tensor = helper.make_tensor_value_info('output0', TensorProto.FLOAT, [1, 84, 8400])
            const_tensor = helper.make_tensor(
                name='const_val',
                data_type=TensorProto.FLOAT,
                dims=[1, 84, 8400],
                vals=[0.0] * (1 * 84 * 8400)
            )
            node_const = helper.make_node('Constant', inputs=[], outputs=['const_out'], value=const_tensor)
            node_id = helper.make_node('Identity', inputs=['const_out'], outputs=['output0'])
            graph = helper.make_graph(
                nodes=[node_const, node_id],
                name='YOLOv8n_Surveillance',
                inputs=[input_tensor],
                outputs=[output_tensor]
            )
            model = helper.make_model(graph, producer_name='CCTV_AI_Platform')
            model.opset_import[0].version = 17
            onnx.save(model, str(model_path))
        except Exception:
            pass


def pytest_sessionfinish(session, exitstatus):
    """Ensures clean shutdown of any Qt or background thread resources."""
    try:
        from engines.storage_engine.storage_service import enterprise_storage_service
        enterprise_storage_service.stop_scheduler()
    except Exception:
        pass
    try:
        from engines.alarm_engine.alarm_service import alarm_service
        alarm_service.stop()
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.closeAllWindows()
            app.processEvents()
            app.quit()
    except Exception:
        pass
    try:
        import threading
        for t in threading.enumerate():
            if t is not threading.main_thread() and t.daemon and t.is_alive():
                t.join(timeout=0.8)
    except Exception:
        pass
