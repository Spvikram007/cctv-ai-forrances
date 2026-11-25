"""
Unit tests for Network Security and Vulnerability Audit (Phase 11 - F-019).
"""

import pytest
from engines.network_engine.security_audit import (
    NetworkSecurityAuditor,
    SecurityAuditReport,
    AuditSeverity,
    SecurityIssue,
)


def test_audit_insecure_protocols():
    # RTSP unencrypted + HTTP unencrypted
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.100",
        open_ports=[554, 80],
        protocols=["RTSP", "HTTP"],
        vendor="Generic Camera",
    )

    check_ids = [issue.check_id for issue in rep.issues]
    assert "SEC-001" in check_ids  # Unencrypted RTSP
    assert "SEC-002" in check_ids  # Insecure HTTP
    assert rep.security_score == 70
    assert rep.grade == "C"


def test_audit_exposed_telnet():
    # Telnet port 23
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
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.102",
        has_onvif_unauth=True,
        default_credentials_detected=True,
    )

    check_ids = [issue.check_id for issue in rep.issues]
    assert "SEC-005" in check_ids  # Unauthenticated ONVIF
    assert "SEC-006" in check_ids  # Default credentials
    assert rep.grade == "F"


def test_cve_mapping_confidence_scoring():
    # 1. Exact firmware match -> HIGH confidence
    rep_high = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.200",
        vendor="Hikvision",
        model="DS-2CD2042WD-I",
        firmware_version="V5.4.5",
    )
    assert len(rep_high.cve_findings) > 0
    cve_hik = next(c for c in rep_high.cve_findings if c.cve_id == "CVE-2021-36260")
    assert cve_hik.confidence == "HIGH"

    # 2. Unknown firmware match -> MEDIUM confidence
    rep_med = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.201",
        vendor="Dahua Technology",
        model="IPC-HFW1230S",
        firmware_version="Unknown",
    )
    assert len(rep_med.cve_findings) > 0
    cve_dahua = next(c for c in rep_med.cve_findings if c.cve_id == "CVE-2021-33044")
    assert cve_dahua.confidence == "MEDIUM"

    # 3. Only vendor profile matched, unknown model & firmware -> LOW confidence
    rep_low = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.202",
        vendor="Axis Communications",
        model="Unknown",
        firmware_version="Unknown",
    )
    assert len(rep_low.cve_findings) > 0
    cve_axis = next(c for c in rep_low.cve_findings if c.cve_id == "CVE-2022-30563")
    assert cve_axis.confidence == "LOW"


def test_clean_device_security_score():
    rep = NetworkSecurityAuditor.audit_device(
        ip_address="192.168.1.50",
        open_ports=[443],  # HTTPS only
        protocols=["HTTPS"],
        vendor="Hardened Security Node",
    )
    assert rep.security_score == 100
    assert rep.grade == "A"
    assert len(rep.issues) == 0
    assert len(rep.cve_findings) == 0
