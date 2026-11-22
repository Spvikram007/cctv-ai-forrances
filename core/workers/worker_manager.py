"""
Worker and Background Process Management Engine.
Manages thread pools, background stream workers, AI inference queues,
and guarantees graceful shutdown and error isolation.
"""

import time
import threading
from typing import Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("worker_manager")


@dataclass
class WorkerStatus:
    name: str
    is_alive: bool = False
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None


class BackgroundWorker(threading.Thread):
    """Base class for resilient long-running background tasks."""

    def __init__(self, name: str, interval_sec: float = 1.0, daemon: bool = True) -> None:
        super().__init__(name=name, daemon=daemon)
        self.worker_name = name
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self.status = WorkerStatus(name=name)

    def stop(self) -> None:
        """Signals the background worker to stop gracefully."""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def run(self) -> None:
        self.status.is_alive = True
        self.status.started_at = datetime.now(timezone.utc)
        logger.info("Worker [%s] started.", self.worker_name)

        while not self._stop_event.is_set():
            try:
                self.status.last_heartbeat = datetime.now(timezone.utc)
                self.work_cycle()
            except Exception as e:
                self.status.error_count += 1
                self.status.last_error = str(e)
                logger.error("Exception in worker [%s]: %s", self.worker_name, e, exc_info=True)

            self._stop_event.wait(self.interval_sec)

        self.status.is_alive = False
        logger.info("Worker [%s] stopped.", self.worker_name)

    def work_cycle(self) -> None:
        """Override in subclasses to perform periodic work."""
        pass


class WorkerManager:
    """Manages thread pools and background worker lifecycles."""

    def __init__(self, max_threads: int = 32) -> None:
        self.max_threads = max_threads
        self._executor = ThreadPoolExecutor(max_workers=max_threads, thread_name_prefix="CCTV-Worker")
        self._workers: Dict[str, BackgroundWorker] = {}
        self._lock = threading.RLock()
        self._is_shutting_down = False

    def submit_task(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
        """Submits a short or medium duration task to the managed thread pool."""
        if self._is_shutting_down:
            raise RuntimeError("Cannot submit task: WorkerManager is shutting down.")
        return self._executor.submit(fn, *args, **kwargs)

    def register_worker(self, worker: BackgroundWorker, start_immediately: bool = True) -> None:
        """Registers a named background worker."""
        with self._lock:
            if worker.worker_name in self._workers:
                logger.warning("Replacing existing worker [%s]", worker.worker_name)
                self.stop_worker(worker.worker_name)
            self._workers[worker.worker_name] = worker
            if start_immediately:
                worker.start()

    def stop_worker(self, name: str) -> None:
        """Stops and removes a registered background worker."""
        with self._lock:
            worker = self._workers.get(name)
            if worker:
                worker.stop()
                if worker.is_alive():
                    worker.join(timeout=3.0)
                del self._workers[name]

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Returns the health status of all registered workers."""
        with self._lock:
            result = {}
            for name, w in self._workers.items():
                result[name] = {
                    "is_alive": w.is_alive(),
                    "started_at": w.status.started_at.isoformat() if w.status.started_at else None,
                    "last_heartbeat": w.status.last_heartbeat.isoformat() if w.status.last_heartbeat else None,
                    "error_count": w.status.error_count,
                    "last_error": w.status.last_error,
                }
            return result

    def shutdown(self, timeout: float = 5.0) -> None:
        """Gracefully halts all workers and the thread pool executor."""
        logger.info("Initiating WorkerManager shutdown (timeout=%.1fs)...", timeout)
        self._is_shutting_down = True

        with self._lock:
            for name, worker in list(self._workers.items()):
                try:
                    worker.stop()
                except Exception as e:
                    logger.warning("Error stopping worker [%s]: %s", name, e)

            for name, worker in list(self._workers.items()):
                if worker.is_alive():
                    worker.join(timeout=timeout / max(len(self._workers), 1))

            self._workers.clear()

        self._executor.shutdown(wait=True, cancel_futures=True)
        logger.info("WorkerManager shutdown completed.")


# Global worker manager singleton
worker_manager = WorkerManager()
