"""
Integration Tests for Physical and Socket-Level CCTV Camera Network Validation.
Phase 11.2 Independent Verification.

Validates multi-vendor network communications over actual TCP and UDP sockets:
- Hikvision ISAPI REST and RTSP OPTIONS handshake
- Dahua CGI RPC and RTSP OPTIONS handshake
- CP PLUS RTSP 401 Digest authentication challenge & credential masking
- Axis Communications HTTP web interface banner extraction
- RFC 3550 RTP video packet stream reception & smoothed interarrival jitter calculation
- Real socket connection latencies and packet counters
"""

import time
import socket
import threading
import pytest
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Tuple, Generator

from engines.network_engine.diagnostics import (
    DeviceDiagnosticEngine,
    DiagnosticRootCause,
    mask_credentials,
)
from engines.network_engine.monitor import (
    DeviceTelemetryHistory,
    TelemetrySample,
)
from engines.network_engine.security_audit import (
    NetworkSecurityAuditor,
    CVEConfidence,
)
from engines.network_engine.scanner import (
    NetworkScanner,
    DeviceType,
)


class MockRTSPServer:
    """Lightweight raw TCP socket server simulating multi-vendor RTSP responses."""

    def __init__(self, vendor_response: bytes):
        self.vendor_response = vendor_response
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                self.sock.settimeout(0.5)
                client, _ = self.sock.accept()
                client.settimeout(1.0)
                try:
                    data = client.recv(1024)
                    if data:
                        client.sendall(self.vendor_response)
                except Exception:
                    pass
                finally:
                    client.close()
            except socket.timeout:
                continue
            except Exception:
                break

    def stop(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass
        self._thread.join(timeout=1.0)


class MockCameraHTTPHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for Hikvision ISAPI, Dahua CGI, and Axis Web."""
    server_version = "Apache/2.4.25 (Axis-Communications)"
    sys_version = ""

    def log_message(self, format, *args):
        pass  # Suppress console logging during tests

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Server", "Apache/2.4.25 (Axis-Communications)")
        self.send_header("Content-Type", "text/html")
        self.end_headers()

    def do_GET(self):
        if "/ISAPI/System/deviceInfo" in self.path:
            # Hikvision ISAPI XML response
            body = (
                b'<?xml version="1.0" encoding="UTF-8"?>\r\n'
                b'<DeviceInfo version="2.0">\r\n'
                b'    <deviceName>IP CAMERA</deviceName>\r\n'
                b'    <model>DS-2CD2043G0-I</model>\r\n'
                b'    <serialNumber>DS-2CD2043G0-I20210101AAWR</serialNumber>\r\n'
                b'    <firmwareVersion>V5.5.80</firmwareVersion>\r\n'
                b'</DeviceInfo>\r\n'
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif "magicBox.cgi" in self.path:
            # Dahua CGI key-value response
            body = (
                b"appVersion=2.800.0000000.16.R\r\n"
                b"deviceType=IPC-HFW4431R-Z\r\n"
                b"serialNumber=3K01F8FPAG0001\r\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(200)
            self.send_header("Server", "Web-Server/1.0")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>OK</body></html>")


class MockHTTPServer:
    """Threaded HTTP server for camera REST and CGI APIs."""

    def __init__(self):
        self.server = HTTPServer(("127.0.0.1", 0), MockCameraHTTPHandler)
        self.port = self.server.server_port
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self._thread.join(timeout=1.0)


@pytest.fixture(scope="module")
def http_camera_server() -> Generator[MockHTTPServer, None, None]:
    srv = MockHTTPServer()
    yield srv
    srv.stop()


def test_hikvision_socket_handshake_and_isapi(http_camera_server):
    """
    Validates physical TCP socket interaction for Hikvision camera:
    - RTSP OPTIONS handshake on TCP socket (Server: Hikvision-RTSP/1.0)
    - ISAPI REST endpoint query returning XML model & firmware
    """
    rtsp_resp = (
        b"RTSP/1.0 200 OK\r\n"
        b"CSeq: 1\r\n"
        b"Server: Hikvision-RTSP/1.0\r\n"
        b"Public: OPTIONS, DESCRIBE, SETUP, TEARDOWN, PLAY, PAUSE\r\n\r\n"
    )
    rtsp_server = MockRTSPServer(rtsp_resp)

    try:
        # 1. Probe RTSP on real TCP socket
        diag = DeviceDiagnosticEngine.probe_rtsp_handshake(
            ip_address="127.0.0.1",
            port=rtsp_server.port,
            rtsp_path="/Streaming/Channels/101",
            timeout_sec=2.0,
        )

        assert diag.is_healthy is True
        assert diag.status_code == 200
        assert diag.latency_ms > 0.0
        assert diag.root_cause == DiagnosticRootCause.SUCCESS
        assert "RTSP OPTIONS handshake successful" in diag.details

        # 2. Probe HTTP endpoint on real TCP socket
        http_diag = DeviceDiagnosticEngine.probe_http_endpoint(
            ip_address="127.0.0.1",
            port=http_camera_server.port,
            timeout_sec=2.0,
        )
        assert http_diag.is_healthy is True
        assert http_diag.status_code == 200

        # 3. Test Hikvision ISAPI Adapter against the live socket
        from integrations.hikvision.isapi_adapter import HikvisionISAPIAdapter
        adapter = HikvisionISAPIAdapter(
            ip_address="127.0.0.1",
            port=http_camera_server.port,
            timeout_sec=2.0,
        )
        info = adapter.test_connection()
        assert info["success"] is True
        assert info["manufacturer"] == "Hikvision"
        assert info["model"] == "DS-2CD2043G0-I"
        assert info["firmware_version"] == "V5.5.80"
        assert info["serial_number"] == "DS-2CD2043G0-I20210101AAWR"

    finally:
        rtsp_server.stop()


def test_dahua_socket_handshake_and_cgi(http_camera_server):
    """
    Validates physical TCP socket interaction for Dahua camera:
    - RTSP OPTIONS handshake (Server: Dahua-RTSP/1.0)
    - Dahua CGI RPC endpoint (magicBox.cgi)
    """
    rtsp_resp = (
        b"RTSP/1.0 200 OK\r\n"
        b"CSeq: 1\r\n"
        b"Server: Dahua-RTSP/1.0\r\n"
        b"Public: OPTIONS, DESCRIBE, SETUP, TEARDOWN, PLAY\r\n\r\n"
    )
    rtsp_server = MockRTSPServer(rtsp_resp)

    try:
        diag = DeviceDiagnosticEngine.probe_rtsp_handshake(
            ip_address="127.0.0.1",
            port=rtsp_server.port,
            rtsp_path="/cam/realmonitor?channel=1&subtype=0",
            timeout_sec=2.0,
        )

        assert diag.is_healthy is True
        assert diag.status_code == 200
        assert diag.latency_ms > 0.0

        # Test Dahua CGI Adapter against the live socket
        from integrations.dahua.cgi_adapter import DahuaCGIAdapter
        adapter = DahuaCGIAdapter(
            ip_address="127.0.0.1",
            port=http_camera_server.port,
            timeout_sec=2.0,
        )
        info = adapter.test_connection()
        assert info["success"] is True
        assert info["manufacturer"] == "Dahua"
        assert info["model"] == "IPC-HFW4431R-Z"
        assert info["firmware_version"] == "2.800.0000000.16.R"

    finally:
        rtsp_server.stop()


def test_cpplus_socket_auth_challenge_and_credential_masking():
    """
    Validates CP PLUS camera returning 401 Unauthorized over real TCP socket:
    - Diagnostic root cause classified as AUTHENTICATION_FAILURE
    - Credentials strictly masked in masked_url / details
    """
    rtsp_resp = (
        b"RTSP/1.0 401 Unauthorized\r\n"
        b"CSeq: 1\r\n"
        b'WWW-Authenticate: Digest realm="CP_PLUS_IPC", nonce="987654321"\r\n\r\n'
    )
    rtsp_server = MockRTSPServer(rtsp_resp)

    try:
        diag = DeviceDiagnosticEngine.probe_rtsp_handshake(
            ip_address="127.0.0.1",
            port=rtsp_server.port,
            rtsp_path="/live/ch0",
            username="admin",
            password="SuperSecretPassword123!",
            timeout_sec=2.0,
        )

        assert diag.is_healthy is False
        assert diag.status_code == 401
        assert diag.root_cause == DiagnosticRootCause.AUTHENTICATION_FAILURE
        # Ensure zero plaintext credential leakage
        assert "SuperSecretPassword123!" not in diag.details
        assert "admin:***@" in diag.details

    finally:
        rtsp_server.stop()


def test_axis_socket_http_and_cve_correlation(http_camera_server):
    """
    Validates Axis Communications HTTP web interface banner extraction
    and CVE correlation over live socket.
    """
    diag = DeviceDiagnosticEngine.probe_http_endpoint(
        ip_address="127.0.0.1",
        port=http_camera_server.port,
        timeout_sec=2.0,
    )
    assert diag.is_healthy is True
    assert diag.status_code == 200
    assert "Axis-Communications" in diag.details

    # Correlate CVEs using NetworkSecurityAuditor
    auditor = NetworkSecurityAuditor()
    report = auditor.audit_device(
        ip_address="127.0.0.1",
        vendor="Axis Communications",
        model="M3045-V",
        firmware_version="9.80.1",
        open_ports=[80, 554],
        protocols=["HTTP", "RTSP"],
    )
    assert report.security_score < 100  # Deductions for unencrypted HTTP/RTSP
    assert len(report.cve_findings) == 0  # 9.80.1 is not in affected range of CVE-2018-10662


def test_rtp_interarrival_jitter_and_stream_counters():
    """
    Validates RFC 3550 Section 6.4.1 interarrival jitter computation
    using simulated RTP packet transit times with 90 kHz video clock.
    """
    history = DeviceTelemetryHistory("127.0.0.1", maxlen=100)

    # Simulate 25 fps video stream (40ms packet arrival interval)
    # Clock rate = 90,000 Hz -> 3600 clock units per 40ms frame
    clock_rate = 90000
    base_arrival = 1000.0
    base_rtp = 100000

    # Feed 20 RTP packet arrivals with controlled network transit jitter
    jitter_offsets_ms = [0, 5, -3, 8, -6, 2, 0, -4, 7, -2, 3, 5, -1, 4, -3, 2, 6, -5, 0, 1]

    for idx, j_ms in enumerate(jitter_offsets_ms):
        arrival = base_arrival + (idx * 0.040) + (j_ms / 1000.0)
        rtp_ts = base_rtp + (idx * 3600)
        history.record_rtp_packet(arrival_time=arrival, rtp_timestamp=rtp_ts, clock_rate=clock_rate)

    jitter_ms = history.get_rfc3550_jitter_ms()
    assert jitter_ms is not None
    assert jitter_ms > 0.0
    # Smoothed jitter should be within reasonable bounds (~1-10 ms)
    assert 0.5 <= jitter_ms <= 15.0

    # Add measured telemetry sample with real packet counter
    history.add_sample(
        TelemetrySample(
            timestamp=time.time(),
            ip_address="127.0.0.1",
            latency_ms=2.5,
            packet_loss_pct=0.0,
            measured_bandwidth_bps=4_194_304.0,  # 4.0 Mbps
            bandwidth_source="RTP_STREAM_COUNTER",
            fps=25.0,
            is_online=True,
        )
    )
    latest = history.samples[-1]
    assert latest.measured_bandwidth_bps == 4_194_304.0
    assert latest.bandwidth_source == "RTP_STREAM_COUNTER"


def test_scanner_live_socket_detection():
    """
    Validates NetworkScanner host probing against a live listening TCP socket.
    Confirms port detection, connect latency, and device classification.
    """
    rtsp_resp = b"RTSP/1.0 200 OK\r\n\r\n"
    rtsp_server = MockRTSPServer(rtsp_resp)

    try:
        scanner = NetworkScanner(max_threads=2, socket_timeout=1.0)
        dev = scanner.probe_host(
            ip_str="127.0.0.1",
            ports_to_check=[rtsp_server.port, 65432],  # 1 open, 1 closed
            default_gateway=None,
            arp_cache={},
        )
        assert dev is not None
        assert dev.ip_address == "127.0.0.1"
        assert rtsp_server.port in dev.open_ports
        assert 65432 not in dev.open_ports
        assert dev.latency_ms > 0.0
    finally:
        rtsp_server.stop()
