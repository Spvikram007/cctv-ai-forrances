"""
Database Management Engine for CCTV AI Intelligence Platform.
Supports PostgreSQL for high-scale enterprise deployments and resilient
automatic SQLite WAL mode fallback for robust offline local operations.
"""

import os
import time
from pathlib import Path
from typing import Generator, Dict, Any, Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, event, text, Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool

from core.logging.logger import get_logger
from core.config.settings import PlatformSettings, settings
from database.models.base import Base
# Ensure all models are imported so Base.metadata knows all tables
import database.models  # noqa: F401

logger = get_logger("database_manager")


class DatabaseManager:
    """Manages database connection lifecycle, sessions, and schema migrations."""

    def __init__(self, config: Optional[PlatformSettings] = None) -> None:
        self.config = config or settings
        self.engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.active_backend: str = "uninitialized"
        self._initialize_engine()

    def _initialize_engine(self) -> None:
        db_conf = self.config.database
        
        # 1. Try PostgreSQL if configured
        if db_conf.engine_type == "postgresql" and db_conf.postgresql_url:
            try:
                logger.info("Attempting connection to PostgreSQL: %s", db_conf.postgresql_url.split("@")[-1])
                pg_engine = create_engine(
                    db_conf.postgresql_url,
                    pool_size=db_conf.pool_size,
                    max_overflow=db_conf.max_overflow,
                    pool_timeout=db_conf.pool_timeout,
                    echo=db_conf.echo_sql,
                )
                with pg_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                self.engine = pg_engine
                self.active_backend = "postgresql"
                logger.info("PostgreSQL database connection verified and active.")
            except Exception as e:
                logger.warning("PostgreSQL connection failed: %s. Falling back to SQLite WAL mode.", e)
                self.engine = None

        # 2. Resilient Fallback to SQLite WAL mode
        if self.engine is None:
            sqlite_path = Path(db_conf.sqlite_path)

            # Security Isolation Guard: Prevent tests from ever connecting to production database
            if "PYTEST_CURRENT_TEST" in os.environ and "cctv_metadata.db" in sqlite_path.name:
                raise RuntimeError(
                    f"SECURITY GUARD VIOLATION: Pytest execution attempted to connect to production database: {sqlite_path}"
                )

            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{sqlite_path.as_posix()}"
            
            logger.info("Initializing local SQLite database with WAL mode: %s", db_url)
            self.engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False, "timeout": 30},
                poolclass=QueuePool,
                echo=db_conf.echo_sql,
            )

            # SQLite performance & integrity optimizations
            @event.listens_for(self.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.close()

            self.active_backend = "sqlite"

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def init_schema(self) -> None:
        """Initializes all registered metadata tables if they do not exist."""
        if self.engine is None:
            self._initialize_engine()
        logger.info("Verifying and creating database schema for backend [%s]...", self.active_backend)
        Base.metadata.create_all(bind=self.engine)

        # Automatic lightweight migration for schema additions (e.g. SQLite missing column/index upgrades)
        try:
            with self.engine.begin() as conn:
                if self.active_backend == "sqlite":
                    cursor = conn.connection.cursor()
                    cursor.execute("PRAGMA table_info(alarm_history)")
                    existing_cols = {row[1] for row in cursor.fetchall()}
                    if existing_cols:
                        if "entry_index" not in existing_cols:
                            conn.execute(text("ALTER TABLE alarm_history ADD COLUMN entry_index INTEGER DEFAULT 0"))
                        if "prev_hash" not in existing_cols:
                            conn.execute(text("ALTER TABLE alarm_history ADD COLUMN prev_hash VARCHAR(64)"))
                        if "entry_hash" not in existing_cols:
                            conn.execute(text("ALTER TABLE alarm_history ADD COLUMN entry_hash VARCHAR(64)"))
                    cursor.close()

                    # Ensure composite and partial unique indexes exist
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alarm_dedup_status ON alarms (dedup_key, status)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alarm_deadline_status ON alarms (next_escalation_deadline, status)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_alarm_status_sev_time ON alarms (status, severity, last_detected_at)"))
                    conn.execute(text("""
                        CREATE UNIQUE INDEX IF NOT EXISTS uq_alarm_active_dedup ON alarms (dedup_key) 
                        WHERE status IN ('NEW', 'ACKNOWLEDGED', 'IN_PROGRESS', 'REOPENED') 
                          AND is_deleted = 0 
                          AND dedup_key IS NOT NULL
                    """))

                    # Upgrade alarm_notifications table for durable delivery retries
                    cursor = conn.connection.cursor()
                    cursor.execute("PRAGMA table_info(alarm_notifications)")
                    notif_cols = {row[1] for row in cursor.fetchall()}
                    if notif_cols:
                        if "next_retry_at" not in notif_cols:
                            conn.execute(text("ALTER TABLE alarm_notifications ADD COLUMN next_retry_at TIMESTAMP"))
                        if "payload" not in notif_cols:
                            conn.execute(text("ALTER TABLE alarm_notifications ADD COLUMN payload TEXT"))
                    cursor.close()

                    # Upgrade storage_volumes table for Phase 13 Enterprise Storage
                    cursor = conn.connection.cursor()
                    cursor.execute("PRAGMA table_info(storage_volumes)")
                    vol_cols = {row[1] for row in cursor.fetchall()}
                    if vol_cols:
                        if "pool_id" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN pool_id VARCHAR(36)"))
                        if "volume_type" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN volume_type VARCHAR(20) DEFAULT 'LOCAL'"))
                        if "filesystem" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN filesystem VARCHAR(20) DEFAULT 'NTFS'"))
                        if "volume_status" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN volume_status VARCHAR(20) DEFAULT 'ONLINE'"))
                        if "is_failover_target" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN is_failover_target BOOLEAN DEFAULT 0"))
                        if "reserved_bytes" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN reserved_bytes BIGINT DEFAULT 0"))
                        if "health_score" not in vol_cols:
                            conn.execute(text("ALTER TABLE storage_volumes ADD COLUMN health_score FLOAT DEFAULT 100.0"))
                    cursor.close()

                    # Upgrade users, user_sessions, and audit_logs tables for Phase 14 User Management, RBAC & Audit
                    cursor = conn.connection.cursor()
                    cursor.execute("PRAGMA table_info(users)")
                    user_cols = {row[1] for row in cursor.fetchall()}
                    if user_cols:
                        if "failed_login_attempts" not in user_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0"))
                        if "locked_until" not in user_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN locked_until TIMESTAMP"))
                        if "last_login_at" not in user_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP"))
                        if "last_activity_at" not in user_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN last_activity_at TIMESTAMP"))
                        if "password_changed_at" not in user_cols:
                            conn.execute(text("ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP"))

                    cursor.execute("PRAGMA table_info(user_sessions)")
                    session_cols = {row[1] for row in cursor.fetchall()}
                    if session_cols:
                        if "last_seen_at" not in session_cols:
                            conn.execute(text("ALTER TABLE user_sessions ADD COLUMN last_seen_at TIMESTAMP"))

                    cursor.execute("PRAGMA table_info(audit_logs)")
                    audit_cols = {row[1] for row in cursor.fetchall()}
                    if audit_cols:
                        if "username" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN username VARCHAR(50)"))
                        if "category" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN category VARCHAR(50)"))
                        if "status" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN status VARCHAR(20) DEFAULT 'SUCCESS'"))
                        if "session_id" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN session_id VARCHAR(255)"))
                        if "correlation_id" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN correlation_id VARCHAR(64)"))
                        if "prev_hash" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN prev_hash VARCHAR(64)"))
                        if "record_hash" not in audit_cols:
                            conn.execute(text("ALTER TABLE audit_logs ADD COLUMN record_hash VARCHAR(64)"))
                    cursor.close()

                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_username ON audit_logs (username)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_category ON audit_logs (category)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_status ON audit_logs (status)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_correlation_id ON audit_logs (correlation_id)"))
        except Exception as e:
            logger.debug("Schema migration notice: %s", e)

        logger.info("Database schema verification completed successfully.")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Context manager for safe transactional database sessions."""
        if self.SessionLocal is None:
            self._initialize_engine()
        assert self.SessionLocal is not None
        session: Session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def health_check(self) -> Dict[str, Any]:
        """Performs a live query and measures latency."""
        if self.engine is None:
            return {"status": "UNHEALTHY", "error": "No engine"}
        
        start_time = time.perf_counter()
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            table_count = len(Base.metadata.tables)
            return {
                "status": "HEALTHY",
                "backend": self.active_backend,
                "latency_ms": latency_ms,
                "table_count": table_count,
            }
        except Exception as e:
            return {
                "status": "UNHEALTHY",
                "backend": self.active_backend,
                "error": str(e),
            }

    def close(self) -> None:
        """Disposes connection pool on application shutdown."""
        if self.engine:
            self.engine.dispose()
            self.engine = None
            self.SessionLocal = None
            logger.info("Database connection pool disposed.")


# Global database manager singleton
db_manager = DatabaseManager()
