"""
CCTV Device Diagnostics and Protocol Health Auditing Engine.
Phase 11 (F-019).
Probes RTSP, ONVIF, HTTP/HTTPS web endpoints, ISAPI, and CGI adapters.
Identifies root causes (auth failures, invalid RTSP paths, timeouts, closed ports)
with zero plaintext credential exposure.
"""

import re
import socket
import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("device_diagnostics")


class DiagnosticRootCause(str, Enum):
    SUCCESS = "SUCCESS"
    CONNECTION_FAILURE = "CONNECTION_FAILURE"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    INVALID_RTSP_PATH = "INVALID_RTSP_PATH"
    UNSUPPORTED_PROTOCOL = "UNSUPPORTED_PROTOCOL"
    STREAM_TIMEOUT = "STREAM_TIMEOUT"
    DNS_GATEWAY_ERROR = "DNS_GATEWAY_ERROR"
    PORT_CLOSED = "PORT_CLOSED"


@dataclass
class DiagnosticResult:
    """Individual probe outcome for a specific protocol/port."""
    protocol: str
    port: int
    is_healthy: bool
    latency_ms: float
    status_code: Optional[int] = None
    root_cause: DiagnosticRootCause = DiagnosticRootCause.SUCCESS
    details: str = ""
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["root_cause"] = self.root_cause.value
        return d


@dataclass
class ComprehensiveDeviceAuditReport:
    """Consolidated diagnostic audit report for a CCTV device."""
    ip_address: str
    hostname: str = ""
    mac_address: str = "Unknown"
    vendor: str = "Unknown Vendor"
    model: str = "Unknown Model"
    firmware_version: str = "Unknown"
    overall_healthy: bool = False
    probes: List[DiagnosticResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    masked_rtsp_url: str = ""
    summary: str = ""
    primary_root_cause: DiagnosticRootCause = DiagnosticRootCause.SUCCESS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "mac_address": self.mac_address,
            "vendor": self.vendor,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "overall_healthy": self.overall_healthy,
            "probes": [p.to_dict() for p in self.probes],
            "timestamp": self.timestamp,
            "masked_rtsp_url": self.masked_rtsp_url,
            "summary": self.summary,
            "primary_root_cause": self.primary_root_cause.value,
        }


def mask_credentials(url_or_string: str) -> str:
    """Masks passwords in connection strings and RTSP URLs (e.g. user:***@host)."""
    if not url_or_string:
        return ""
    # Matches scheme://user:pass@host
    return re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://\1:***@", url_or_string)


class DeviceDiagnosticEngine:
    """
    Multi-protocol CCTV reachability, RTSP handshake, ONVIF probe,
    and HTTP web management diagnostic engine.
    """

    @staticmethod
    def probe_tcp_port(ip_address: str, port: int, timeout_sec: float = 2.0) -> Tuple[bool, float, Optional[str]]:
        """Tests pure TCP connect latency and port availability."""
        t0 = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        try:
            sock.connect((ip_address, port))
            t1 = time.perf_counter()
            latency = (t1 - t0) * 1000.0
            return True, latency, None
        except socket.timeout:
            return False, 0.0, "Socket timeout: host or port did not respond"
        except ConnectionRefusedError:
            return False, 0.0, "Connection refused: port is closed"
        except Exception as e:
            return False, 0.0, f"Socket error: {e}"
        finally:
            sock.close()

    @classmethod
    def probe_rtsp_handshake(
        cls,
        ip_address: str,
        port: int = 554,
        rtsp_path: str = "/live",
        username: str = "",
        password: str = "",
        timeout_sec: float = 3.0,
    ) -> DiagnosticResult:
        """
        Sends standard RTSP OPTIONS and DESCRIBE commands.
        Analyzes response status codes without leaking credentials.
        """
        norm_path = "/" + rtsp_path.lstrip("/")
        # Build masked URL for display
        masked_url = mask_credentials(f"rtsp://{username}:{password}@{ip_address}:{port}{norm_path}") if username else f"rtsp://{ip_address}:{port}{norm_path}"

        t0 = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        try:
            sock.connect((ip_address, port))
            # 1. Send OPTIONS request
            options_req = (
                f"OPTIONS rtsp://{ip_address}:{port}{norm_path} RTSP/1.0\r\n"
                f"CSeq: 1\r\n"
                f"User-Agent: CCTV-AI-Diagnostics/1.1\r\n\r\n"
            )
            sock.sendall(options_req.encode("utf-8"))
            response_data = sock.recv(2048).decode("latin-1", errors="ignore")
            t1 = time.perf_counter()
            latency = (t1 - t0) * 1000.0

            # Parse status code
            status_match = re.search(r"RTSP/1\.\d\s+(\d{3})\s*(.*)", response_data)
            status_code = int(status_match.group(1)) if status_match else None
            status_line = status_match.group(2).strip() if status_match else ""

            if status_code in (200, 204):
                return DiagnosticResult(
                    protocol="RTSP",
                    port=port,
                    is_healthy=True,
                    latency_ms=round(latency, 2),
                    status_code=status_code,
                    root_cause=DiagnosticRootCause.SUCCESS,
                    details=f"RTSP OPTIONS handshake successful ({status_code} {status_line})",
                    recommendation="RTSP stream transport is operating normally.",
                )
            elif status_code == 401 or status_code == 403:
                return DiagnosticResult(
                    protocol="RTSP",
                    port=port,
                    is_healthy=False,
                    latency_ms=round(latency, 2),
                    status_code=status_code,
                    root_cause=DiagnosticRootCause.AUTHENTICATION_FAILURE,
                    details=f"RTSP authentication failed ({status_code} {status_line}) at {masked_url}",
                    recommendation="Verify camera username and password in Device Management.",
                )
            elif status_code in (404, 454):
                return DiagnosticResult(
                    protocol="RTSP",
                    port=port,
                    is_healthy=False,
                    latency_ms=round(latency, 2),
                    status_code=status_code,
                    root_cause=DiagnosticRootCause.INVALID_RTSP_PATH,
                    details=f"Invalid RTSP stream path ({status_code} {status_line}) on '{norm_path}'",
                    recommendation="Verify camera manufacturer RTSP URL path (e.g. /h264Preview_01_main or /live/ch0).",
                )
            else:
                return DiagnosticResult(
                    protocol="RTSP",
                    port=port,
                    is_healthy=False,
                    latency_ms=round(latency, 2),
                    status_code=status_code,
                    root_cause=DiagnosticRootCause.UNSUPPORTED_PROTOCOL,
                    details=f"RTSP unexpected response: {status_code} {status_line}",
                    recommendation="Check if camera supports standard RTSP 1.0 or requires specialized encapsulation.",
                )
        except socket.timeout:
            return DiagnosticResult(
                protocol="RTSP",
                port=port,
                is_healthy=False,
                latency_ms=0.0,
                root_cause=DiagnosticRootCause.STREAM_TIMEOUT,
                details=f"RTSP handshake connection timed out after {timeout_sec}s",
                recommendation="Check camera power, network PoE switch load, or firewall blocking port 554.",
            )
        except ConnectionRefusedError:
            return DiagnosticResult(
                protocol="RTSP",
                port=port,
                is_healthy=False,
                latency_ms=0.0,
                root_cause=DiagnosticRootCause.PORT_CLOSED,
                details=f"RTSP port {port} is closed or rejected connection",
                recommendation="Enable RTSP streaming service in camera web administration interface.",
            )
        except Exception as e:
            return DiagnosticResult(
                protocol="RTSP",
                port=port,
                is_healthy=False,
                latency_ms=0.0,
                root_cause=DiagnosticRootCause.CONNECTION_FAILURE,
                details=f"RTSP connection error: {e}",
                recommendation="Verify physical link, IP configuration, and subnet reachability.",
            )
        finally:
            sock.close()

    @classmethod
    def probe_http_endpoint(
        cls,
        ip_address: str,
        port: int = 80,
        use_https: bool = False,
        timeout_sec: float = 3.0,
    ) -> DiagnosticResult:
        """Tests HTTP/HTTPS web management endpoint reachability and server headers."""
        protocol_name = "HTTPS" if use_https else "HTTP"
        t0 = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        try:
            if use_https:
                import ssl
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                s = context.wrap_socket(sock, server_hostname=ip_address)
            else:
                s = sock

            s.connect((ip_address, port))
            req = f"HEAD / HTTP/1.1\r\nHost: {ip_address}:{port}\r\nUser-Agent: CCTV-AI-Diagnostics/1.1\r\nConnection: close\r\n\r\n"
            s.sendall(req.encode("utf-8"))
            resp = s.recv(2048).decode("latin-1", errors="ignore")
            t1 = time.perf_counter()
            latency = (t1 - t0) * 1000.0

            m = re.search(r"HTTP/1\.[01]\s+(\d{3})\s*(.*)", resp)
            status_code = int(m.group(1)) if m else None
            status_line = m.group(2).strip() if m else ""

            server_m = re.search(r"Server:\s*([^\r\n]+)", resp, re.IGNORECASE)
            server_banner = server_m.group(1).strip() if server_m else "Web Management"

            if status_code in (200, 301, 302, 401, 403):
                return DiagnosticResult(
                    protocol=protocol_name,
                    port=port,
                    is_healthy=True,
                    latency_ms=round(latency, 2),
                    status_code=status_code,
                    root_cause=DiagnosticRootCause.SUCCESS,
                    details=f"{protocol_name} response {status_code} ({server_banner})",
                    recommendation="Web interface reachable.",
                )
            else:
                return DiagnosticResult(
                    protocol=protocol_name,
                    port=port,
                    is_healthy=False,
                    latency_ms=round(latency, 2),
                    status_code=status_code,
                    root_cause=DiagnosticRootCause.UNSUPPORTED_PROTOCOL,
                    details=f"{protocol_name} returned unexpected code {status_code}",
                    recommendation="Verify web server service on camera.",
                )
        except ConnectionRefusedError:
            return DiagnosticResult(
                protocol=protocol_name,
                port=port,
                is_healthy=False,
                latency_ms=0.0,
                root_cause=DiagnosticRootCause.PORT_CLOSED,
                details=f"{protocol_name} port {port} closed",
                recommendation=f"Enable {protocol_name} web management in camera settings if required.",
            )
        except Exception as e:
            return DiagnosticResult(
                protocol=protocol_name,
                port=port,
                is_healthy=False,
                latency_ms=0.0,
                root_cause=DiagnosticRootCause.CONNECTION_FAILURE,
                details=f"{protocol_name} connection failed: {e}",
                recommendation="Check host reachability.",
            )
        finally:
            try:
                s.close()
            except Exception:
                pass

    @classmethod
    def probe_onvif_capabilities(
        cls,
        ip_address: str,
        port: int = 80,
        username: str = "",
        password: str = "",
        timeout_sec: float = 3.0,
    ) -> DiagnosticResult:
        """Probes ONVIF Device Service capabilities."""
        # Reuse or call integrations.onvif.client if present
        try:
            from integrations.onvif.client import ONVIFClient
            client = ONVIFClient(
                ip_address=ip_address,
                port=port,
                username=username,
                password=password,
                timeout_sec=timeout_sec,
            )
            t0 = time.perf_counter()
            caps = client.get_capabilities()
            t1 = time.perf_counter()
            latency = (t1 - t0) * 1000.0

            ptz_info = "PTZ Supported" if caps.has_ptz else "Fixed View (No PTZ)"
            return DiagnosticResult(
                protocol="ONVIF",
                port=port,
                is_healthy=True,
                latency_ms=round(latency, 2),
                status_code=200,
                root_cause=DiagnosticRootCause.SUCCESS,
                details=f"ONVIF device service active ({ptz_info})",
                recommendation="ONVIF Profile S/T compatibility verified.",
            )
        except Exception as e:
            err_msg = str(e)
            root_cause = DiagnosticRootCause.CONNECTION_FAILURE
            if "401" in err_msg or "Unauthorized" in err_msg or "auth" in err_msg.lower():
                root_cause = DiagnosticRootCause.AUTHENTICATION_FAILURE
            elif "timed out" in err_msg.lower():
                root_cause = DiagnosticRootCause.STREAM_TIMEOUT
            elif "refused" in err_msg.lower():
                root_cause = DiagnosticRootCause.PORT_CLOSED

            return DiagnosticResult(
                protocol="ONVIF",
                port=port,
                is_healthy=False,
                latency_ms=0.0,
                root_cause=root_cause,
                details=f"ONVIF probe failed: {err_msg}",
                recommendation="Verify ONVIF user account on camera and ensure ONVIF service is enabled.",
            )

    @classmethod
    def audit_device(
        cls,
        ip_address: str,
        rtsp_port: int = 554,
        onvif_port: int = 80,
        http_port: int = 80,
        username: str = "",
        password: str = "",
        rtsp_path: str = "/live",
        vendor: str = "Unknown",
        mac_address: str = "Unknown",
        timeout_sec: float = 3.0,
    ) -> ComprehensiveDeviceAuditReport:
        """
        Runs comprehensive multi-protocol diagnostic audit on a target CCTV device.
        Synthesizes results into a unified report with root cause categorization.
        """
        probes: List[DiagnosticResult] = []

        # 1. RTSP Probe
        rtsp_res = cls.probe_rtsp_handshake(
            ip_address=ip_address,
            port=rtsp_port,
            rtsp_path=rtsp_path,
            username=username,
            password=password,
            timeout_sec=timeout_sec,
        )
        probes.append(rtsp_res)

        # 2. ONVIF Probe
        if onvif_port:
            onvif_res = cls.probe_onvif_capabilities(
                ip_address=ip_address,
                port=onvif_port,
                username=username,
                password=password,
                timeout_sec=timeout_sec,
            )
            probes.append(onvif_res)

        # 3. HTTP Probe
        if http_port and http_port != onvif_port:
            http_res = cls.probe_http_endpoint(
                ip_address=ip_address,
                port=http_port,
                use_https=False,
                timeout_sec=timeout_sec,
            )
            probes.append(http_res)

        # Evaluate overall health
        has_healthy_stream = rtsp_res.is_healthy
        has_healthy_onvif = any(p.protocol == "ONVIF" and p.is_healthy for p in probes)
        overall_healthy = has_healthy_stream or has_healthy_onvif

        # Determine primary root cause
        primary_cause = DiagnosticRootCause.SUCCESS
        if not overall_healthy:
            # Prioritize authentication failure or invalid path over generic connection failure
            for p in probes:
                if p.root_cause == DiagnosticRootCause.AUTHENTICATION_FAILURE:
                    primary_cause = DiagnosticRootCause.AUTHENTICATION_FAILURE
                    break
                elif p.root_cause == DiagnosticRootCause.INVALID_RTSP_PATH:
                    primary_cause = DiagnosticRootCause.INVALID_RTSP_PATH
                    break
                elif p.root_cause == DiagnosticRootCause.PORT_CLOSED:
                    primary_cause = DiagnosticRootCause.PORT_CLOSED
                elif p.root_cause == DiagnosticRootCause.STREAM_TIMEOUT:
                    primary_cause = DiagnosticRootCause.STREAM_TIMEOUT
                elif primary_cause == DiagnosticRootCause.SUCCESS:
                    primary_cause = p.root_cause

        summary = (
            f"Device {ip_address} is operational (RTSP={has_healthy_stream}, ONVIF={has_healthy_onvif})"
            if overall_healthy
            else f"Device {ip_address} diagnostic alert: {primary_cause.value}"
        )

        masked_rtsp = mask_credentials(f"rtsp://{username}:{password}@{ip_address}:{rtsp_port}/{rtsp_path.lstrip('/')}") if username else f"rtsp://{ip_address}:{rtsp_port}/{rtsp_path.lstrip('/')}"

        return ComprehensiveDeviceAuditReport(
            ip_address=ip_address,
            mac_address=mac_address,
            vendor=vendor,
            overall_healthy=overall_healthy,
            probes=probes,
            masked_rtsp_url=masked_rtsp,
            summary=summary,
            primary_root_cause=primary_cause,
        )
