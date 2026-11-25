"""
Network Security and Vulnerability Audit Engine.
Phase 11.1 (F-019, Release 1.1.1-alpha).
Performs non-intrusive security posture inspection with verified CVE mappings,
authoritative source references, advisory dates, and strict confidence scoring.
Distinguishes RTSP control encryption from RTP media encryption, and
endpoint accessibility from unauthenticated control access.
"""

import re
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from core.logging.logger import get_logger

logger = get_logger("security_audit")


class AuditSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class CVEConfidence(str, Enum):
    CONFIRMED_VULNERABLE = "CONFIRMED_VULNERABLE"
    POTENTIALLY_VULNERABLE = "POTENTIALLY_VULNERABLE"
    UNAFFECTED = "UNAFFECTED"
    NO_MATCH = "NO_MATCH"


@dataclass
class SecurityIssue:
    """Represents a specific verified security weakness or configuration defect."""
    check_id: str
    title: str
    description: str
    severity: AuditSeverity
    recommendation: str
    affected_protocol: str
    affected_port: Optional[int] = None
    cve_id: Optional[str] = None
    confidence: str = "HIGH"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class CVEFinding:
    """Represents a verified CVE vulnerability finding with authoritative attribution."""
    cve_id: str
    vendor: str
    model: str
    affected_versions: str
    detected_version: str
    cvss_score: float
    confidence: str  # CONFIRMED_VULNERABLE, POTENTIALLY_VULNERABLE, UNAFFECTED
    description: str
    mitigation: str
    source_url: str
    advisory_date: str
    status_note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SecurityAuditReport:
    """Comprehensive security audit report for a network CCTV host."""
    ip_address: str
    hostname: str = ""
    mac_address: str = "Unknown"
    vendor: str = "Unknown"
    model: str = "Unknown"
    firmware_version: str = "Unknown"
    security_score: int = 100  # 0 to 100
    grade: str = "A"  # A, B, C, D, F
    issues: List[SecurityIssue] = field(default_factory=list)
    cve_findings: List[CVEFinding] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "mac_address": self.mac_address,
            "vendor": self.vendor,
            "model": self.model,
            "firmware_version": self.firmware_version,
            "security_score": self.security_score,
            "grade": self.grade,
            "issues": [i.to_dict() for i in self.issues],
            "cve_findings": [c.to_dict() for c in self.cve_findings],
            "timestamp": self.timestamp,
        }


# Authoritative CCTV CVE Reference Database (Strictly Verified)
CCTV_CVE_DATABASE: List[Dict[str, Any]] = [
    {
        "cve_id": "CVE-2021-36260",
        "vendor": "Hikvision",
        "title": "Hikvision Web Server Command Injection",
        "cvss": 9.8,
        "affected_models": ["DS-2CD", "DS-2DE", "DS-2DF", "DS-2DY", "DS-2PT", "DS-76", "DS-77", "DS-86", "DS-96", "iDS-"],
        "affected_versions": "< V5.5.800",
        "fixed_version": "V5.5.800",
        "description": "Command injection vulnerability in the web server of certain Hikvision products due to insufficient input validation. Attackers can execute arbitrary commands with root privileges via crafted messages.",
        "mitigation": "Update firmware immediately to V5.5.800, V5.7.3, or later official release from Hikvision.",
        "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2021-36260",
        "advisory_date": "2021-09-22",
    },
    {
        "cve_id": "CVE-2021-33044",
        "vendor": "Dahua Technology",
        "title": "Dahua Identity Authentication Bypass",
        "cvss": 9.8,
        "affected_models": ["IPC-", "NVR", "VTH", "SD"],
        "affected_versions": "Firmware builds prior to August 2021",
        "fixed_version": "August 2021 security release",
        "description": "Authentication bypass vulnerability during identity authentication interaction on specified Dahua IP camera and NVR product lines.",
        "mitigation": "Apply official Dahua security patch firmware released August 2021 or later.",
        "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2021-33044",
        "advisory_date": "2021-09-08",
    },
    {
        "cve_id": "CVE-2020-25078",
        "vendor": "D-Link",
        "title": "D-Link DCS Camera Unauthenticated Administrator Password Disclosure",
        "cvss": 7.5,
        "affected_models": ["DCS-2530L", "DCS-2670L"],
        "affected_versions": "DCS-2530L <= 1.05.02, DCS-2670L <= 2.02.04",
        "fixed_version": "DCS-2530L 1.06.01, DCS-2670L 2.03.01",
        "description": "Unauthenticated administrator password disclosure vulnerability in D-Link DCS-2530L and DCS-2670L cameras allowing remote attackers to retrieve admin credentials via a direct request to /config/getuser.cgi.",
        "mitigation": "Update to firmware version 1.06.01 (DCS-2530L) or 2.03.01 (DCS-2670L), or isolate camera on private unrouted VLAN.",
        "source_url": "https://www.cve.org/CVERecord?id=CVE-2020-25078",
        "advisory_date": "2020-09-02",
    },
    {
        "cve_id": "CVE-2022-30563",
        "vendor": "Dahua Technology",
        "title": "Dahua ONVIF WS-UsernameToken Authentication Replay",
        "cvss": 7.5,
        "affected_models": ["IPC-", "SD", "NVR"],
        "affected_versions": "Firmware builds prior to June 2022",
        "fixed_version": "June 2022 security release",
        "description": "Flaw in ONVIF WS-UsernameToken authentication implementation in Dahua devices allowing attackers to capture credentials hash in unencrypted HTTP/ONVIF packets and replay them to gain unauthorized administrative access.",
        "mitigation": "Update Dahua camera firmware to June 2022 or later; disable unencrypted HTTP/ONVIF and enforce HTTPS for ONVIF communication.",
        "source_url": "https://www.dahuasecurity.com/about-dahua/news-events/notice/1017",
        "advisory_date": "2022-06-29",
    },
    {
        "cve_id": "CVE-2023-1518",
        "vendor": "CP PLUS",
        "title": "CP PLUS KVMS Pro Management Software Credential Exposure",
        "cvss": 6.5,
        "affected_models": ["KVMS Pro", "KVMS_PRO"],
        "affected_versions": "<= 2.01.0.T.190521",
        "fixed_version": "KVMS Pro 2.02 or newer",
        "description": "Cleartext transmission and local credential storage exposure in CP PLUS KVMS Pro management software. Only applicable to the KVMS Pro client application, not to standalone CP PLUS IP cameras.",
        "mitigation": "Upgrade KVMS Pro client installation to latest version and enforce encrypted credential storage.",
        "source_url": "https://nvd.nist.gov/vuln/detail/CVE-2023-1518",
        "advisory_date": "2023-03-20",
    },
]


def _parse_version_tuple(ver_str: str) -> Tuple[int, ...]:
    """Extracts integer components from a version string (e.g. 'V5.4.5' -> (5, 4, 5))."""
    nums = re.findall(r"\d+", ver_str)
    return tuple(int(n) for n in nums) if nums else (0,)


def evaluate_firmware_vulnerability(
    cve_id: str,
    detected_ver: str,
    target_rule: str,
) -> Tuple[CVEConfidence, str]:
    """
    Evaluates detected firmware against a target vulnerability rule.
    Returns (CVEConfidence, status_note).
    """
    if not detected_ver or detected_ver.lower() in ("unknown", "none", ""):
        return (
            CVEConfidence.POTENTIALLY_VULNERABLE,
            "FIRMWARE VERSION UNKNOWN — EXPOSURE UNCONFIRMED. Verify physical camera firmware build.",
        )

    # 1. Hikvision CVE-2021-36260 rule: < V5.5.800
    if cve_id == "CVE-2021-36260":
        detected_tuple = _parse_version_tuple(detected_ver)
        fixed_tuple = (5, 5, 800)
        # Compare (major, minor, patch)
        if detected_tuple < fixed_tuple:
            return (
                CVEConfidence.CONFIRMED_VULNERABLE,
                f"Confirmed vulnerable firmware build ({detected_ver} < V5.5.800). Remote command injection exposed.",
            )
        else:
            return (
                CVEConfidence.UNAFFECTED,
                f"Firmware version ({detected_ver} >= V5.5.800) is patched against CVE-2021-36260.",
            )

    # 2. Dahua CVE-2021-33044 rule: builds prior to August 2021 (2021-08-01)
    if cve_id == "CVE-2021-33044":
        # Check for year/date string in build e.g. '20210715' or '210715' or '2.800'
        date_match = re.search(r"(?:20)?(2[0-9])([0-1][0-9])([0-3][0-9])", detected_ver)
        if date_match:
            year = int("20" + date_match.group(1))
            month = int(date_match.group(2))
            if year < 2021 or (year == 2021 and month < 8):
                return (
                    CVEConfidence.CONFIRMED_VULNERABLE,
                    f"Confirmed vulnerable Dahua firmware build date ({year}-{month:02d} prior to 2021-08).",
                )
            else:
                return (
                    CVEConfidence.UNAFFECTED,
                    f"Dahua firmware build ({year}-{month:02d}) is patched against CVE-2021-33044.",
                )
        # If version string like V2.800 < V2.820
        detected_tuple = _parse_version_tuple(detected_ver)
        if detected_tuple and detected_tuple[0] < 3:
            return (
                CVEConfidence.CONFIRMED_VULNERABLE,
                f"Confirmed vulnerable legacy Dahua baseline ({detected_ver}). Authentication bypass exposed.",
            )

    # 3. D-Link CVE-2020-25078 rule: DCS-2530L <= 1.05.02, DCS-2670L <= 2.02.04
    if cve_id == "CVE-2020-25078":
        detected_tuple = _parse_version_tuple(detected_ver)
        # If major version 1 (DCS-2530L)
        if detected_tuple and detected_tuple[0] == 1:
            if detected_tuple <= (1, 5, 2):
                return (
                    CVEConfidence.CONFIRMED_VULNERABLE,
                    f"Confirmed vulnerable D-Link DCS-2530L firmware ({detected_ver} <= 1.05.02). Password disclosure exposed.",
                )
            return (CVEConfidence.UNAFFECTED, f"D-Link DCS-2530L firmware ({detected_ver}) is patched.")
        elif detected_tuple and detected_tuple[0] == 2:
            if detected_tuple <= (2, 2, 4):
                return (
                    CVEConfidence.CONFIRMED_VULNERABLE,
                    f"Confirmed vulnerable D-Link DCS-2670L firmware ({detected_ver} <= 2.02.04). Password disclosure exposed.",
                )
            return (CVEConfidence.UNAFFECTED, f"D-Link DCS-2670L firmware ({detected_ver}) is patched.")

    # 4. Dahua CVE-2022-30563 rule: builds prior to June 2022
    if cve_id == "CVE-2022-30563":
        date_match = re.search(r"(?:20)?(2[0-9])([0-1][0-9])([0-3][0-9])", detected_ver)
        if date_match:
            year = int("20" + date_match.group(1))
            month = int(date_match.group(2))
            if year < 2022 or (year == 2022 and month < 6):
                return (
                    CVEConfidence.CONFIRMED_VULNERABLE,
                    f"Confirmed vulnerable Dahua ONVIF build ({year}-{month:02d} prior to 2022-06). Replay attack exposed.",
                )
            return (CVEConfidence.UNAFFECTED, f"Dahua ONVIF firmware ({year}-{month:02d}) is patched.")
        detected_tuple = _parse_version_tuple(detected_ver)
        if detected_tuple and detected_tuple[0] < 3:
            return (
                CVEConfidence.CONFIRMED_VULNERABLE,
                f"Confirmed vulnerable Dahua firmware ({detected_ver}). ONVIF replay attack exposed.",
            )

    # 5. CP PLUS KVMS Pro CVE-2023-1518 rule: <= 2.01.0.T.190521
    if cve_id == "CVE-2023-1518":
        detected_tuple = _parse_version_tuple(detected_ver)
        if detected_tuple <= (2, 1, 0):
            return (
                CVEConfidence.CONFIRMED_VULNERABLE,
                f"Confirmed vulnerable KVMS Pro version ({detected_ver} <= 2.01.0). Credential exposure exposed.",
            )
        return (CVEConfidence.UNAFFECTED, f"KVMS Pro version ({detected_ver}) is patched.")

    return (
        CVEConfidence.POTENTIALLY_VULNERABLE,
        f"Firmware {detected_ver} requires manual verification against security advisory.",
    )


class NetworkSecurityAuditor:
    """
    Non-intrusive security auditor evaluating CCTV devices against
    security best practices, transport encryption, exposed services, and verified CVEs.
    """

    @classmethod
    def audit_device(
        cls,
        ip_address: str,
        open_ports: Optional[List[int]] = None,
        protocols: Optional[List[str]] = None,
        vendor: str = "Unknown",
        model: str = "Unknown",
        firmware_version: str = "Unknown",
        rtsp_control_encrypted: bool = False,
        rtp_media_encrypted: bool = False,
        srtp_available: bool = False,
        has_onvif_unauth: bool = False,
        default_credentials_detected: bool = False,
    ) -> SecurityAuditReport:
        """
        Conducts a non-intrusive security posture audit on a network host.
        Distinguishes RTSP control from RTP media transport, and anonymous endpoint
        reachability from unauthenticated control access.
        """
        if open_ports is None:
            open_ports = []
        if protocols is None:
            protocols = []

        issues: List[SecurityIssue] = []
        cve_findings: List[CVEFinding] = []
        score = 100

        # Check 1A: RTSP Control Channel Encryption
        if (554 in open_ports or "RTSP" in protocols) and not rtsp_control_encrypted:
            issues.append(
                SecurityIssue(
                    check_id="SEC-001A",
                    title="Unencrypted RTSP Control Channel",
                    description="RTSP signaling is transmitted in plaintext over TCP port 554 without TLS encryption, allowing session hijacking or credential interception.",
                    severity=AuditSeverity.MEDIUM,
                    recommendation="Enable RTSPS (RTSP over TLS) on port 322 or tunnel video signaling through an encrypted IPsec/WireGuard VPN.",
                    affected_protocol="RTSP-CONTROL",
                    affected_port=554,
                    confidence="HIGH",
                )
            )
            score -= 10

        # Check 1B: RTP Media Stream Encryption
        if (554 in open_ports or "RTSP" in protocols) and not rtp_media_encrypted and not srtp_available:
            issues.append(
                SecurityIssue(
                    check_id="SEC-001B",
                    title="Unencrypted RTP Video Media Transport",
                    description="RTP payload streaming transmits raw video data without SRTP (Secure RTP) encryption, exposing video frames to local network packet capture.",
                    severity=AuditSeverity.MEDIUM,
                    recommendation="Enable SRTP media encryption (RTP/SAVP profile) in camera stream settings or isolate on a dedicated surveillance VLAN.",
                    affected_protocol="RTP-MEDIA",
                    confidence="HIGH",
                )
            )
            score -= 10

        # Check 2: Insecure HTTP Web Administration
        if (80 in open_ports or 8080 in open_ports) and 443 not in open_ports:
            issues.append(
                SecurityIssue(
                    check_id="SEC-002",
                    title="Insecure HTTP Web Management",
                    description="Web management portal is served over plaintext HTTP without HTTPS encryption, exposing credentials to local sniffing.",
                    severity=AuditSeverity.MEDIUM,
                    recommendation="Enable HTTPS on port 443, install a valid TLS certificate, and redirect HTTP requests to HTTPS.",
                    affected_protocol="HTTP",
                    affected_port=80,
                    confidence="HIGH",
                )
            )
            score -= 15

        # Check 3: Exposed Legacy Remote Management Ports
        if 23 in open_ports:
            issues.append(
                SecurityIssue(
                    check_id="SEC-003",
                    title="Exposed Telnet Remote Shell Port",
                    description="Telnet service (port 23) is open and accessible. Telnet transmits all commands and passwords in plaintext.",
                    severity=AuditSeverity.HIGH,
                    recommendation="Disable Telnet service in camera system configuration; use SSH or secure vendor API.",
                    affected_protocol="TELNET",
                    affected_port=23,
                    confidence="HIGH",
                )
            )
            score -= 25

        if 21 in open_ports:
            issues.append(
                SecurityIssue(
                    check_id="SEC-004",
                    title="Exposed FTP Service",
                    description="FTP service (port 21) is active on the device. Plaintext FTP allows credential sniffing and unauthorized snapshot access.",
                    severity=AuditSeverity.LOW,
                    recommendation="Disable FTP service unless required for offsite snapshot backup. Prefer SFTP or FTPS.",
                    affected_protocol="FTP",
                    affected_port=21,
                    confidence="HIGH",
                )
            )
            score -= 5

        # Check 4: Unauthenticated ONVIF Device Access
        if has_onvif_unauth:
            issues.append(
                SecurityIssue(
                    check_id="SEC-005",
                    title="Unauthenticated ONVIF Control Operations Permitted",
                    description="ONVIF service permits administrative or control operations without mandatory WS-UsernameToken authentication challenge.",
                    severity=AuditSeverity.CRITICAL,
                    recommendation="Enable mandatory authentication for ONVIF service in camera administrative settings.",
                    affected_protocol="ONVIF",
                    affected_port=80,
                    confidence="HIGH",
                )
            )
            score -= 35

        # Check 5: Default Credentials Risk Flag
        if default_credentials_detected:
            issues.append(
                SecurityIssue(
                    check_id="SEC-006",
                    title="Default or Factory Credentials Detected",
                    description="Device appears to be using factory default credentials or uninitialized setup state, posing immediate takeover risk.",
                    severity=AuditSeverity.CRITICAL,
                    recommendation="Immediately change administrator password to a strong, unique 16+ character passphrase.",
                    affected_protocol="AUTH",
                    confidence="HIGH",
                )
            )
            score -= 40

        # Check 6: Verified CCTV CVE Vulnerability Mapping
        for cve in CCTV_CVE_DATABASE:
            cve_vendor = cve["vendor"].lower()
            device_vendor = vendor.lower()

            # Rule: Match manufacturer profile
            if not (cve_vendor in device_vendor or (device_vendor in cve_vendor and len(device_vendor) > 3)):
                continue

            # Model Specific Matching Rule
            is_unknown_model = (not model) or model.lower() in ("unknown", "unknown model", "none", "", "generic")
            if is_unknown_model:
                # Never mark a device vulnerable based on manufacturer alone!
                continue

            target_models = cve["affected_models"]
            model_matched = any(m.lower() in model.lower() for m in target_models)
            if not model_matched:
                continue

            # Evaluate exact firmware version
            confidence_enum, status_note = evaluate_firmware_vulnerability(
                cve_id=cve["cve_id"],
                detected_ver=firmware_version,
                target_rule=cve["affected_versions"],
            )

            cve_finding = CVEFinding(
                cve_id=cve["cve_id"],
                vendor=cve["vendor"],
                model=model,
                affected_versions=cve["affected_versions"],
                detected_version=firmware_version,
                cvss_score=cve["cvss"],
                confidence=confidence_enum.value,
                description=f"{cve['description']} [{status_note}]",
                mitigation=cve["mitigation"],
                source_url=cve["source_url"],
                advisory_date=cve["advisory_date"],
                status_note=status_note,
            )
            cve_findings.append(cve_finding)

            # Deduct score strictly based on verified confidence
            if confidence_enum == CVEConfidence.CONFIRMED_VULNERABLE:
                score -= 30
            elif confidence_enum == CVEConfidence.POTENTIALLY_VULNERABLE:
                # Firmware unknown or exposure unconfirmed: informational penalty only (-5)
                score -= 5
            # For UNAFFECTED, deduction is 0

        # Clamp score
        final_score = max(0, min(100, score))

        # Determine Letter Grade
        if final_score >= 90:
            grade = "A"
        elif final_score >= 80:
            grade = "B"
        elif final_score >= 70:
            grade = "C"
        elif final_score >= 60:
            grade = "D"
        else:
            grade = "F"

        return SecurityAuditReport(
            ip_address=ip_address,
            vendor=vendor,
            model=model,
            firmware_version=firmware_version,
            security_score=final_score,
            grade=grade,
            issues=issues,
            cve_findings=cve_findings,
        )
