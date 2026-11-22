"""
Unit tests for Structured Logging and Credential Redaction.
"""

import json
from pathlib import Path
from core.logging.logger import redact_sensitive_text, setup_logging, get_logger


def test_redact_sensitive_text():
    # RTSP url with credentials
    rtsp_raw = "rtsp://admin:superSecret123@192.168.1.100:554/live"
    redacted = redact_sensitive_text(rtsp_raw)
    assert "superSecret123" not in redacted
    assert "rtsp://admin:******@192.168.1.100:554/live" in redacted

    # HTTP basic auth
    http_raw = "http://root:pass456@192.168.1.50/isapi/streaming"
    redacted_http = redact_sensitive_text(http_raw)
    assert "pass456" not in redacted_http

    # JSON password field
    json_field = '{"username": "admin", "password": "MySecretPassword"}'
    redacted_json = redact_sensitive_text(json_field)
    assert "MySecretPassword" not in redacted_json
    assert "******" in redacted_json


def test_logging_setup_and_output(tmp_path):
    log_dir = tmp_path / "logs"
    logger = setup_logging(log_dir=str(log_dir), log_level="DEBUG", enable_json_file=True, force_reconfigure=True)

    test_logger = get_logger("test_module")
    test_logger.info("Test message with rtsp://admin:cleartextpass@10.0.0.1:554/ch1")

    # Verify log files exist
    text_log = log_dir / "cctv_application.log"
    json_log = log_dir / "cctv_events.jsonl"
    assert text_log.exists()
    assert json_log.exists()

    # Verify redaction in text log
    content = text_log.read_text(encoding="utf-8")
    assert "cleartextpass" not in content
    assert "******" in content

    # Verify JSON structure
    json_lines = json_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(json_lines) > 0
    last_entry = json.loads(json_lines[-1])
    assert "timestamp" in last_entry
    assert "level" in last_entry
    assert "message" in last_entry
    assert "cleartextpass" not in last_entry["message"]
