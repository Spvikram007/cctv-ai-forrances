"""
Automated Root-Cause Diagnostic and Fault Isolation Engine.
Phase 11 (F-019).
Analyzes network metrics and CCTV telemetry to isolate root causes:
CAMERA_HARDWARE_FAILURE, NVR_FAILURE, NETWORK_DISCONNECTION,
AUTHENTICATION_FAILURE, DNS_FAILURE, RTSP_STREAM_FAILURE, and BANDWIDTH_CONGESTION.
Generates operator-gated remediation recommendations.
"""

from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("fault_analyzer")


class FaultType(str, Enum):
    CAMERA_HARDWARE_FAILURE = "CAMERA_HARDWARE_FAILURE"
    NVR_FAILURE = "NVR_FAILURE"
    NETWORK_DISCONNECTION = "NETWORK_DISCONNECTION"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    DNS_FAILURE = "DNS_FAILURE"
    RTSP_STREAM_FAILURE = "RTSP_STREAM_FAILURE"
    BANDWIDTH_CONGESTION = "BANDWIDTH_CONGESTION"
    NO_FAULT = "NO_FAULT"


@dataclass
class FaultAnalysisReport:
    """Detailed fault diagnostic report with isolation explanation and remediation."""
    fault_type: FaultType
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW, INFO
    affected_ips: List[str]
    root_cause_explanation: str
    recommended_remediation: str
    requires_operator_approval: bool = True
    remediation_action_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["fault_type"] = self.fault_type.value
        return d


class FaultIsolationMatrix:
    """Matrix rules defining fault classification logic."""

    @staticmethod
    def is_gateway_offline(gateway_ping_ok: bool) -> bool:
        return not gateway_ping_ok

    @staticmethod
    def is_nvr_failure(nvr_online: bool, attached_camera_online_count: int, total_attached: int) -> bool:
        if not nvr_online and total_attached > 0 and attached_camera_online_count == 0:
            return True
        return False

    @staticmethod
    def is_isolated_camera_failure(target_online: bool, subnet_online_ratio: float) -> bool:
        # If target camera is offline, but > 70% of other devices on the same subnet are healthy
        return (not target_online) and (subnet_online_ratio >= 0.7)

    @staticmethod
    def is_congestion(avg_latency_ms: float, avg_packet_loss_pct: float) -> bool:
        return avg_latency_ms > 150.0 or avg_packet_loss_pct > 5.0


class AutomatedFaultAnalyzer:
    """
    Evaluates telemetry across multiple devices, gateways, and NVRs to
    diagnose root network and device faults.
    """

    def __init__(self) -> None:
        self.matrix = FaultIsolationMatrix()

    def analyze_network_state(
        self,
        gateway_ip: Optional[str] = None,
        gateway_online: bool = True,
        devices: Optional[List[Dict[str, Any]]] = None,
        nvr_mappings: Optional[Dict[str, List[str]]] = None,
    ) -> List[FaultAnalysisReport]:
        """
        Analyzes full network telemetry state and returns prioritized fault reports.
        """
        if devices is None:
            devices = []
        if nvr_mappings is None:
            nvr_mappings = {}

        reports: List[FaultAnalysisReport] = []

        # Rule 1: Check Default Gateway Health (Network Disconnection)
        if gateway_ip and not gateway_online:
            reports.append(
                FaultAnalysisReport(
                    fault_type=FaultType.NETWORK_DISCONNECTION,
                    severity="CRITICAL",
                    affected_ips=[gateway_ip] + [d["ip_address"] for d in devices if not d.get("is_online", True)],
                    root_cause_explanation=(
                        f"Default gateway {gateway_ip} is unreachable via ICMP/TCP ping. "
                        "Uplink connectivity and inter-VLAN routing have stopped responding."
                    ),
                    recommended_remediation=(
                        "Inspect power and link state on the core gateway router or firewall. "
                        "Verify physical patch cables connecting the CCTV switch to the gateway."
                    ),
                    requires_operator_approval=True,
                    remediation_action_id="REMEDIATE-GATEWAY-CHECK",
                )
            )

        # Rule 2: Check NVR Correlated Failures
        for nvr_ip, child_ips in nvr_mappings.items():
            nvr_dev = next((d for d in devices if d.get("ip_address") == nvr_ip), None)
            is_nvr_online = nvr_dev.get("is_online", True) if nvr_dev else True
            child_devs = [d for d in devices if d.get("ip_address") in child_ips]
            online_child_count = sum(1 for c in child_devs if c.get("is_online", True))

            if self.matrix.is_nvr_failure(is_nvr_online, online_child_count, len(child_ips)):
                reports.append(
                    FaultAnalysisReport(
                        fault_type=FaultType.NVR_FAILURE,
                        severity="CRITICAL",
                        affected_ips=[nvr_ip] + child_ips,
                        root_cause_explanation=(
                            f"NVR recorder at {nvr_ip} is unresponsive, causing correlated stream "
                            f"failure across all {len(child_ips)} associated camera channels."
                        ),
                        recommended_remediation=(
                            "Reboot NVR hardware or restart video recording daemon. "
                            "Verify NVR internal PoE switch power delivery and storage array health."
                        ),
                        requires_operator_approval=True,
                        remediation_action_id="REMEDIATE-NVR-RESTART",
                    )
                )

        # Rule 3: Check Isolated Camera Failures
        total_devs = len(devices)
        online_devs = sum(1 for d in devices if d.get("is_online", True))
        subnet_ratio = (online_devs / total_devs) if total_devs > 0 else 1.0

        for dev in devices:
            ip = dev.get("ip_address", "")
            is_online = dev.get("is_online", True)
            dev_type = dev.get("device_type", "")

            if not is_online:
                if self.matrix.is_isolated_camera_failure(is_online, subnet_ratio):
                    reports.append(
                        FaultAnalysisReport(
                            fault_type=FaultType.CAMERA_HARDWARE_FAILURE,
                            severity="HIGH",
                            affected_ips=[ip],
                            root_cause_explanation=(
                                f"Camera {ip} failed reachability, while {round(subnet_ratio * 100)}% "
                                "of adjacent network devices operate normally. Suggests localized hardware or drop cable failure."
                            ),
                            recommended_remediation=(
                                f"Check physical RJ45 cable and PoE injector link status for camera {ip}. "
                                "Power-cycle the corresponding switch port if using a managed PoE switch."
                            ),
                            requires_operator_approval=True,
                            remediation_action_id=f"REMEDIATE-CAMERA-POWER-{ip}",
                        )
                    )

            # Rule 4: Authentication Failures
            if dev.get("auth_failed", False):
                reports.append(
                    FaultAnalysisReport(
                        fault_type=FaultType.AUTHENTICATION_FAILURE,
                        severity="MEDIUM",
                        affected_ips=[ip],
                        root_cause_explanation=(
                            f"Host {ip} responded to network probes but rejected RTSP/ONVIF credentials with 401/403."
                        ),
                        recommended_remediation=(
                            f"Open Camera Settings for {ip} and verify username/password against the camera credential registry."
                        ),
                        requires_operator_approval=True,
                        remediation_action_id=f"REMEDIATE-AUTH-UPDATE-{ip}",
                    )
                )

            # Rule 5: RTSP Stream Failure (Device online, but stream path or RTSP port failing)
            if is_online and dev.get("rtsp_failed", False):
                reports.append(
                    FaultAnalysisReport(
                        fault_type=FaultType.RTSP_STREAM_FAILURE,
                        severity="MEDIUM",
                        affected_ips=[ip],
                        root_cause_explanation=(
                            f"Camera {ip} is reachable via HTTP/ping, but RTSP streaming on port 554 failed or path is invalid."
                        ),
                        recommended_remediation=(
                            f"Verify RTSP streaming URI for {ip} in camera settings and check if camera encoding bitrate is supported."
                        ),
                        requires_operator_approval=True,
                        remediation_action_id=f"REMEDIATE-RTSP-CONFIG-{ip}",
                    )
                )

            # Rule 6: DNS Failure
            if dev.get("dns_failed", False):
                reports.append(
                    FaultAnalysisReport(
                        fault_type=FaultType.DNS_FAILURE,
                        severity="LOW",
                        affected_ips=[ip],
                        root_cause_explanation=(
                            f"Direct IP communication with {ip} succeeded, but local DNS reverse lookup failed."
                        ),
                        recommended_remediation=(
                            "Add DNS PTR reverse-lookup record on local DNS server or configure static IP in hosts table."
                        ),
                        requires_operator_approval=True,
                        remediation_action_id=f"REMEDIATE-DNS-RECORD-{ip}",
                    )
                )

        # Rule 7: Bandwidth Congestion Detection
        congested_ips = [
            d["ip_address"]
            for d in devices
            if self.matrix.is_congestion(d.get("latency_ms", 0.0), d.get("packet_loss_pct", 0.0))
        ]
        if len(congested_ips) >= 2 or (len(devices) > 0 and len(congested_ips) / len(devices) > 0.3):
            reports.append(
                FaultAnalysisReport(
                    fault_type=FaultType.BANDWIDTH_CONGESTION,
                    severity="HIGH",
                    affected_ips=congested_ips,
                    root_cause_explanation=(
                        f"{len(congested_ips)} devices are experiencing latency > 150ms or packet loss > 5%, "
                        "indicating switch uplink saturation or PoE switch buffer exhaustion."
                    ),
                    recommended_remediation=(
                        "Throttle camera bitrates from 8 Mbps to 4 Mbps, switch video stream codec from H.264 to H.265/HEVC, "
                        "or isolate camera traffic onto a dedicated Gigabit CCTV VLAN."
                    ),
                    requires_operator_approval=True,
                    remediation_action_id="REMEDIATE-BANDWIDTH-THROTTLE",
                )
            )

        if not reports:
            reports.append(
                FaultAnalysisReport(
                    fault_type=FaultType.NO_FAULT,
                    severity="INFO",
                    affected_ips=[],
                    root_cause_explanation="All monitored network devices, recorders, and gateways are operating within normal parameters.",
                    recommended_remediation="No remediation required. System operating normally.",
                    requires_operator_approval=False,
                    remediation_action_id="NONE",
                )
            )

        return reports
