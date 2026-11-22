"""
Unit tests for WorkerManager and Background Workers.
"""

import time
from core.workers.worker_manager import WorkerManager, BackgroundWorker


class DummyWorker(BackgroundWorker):
    def __init__(self, name: str, interval_sec: float = 0.05):
        super().__init__(name=name, interval_sec=interval_sec)
        self.counter = 0

    def work_cycle(self) -> None:
        self.counter += 1


def test_task_pool_execution():
    manager = WorkerManager(max_threads=4)
    future = manager.submit_task(lambda x, y: x * y, 6, 7)
    result = future.result(timeout=2.0)
    assert result == 42
    manager.shutdown()


def test_background_worker_lifecycle():
    manager = WorkerManager(max_threads=4)
    worker = DummyWorker(name="TestDummy", interval_sec=0.05)
    
    manager.register_worker(worker, start_immediately=True)
    time.sleep(0.2)
    
    status = manager.get_status()
    assert "TestDummy" in status
    assert status["TestDummy"]["is_alive"] is True
    assert worker.counter > 0
    
    manager.stop_worker("TestDummy")
    assert worker.is_alive() is False
    manager.shutdown()
