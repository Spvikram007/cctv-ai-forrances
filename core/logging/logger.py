"""
Structured Logging Module for CCTV AI Intelligence Platform.
Provides JSON formatting, sensitive data redaction (credentials, tokens, RTSP passwords),
rotating file handlers, and console output.
"""

import os
import re
import sys
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Regular expressions for masking sensitive data (passwords, tokens, credentials)
SENSITIVE_PATTERNS = [
    (re.compile(r'(rtsp://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1******\3'),
    (re.compile(r'(https?://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1******\3'),
    (re.compile(r'("?(?:password|passwd|secret|token|api_key|access_key)"?\s*[:=]\s*["\'])([^"\']+)(["\'])', re.IGNORECASE), r'\1******\3'),
    (re.compile(r'(postgresql://[^:]+:)([^@]+)(@)', re.IGNORECASE), r'\1******\3'),
]


def redact_sensitive_text(text: str) -> str:
    """Redacts sensitive credentials and passwords from log strings."""
    if not isinstance(text, str):
        return str(text)
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    """Standard console/file formatter that redacts credentials from output."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_sensitive_text(formatted)


class JSONFormatter(logging.Formatter):
    """Structured JSON formatter for audit trails and file logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread,
            "thread_name": record.threadName,
            "process_id": record.process,
            "message": redact_sensitive_text(record.getMessage()),
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if k not in log_entry:
                    log_entry[k] = v

        return json.dumps(log_entry, default=str)


_configured = False


def setup_logging(
    log_dir: str = "storage/logs",
    log_level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB per file
    backup_count: int = 10,
    enable_console: bool = True,
    enable_json_file: bool = True,
    force_reconfigure: bool = False,
) -> logging.Logger:
    """
    Initializes root logger with redacting console and rotating file handlers.
    """
    global _configured

    root_logger = logging.getLogger()
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    if _configured and not force_reconfigure:
        return logging.getLogger("cctv_ai")

    # Clear pre-existing handlers
    for hdlr in list(root_logger.handlers):
        root_logger.removeHandler(hdlr)
        hdlr.close()

    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 1. Console Handler
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_format = RedactingFormatter(
            fmt="[%(asctime)s] [%(levelname)-8s] [%(name)s:%(module)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(console_format)
        root_logger.addHandler(console_handler)

    # 2. Main Human-Readable Rotating Log File
    text_log_file = log_path / "cctv_application.log"
    text_handler = RotatingFileHandler(
        filename=str(text_log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    text_handler.setLevel(level)
    text_handler.setFormatter(
        RedactingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s:%(module)s:%(lineno)d] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(text_handler)

    # 3. Structured JSON Rotating Log File
    if enable_json_file:
        json_log_file = log_path / "cctv_events.jsonl"
        json_handler = RotatingFileHandler(
            filename=str(json_log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        json_handler.setLevel(level)
        json_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(json_handler)

    _configured = True
    app_logger = logging.getLogger("cctv_ai")
    app_logger.info("Structured logging initialized (Level: %s, Directory: %s)", log_level, log_dir)
    return app_logger


def get_logger(name: str) -> logging.Logger:
    """Returns a named logger child of the platform logger."""
    return logging.getLogger(f"cctv_ai.{name}")
