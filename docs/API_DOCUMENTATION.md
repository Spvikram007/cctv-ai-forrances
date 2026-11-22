# Internal Core API Documentation

## 1. Hardware Detection API (`core.hardware.detector`)

### `HardwareDetector.generate_full_report(storage_path: str = ".") -> SystemHardwareReport`
Performs live probing of host hardware and AI acceleration runtime:
- **Returns**: `SystemHardwareReport` dataclass with CPU, RAM, GPU, storage metrics, OpenVINO status, acceleration tier, and recommended concurrent AI streams.

### `HardwareDetector.detect_openvino() -> OpenVINOInfo`
Queries OpenVINO™ Core runtime for available inference plugins (`['CPU', 'GPU']`) and detects whether Intel GPU offload is possible.

---

## 2. Database Manager API (`database.database_manager`)

### `db_manager.init_schema() -> None`
Creates all tables registered in `database.models` if they do not exist.

### `db_manager.get_session() -> Generator[Session, None, None]`
Context manager yielding a thread-safe SQLAlchemy transactional session. Automatically commits upon normal exit and rolls back on exception.

### `db_manager.health_check() -> Dict[str, Any]`
Executes a live query (`SELECT 1`) to measure connection latency in milliseconds and verify table counts.

---

## 3. Worker Manager API (`core.workers.worker_manager`)

### `worker_manager.submit_task(fn: Callable, *args, **kwargs) -> Future`
Dispatches a background task to the managed `ThreadPoolExecutor`.

### `worker_manager.register_worker(worker: BackgroundWorker, start_immediately: bool = True) -> None`
Registers a persistent background worker thread with automated heartbeat and status monitoring.

### `worker_manager.shutdown(timeout: float = 5.0) -> None`
Gracefully halts all registered workers and thread pools.

---

## 4. Structured Redacting Logger API (`core.logging.logger`)

### `setup_logging(log_dir: str, log_level: str, ...) -> logging.Logger`
Configures root logger with credential redaction for RTSP URLs, database connection strings, passwords, and tokens. Creates human-readable `cctv_application.log` and structured `cctv_events.jsonl`.

### `get_logger(name: str) -> logging.Logger`
Returns a child logger under the `cctv_ai` namespace.

---

## 5. Event Bus API (`core.events.event_bus`)

### `bus.subscribe(topic: str, handler: Callable[[Event], None]) -> None`
Subscribes a callable to an event topic (supports exact match and wildcards e.g. `alarm.*`).

### `bus.publish(topic: str, data: Any, source: str = "system") -> None`
Dispatches an event synchronously to all registered listeners.
