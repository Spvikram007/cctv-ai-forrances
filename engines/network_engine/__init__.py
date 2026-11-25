"""
Network Intelligence Engine for CCTV AI Intelligence Platform.
Phase 11 (F-019, Release 1.1.0-alpha).
"""

from engines.network_engine.scanner import (
    DeviceType,
    DeviceStatus,
    DiscoveredNetworkDevice,
    NetworkScanner,
    validate_cidr_block,
    compute_scan_scope,
    record_scan_audit,
    ScanScope,
    get_default_gateway,
    get_local_subnets,
)
from engines.network_engine.diagnostics import (
    DeviceDiagnosticEngine,
    DiagnosticResult,
    ComprehensiveDeviceAuditReport,
    DiagnosticRootCause,
)
from engines.network_engine.monitor import (
    NetworkPerformanceMonitor,
    TelemetrySample,
    DeviceTelemetryHistory,
)
from engines.network_engine.security_audit import (
    NetworkSecurityAuditor,
    SecurityAuditReport,
    SecurityIssue,
    AuditSeverity,
    CVEFinding,
    CVEConfidence,
)
from engines.network_engine.fault_analyzer import (
    AutomatedFaultAnalyzer,
    FaultType,
    FaultAnalysisReport,
    FaultIsolationMatrix,
)

__all__ = [
    "DeviceType",
    "DeviceStatus",
    "DiscoveredNetworkDevice",
    "NetworkScanner",
    "validate_cidr_block",
    "compute_scan_scope",
    "record_scan_audit",
    "ScanScope",
    "get_default_gateway",
    "get_local_subnets",
    "DeviceDiagnosticEngine",
    "DiagnosticResult",
    "ComprehensiveDeviceAuditReport",
    "DiagnosticRootCause",
    "NetworkPerformanceMonitor",
    "TelemetrySample",
    "DeviceTelemetryHistory",
    "NetworkSecurityAuditor",
    "SecurityAuditReport",
    "SecurityIssue",
    "AuditSeverity",
    "CVEFinding",
    "CVEConfidence",
    "AutomatedFaultAnalyzer",
    "FaultType",
    "FaultAnalysisReport",
    "FaultIsolationMatrix",
]
