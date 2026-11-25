"""
Unit tests for Network Security and Vulnerability Audit (Phase 11.1 - F-019, Release 1.1.1-alpha).
Tests verified CVE mappings, authoritative source attribution, firmware matching accuracy,
confidence states, RTSP/RTP encryption separation, and CP PLUS / Axis correction.
"""

import pytest
from engines.network_engine.security_audit import (
    NetworkSecurityAuditor,
    SecurityAuditReport,
    AuditSeverity,
    CVEConfidence,
    SecurityIssue,
    CVEFinding,
    CCTV_CVE_DATABASE,
    evaluate_firmware_vulnerability,
)


def test_audit_insecure_protocols_disaggregation():
    """Verify separate checks for unencrypted RTSP control channel and RTP media transport."""
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.100",
        open_ports=[554, 80],
        protocols=["RTSP", "HTTP"],
        vendor="Generic Camera",
    )

    check_ids = [issue.check_id for issue in rep.issues]
    # SEC-001A (Unencrypted RTSP Control) and SEC-001B (Unencrypted RTP Media)
    assert "SEC-001A" in check_ids
    assert "SEC-001B" in check_ids
    assert "SEC-002" in check_ids  # Insecure HTTP
    assert rep.security_score == 65
    assert rep.grade == "D"


def test_audit_exposed_telnet():
    """Verify detection of obsolete, unencrypted Telnet port 23."""
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.101",
        open_ports=[23],
        protocols=["TELNET"],
        vendor="Legacy Camera",
    )

    check_ids = [issue.check_id for issue in rep.issues]
    assert "SEC-003" in check_ids
    telnet_issue = next(i for i in rep.issues if i.check_id == "SEC-003")
    assert telnet_issue.severity == AuditSeverity.HIGH
    assert telnet_issue.affected_port == 23


def test_audit_unauthenticated_onvif_and_default_creds():
    """Verify critical severity on unauthenticated ONVIF access and default credentials."""
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.102",
        has_onvif_unauth=True,
        default_credentials_detected=True,
    )

    check_ids = [issue.check_id for issue in rep.issues]
    assert "SEC-005" in check_ids  # Unauthenticated ONVIF
    assert "SEC-006" in check_ids  # Default credentials
    assert rep.grade == "F"


def test_cve_database_integrity_and_authoritative_sources():
    """Ensure all entries in CCTV_CVE_DATABASE have authoritative source URLs and advisory dates."""
    for data in CCTV_CVE_DATABASE:
        cve_id = data["cve_id"]
        assert cve_id.startswith("CVE-")
        assert "source_url" in data
        assert data["source_url"].startswith("https://")
        assert "advisory_date" in data
        assert len(data["advisory_date"]) == 10  # YYYY-MM-DD
        assert "cvss" in data
        assert 0.0 <= data["cvss"] <= 10.0


def test_cve_pimcore_3820_removed_from_database():
    """CVE-2023-3820 (Pimcore SQL injection) must NOT be present in CCTV CVE database."""
    cve_ids = [c["cve_id"] for c in CCTV_CVE_DATABASE]
    assert "CVE-2023-3820" not in cve_ids
    for data in CCTV_CVE_DATABASE:
        assert "Pimcore" not in data.get("description", "")
        assert "Pimcore" not in data.get("title", "")


def test_cve_2022_30563_attributed_to_dahua_not_axis():
    """CVE-2022-30563 is a Dahua ONVIF authentication replay issue, NOT Axis Communications."""
    entry = next(c for c in CCTV_CVE_DATABASE if c["cve_id"] == "CVE-2022-30563")
    assert "Dahua" in entry["vendor"]
    assert "Axis" not in entry["vendor"]

    # Auditing an Axis camera must NOT produce CVE-2022-30563
    rep_axis = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.150",
        vendor="Axis Communications",
        model="AXIS M3045-V",
        firmware_version="9.80.3",
    )
    cve_ids_axis = [c.cve_id for c in rep_axis.cve_findings]
    assert "CVE-2022-30563" not in cve_ids_axis

    # Auditing a Dahua camera matching the model range with vulnerable firmware produces CVE-2022-30563
    rep_dahua = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.151",
        vendor="Dahua Technology",
        model="IPC-HDBW4231E-AS",
        firmware_version="2.800.0000000.10.R",
    )
    cve_ids_dahua = [c.cve_id for c in rep_dahua.cve_findings]
    assert "CVE-2022-30563" in cve_ids_dahua


def test_cve_2020_25078_dlink_password_disclosure_not_rce():
    """CVE-2020-25078 must be classified as password disclosure, NOT remote code execution."""
    entry = next(c for c in CCTV_CVE_DATABASE if c["cve_id"] == "CVE-2020-25078")
    assert "password disclosure" in entry["description"].lower()
    assert "remote code execution" not in entry["description"].lower()
    assert entry["cvss"] == 7.5

    rep_dlink = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.160",
        vendor="D-Link",
        model="DCS-2530L",
        firmware_version="1.00.00",
    )
    finding = next((c for c in rep_dlink.cve_findings if c.cve_id == "CVE-2020-25078"), None)
    assert finding is not None
    assert "password disclosure" in finding.description.lower()
    assert finding.confidence == CVEConfidence.CONFIRMED_VULNERABLE.value


def test_cve_2023_1518_restricted_to_cpplus_kvms_pro_only():
    """CVE-2023-1518 applies to CP PLUS KVMS Pro software, NOT IP cameras."""
    # Auditing a generic CP PLUS camera must NOT trigger CVE-2023-1518
    rep_cam = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.170",
        vendor="CP PLUS",
        model="CP-UNC-TA21PL3",
        firmware_version="2.800.0000000.1.R",
    )
    cve_ids_cam = [c.cve_id for c in rep_cam.cve_findings]
    assert "CVE-2023-1518" not in cve_ids_cam

    # Auditing a host running KVMS Pro does match
    rep_vms = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.171",
        vendor="CP PLUS",
        model="KVMS Pro",
        firmware_version="2.01.0",
    )
    cve_ids_vms = [c.cve_id for c in rep_vms.cve_findings]
    assert "CVE-2023-1518" in cve_ids_vms


def test_firmware_version_matching_precision():
    """Verify exact version comparison against affected range for Hikvision CVE-2021-36260."""
    # 1. Version < 5.5.800 -> CONFIRMED_VULNERABLE
    rep_vuln = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.200",
        vendor="Hikvision",
        model="DS-2CD2042WD-I",
        firmware_version="V5.4.5",
    )
    finding_vuln = next(c for c in rep_vuln.cve_findings if c.cve_id == "CVE-2021-36260")
    assert finding_vuln.confidence == CVEConfidence.CONFIRMED_VULNERABLE.value

    # 2. Version >= 5.5.800 -> UNAFFECTED
    rep_safe = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.201",
        vendor="Hikvision",
        model="DS-2CD2042WD-I",
        firmware_version="V5.5.800",
    )
    finding_safe = next((c for c in rep_safe.cve_findings if c.cve_id == "CVE-2021-36260"), None)
    assert finding_safe is not None
    assert finding_safe.confidence == CVEConfidence.UNAFFECTED.value

    # 3. Unknown firmware version -> POTENTIALLY_VULNERABLE with unconfirmed notice
    rep_unk = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.202",
        vendor="Hikvision",
        model="DS-2CD2042WD-I",
        firmware_version="Unknown",
    )
    finding_unk = next(c for c in rep_unk.cve_findings if c.cve_id == "CVE-2021-36260")
    assert finding_unk.confidence == CVEConfidence.POTENTIALLY_VULNERABLE.value
    assert "FIRMWARE VERSION UNKNOWN — EXPOSURE UNCONFIRMED" in finding_unk.status_note


def test_vendor_alone_never_flags_vulnerability():
    """A device must NEVER be marked vulnerable based on manufacturer alone with unknown model."""
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.210",
        vendor="Hikvision",
        model="Unknown Model",
        firmware_version="Unknown",
    )
    assert len(rep.cve_findings) == 0


def test_clean_device_security_score():
    """A hardened device with only HTTPS port 443 gets a score of 100, Grade A, and no CVEs."""
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.50",
        open_ports=[443],
        protocols=["HTTPS"],
        vendor="Hardened Security Node",
    )
    assert rep.security_score == 100
    assert rep.grade == "A"
    assert len(rep.issues) == 0
    assert len(rep.cve_findings) == 0
