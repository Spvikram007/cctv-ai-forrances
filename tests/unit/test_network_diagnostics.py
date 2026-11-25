"""
Unit tests for CCTV Device Diagnostics (Phase 11 - F-019).
"""

import pytest
import socket
from unittest.mock import patch, MagicMock

from engines.network_engine.diagnostics import (
    DeviceDiagnosticEngine,
    DiagnosticResult,
    DiagnosticRootCause,
    ComprehensiveDeviceAuditReport,
    mask_credentials,
)


def test_mask_credentials():
    assert mask_credentials("rtsp://admin:secret123@192.168.1.100:554/live") == "rtsp://admin:***@192.168.1.100:554/live"
    assert mask_credentials("rtsp://user:pass@camera.local/stream") == "rtsp://user:***@camera.local/stream"
    assert mask_credentials("rtsp://192.168.1.100:554/live") == "rtsp://192.168.1.100:554/live"
    assert mask_credentials("") == ""


def test_rtsp_handshake_success():
    mock_socket = MagicMock()
    mock_socket.recv.return_value = b"RTSP/1.0 200 OK\r\nCSeq: 1\r\nPublic: OPTIONS, DESCRIBE, SETUP, PLAY\r\n\r\n"

    with patch("socket.socket", return_value=mock_socket):
        res = DeviceDiagnosticEngine.probe_rtsp_handshake("192.168.1.50", port=554)

    assert res.is_healthy is True
    assert res.status_code == 200
    assert res.root_cause == DiagnosticRootCause.SUCCESS
    assert "successful" in res.details.lower()


def test_rtsp_handshake_auth_failure():
    mock_socket = MagicMock()
    mock_socket.recv.return_value = b"RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\nWWW-Authenticate: Digest realm=\"IP Camera\"\r\n\r\n"

    with patch("socket.socket", return_value=mock_socket):
        res = DeviceDiagnosticEngine.probe_rtsp_handshake("192.168.1.50", port=554, username="admin", password="wrongpassword")

    assert res.is_healthy is False
    assert res.status_code == 401
    assert res.root_cause == DiagnosticRootCause.AUTHENTICATION_FAILURE
    assert "wrongpassword" not in res.details
    assert "***" in res.details or "admin" in res.details


def test_rtsp_handshake_invalid_path():
    mock_socket = MagicMock()
    mock_socket.recv.return_value = b"RTSP/1.0 404 Not Found\r\nCSeq: 1\r\n\r\n"

    with patch("socket.socket", return_value=mock_socket):
        res = DeviceDiagnosticEngine.probe_rtsp_handshake("192.168.1.50", port=554, rtsp_path="/nonexistent_channel")

    assert res.is_healthy is False
    assert res.status_code == 404
    assert res.root_cause == DiagnosticRootCause.INVALID_RTSP_PATH


def test_rtsp_handshake_timeout():
    mock_socket = MagicMock()
    mock_socket.connect.side_effect = socket.timeout("Timed out")

    with patch("socket.socket", return_value=mock_socket):
        res = DeviceDiagnosticEngine.probe_rtsp_handshake("192.168.1.50", port=554)

    assert res.is_healthy is False
    assert res.root_cause == DiagnosticRootCause.STREAM_TIMEOUT


def test_rtsp_handshake_port_closed():
    mock_socket = MagicMock()
    mock_socket.connect.side_effect = ConnectionRefusedError("Connection refused")

    with patch("socket.socket", return_value=mock_socket):
        res = DeviceDiagnosticEngine.probe_rtsp_handshake("192.168.1.50", port=554)

    assert res.is_healthy is False
    assert res.root_cause == DiagnosticRootCause.PORT_CLOSED


def test_http_endpoint_probe():
    mock_socket = MagicMock()
    mock_socket.recv.return_value = b"HTTP/1.1 200 OK\r\nServer: Hikvision-Webs\r\n\r\n"

    with patch("socket.socket", return_value=mock_socket):
        res = DeviceDiagnosticEngine.probe_http_endpoint("192.168.1.50", port=80)

    assert res.is_healthy is True
    assert res.status_code == 200
    assert "Hikvision-Webs" in res.details


def test_comprehensive_device_audit():
    with patch.object(
        DeviceDiagnosticEngine,
        "probe_rtsp_handshake",
        return_value=DiagnosticResult(
            protocol="RTSP",
            port=554,
            is_healthy=True,
            latency_ms=15.0,
            status_code=200,
            root_cause=DiagnosticRootCause.SUCCESS,
            details="RTSP OK",
        ),
    ), patch.object(
        DeviceDiagnosticEngine,
        "probe_onvif_capabilities",
        return_value=DiagnosticResult(
            protocol="ONVIF",
            port=80,
            is_healthy=True,
            latency_ms=25.0,
            status_code=200,
            root_cause=DiagnosticRootCause.SUCCESS,
            details="ONVIF Profile S active",
        ),
    ):
        report = DeviceDiagnosticEngine.audit_device("192.168.1.50", vendor="Hikvision")

    assert report.overall_healthy is True
    assert report.primary_root_cause == DiagnosticRootCause.SUCCESS
    assert len(report.probes) >= 2
    assert report.vendor == "Hikvision"
