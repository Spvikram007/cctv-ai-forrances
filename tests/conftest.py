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
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.closeAllWindows()
            app.processEvents()
            app.quit()
        import gc
        gc.collect()
    except Exception:
        pass
