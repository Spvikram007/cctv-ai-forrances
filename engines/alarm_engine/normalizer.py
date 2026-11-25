"""
Event Normalization Engine for Alarm Management.
Phase 12 (F-046, Change ID: CHG-20261125-009).

Translates heterogeneous subsystem event payloads into standard NormalizedAlarmEvents.
"""

import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from engines.alarm_engine.enums import (
    AlarmSeverity,
    AlarmPriority,
    AlarmCategory,
    SubsystemSource,
)


@dataclass
class NormalizedAlarmEvent:
    """Standardized internal representation of an event ready for alarm processing."""
    event_id: str
    source_subsystem: str
    event_type: str
    title: str
    description: str
    category: AlarmCategory
    severity: AlarmSeverity
    priority: AlarmPriority
    camera_id: Optional[str] = None
    site_id: Optional[str] = None
    zone_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: Optional[float] = None
    evidence_refs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    dedup_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source_subsystem": self.source_subsystem,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "severity": self.severity.value,
            "priority": self.priority.value,
            "camera_id": self.camera_id,
            "site_id": self.site_id,
            "zone_id": self.zone_id,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "metadata": self.metadata,
            "dedup_key": self.dedup_key,
        }


class EventNormalizer:
    """Normalizes raw event payloads from various platform subsystems."""

    @classmethod
    def normalize(cls, source_subsystem: str, event_type: str, data: Dict[str, Any]) -> NormalizedAlarmEvent:
        event_id = str(data.get("event_id") or data.get("id") or uuid.uuid4())
        camera_id = data.get("channel_id") or data.get("camera_id") or data.get("device_id")
        site_id = data.get("site_id")
        zone_id = data.get("zone_id") or data.get("rule_id")
        confidence = data.get("confidence")

        # Parse timestamp safely
        ts = data.get("timestamp")
        if isinstance(ts, (int, float)):
            event_ts = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            try:
                event_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                event_ts = datetime.now(timezone.utc)
        elif isinstance(ts, datetime):
            event_ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        else:
            event_ts = datetime.now(timezone.utc)

        # Collect evidence references
        evidence_refs: Dict[str, Any] = {}
        if "snapshot_path" in data:
            evidence_refs["snapshot_path"] = data["snapshot_path"]
        if "recording_segment_id" in data:
            evidence_refs["recording_segment_id"] = data["recording_segment_id"]
        if "segment_id" in data:
            evidence_refs["recording_segment_id"] = data["segment_id"]
        if "bbox" in data:
            evidence_refs["bbox"] = data["bbox"]
        if "plate_text" in data:
            evidence_refs["plate_text"] = data["plate_text"]
        if "identity_id" in data:
            evidence_refs["identity_id"] = data["identity_id"]
        if "evidence_id" in data:
            evidence_refs["evidence_id"] = data["evidence_id"]

        # Default classification
        category = AlarmCategory.SECURITY
        severity = AlarmSeverity.MEDIUM
        priority = AlarmPriority.P3_NORMAL
        title = data.get("title") or f"{event_type.replace('_', ' ').title()}"
        description = data.get("description") or f"Subsystem {source_subsystem} triggered {event_type} event on camera {camera_id or 'unknown'}."

        subsystem_upper = source_subsystem.upper()

        # 1. Analytics & Behaviour Events
        if subsystem_upper in ("ANALYTICS", "BEHAVIOUR"):
            rule_type = (data.get("rule_type") or event_type).upper()
            if "INTRUSION" in rule_type:
                title = f"Intrusion Alert: Camera {camera_id}"
                description = f"Unauthorized intrusion detected in surveillance zone {zone_id or 'Default'}."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.SECURITY
            elif "LINE_CROSSING" in rule_type or "TRIPWIRE" in rule_type:
                title = f"Tripwire Crossing: Camera {camera_id}"
                description = f"Virtual tripwire crossed: direction {data.get('direction', 'bidirectional')}."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P3_NORMAL
                category = AlarmCategory.SECURITY
            elif "LOITERING" in rule_type:
                dwell = data.get("dwell_time_sec", 0.0)
                title = f"Loitering Alert: Camera {camera_id}"
                description = f"Target loitering in zone for {dwell:.1f} seconds."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P3_NORMAL
                category = AlarmCategory.SECURITY
            elif "CROWD" in rule_type:
                density = data.get("density_people_m2", 0.0)
                is_crit = density >= 5.0 or data.get("severity") == "CRITICAL"
                title = f"Crowd Anomaly ({density:.1f}/m²): Camera {camera_id}"
                description = f"Crowd density threshold exceeded: {density:.2f} people/m² in monitored area."
                severity = AlarmSeverity.HIGH if is_crit else AlarmSeverity.MEDIUM
                priority = AlarmPriority.P2_HIGH if is_crit else AlarmPriority.P3_NORMAL
                category = AlarmCategory.SAFETY
            elif "FALL" in rule_type:
                title = f"Fall Detected: Camera {camera_id}"
                description = "Human fall posture and rapid vertical descent confirmed. Immediate safety verification required."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P1_URGENT
                category = AlarmCategory.SAFETY
            elif "ABANDONED" in rule_type or "STATIONARY" in rule_type:
                dwell = data.get("dwell_time_sec", 60.0)
                title = f"Unattended Object: Camera {camera_id}"
                description = f"Stationary object unattended for {dwell:.0f} seconds without owner proximity."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.SECURITY
            elif "REMOVED" in rule_type:
                title = f"Object Removed / Theft Alert: Camera {camera_id}"
                description = "Monitored asset removed from designated zone."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.SECURITY
            elif "WRONG_WAY" in rule_type or "DIRECTION" in rule_type:
                title = f"Wrong-Way Movement: Camera {camera_id}"
                description = "Sustained directional movement against authorized flow."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P3_NORMAL
                category = AlarmCategory.SAFETY

        # 2. ANPR & Face Biometrics Events
        elif subsystem_upper in ("ANPR", "FACE"):
            if "WATCHLIST" in event_type.upper():
                plate = data.get("plate_text", "Unknown")
                wl_cat = data.get("watchlist_category", "Stolen/Wanted")
                title = f"Watchlist Plate Alert: {plate}"
                description = f"Vehicle plate {plate} matched in {wl_cat} watchlist on camera {camera_id}."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P1_URGENT
                category = AlarmCategory.SECURITY
            elif "CANDIDATE" in event_type.upper() or "MATCH" in event_type.upper():
                name = data.get("identity_name", "Known Person")
                title = f"Face Recognition Candidate: {name}"
                description = f"Identity {name} matched with {data.get('similarity', 0.0)*100:.1f}% similarity on camera {camera_id}."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.SECURITY
            else:
                title = f"Biometric Event on Camera {camera_id}"
                category = AlarmCategory.SECURITY

        # 3. Stream & Video Engine Events
        elif subsystem_upper == "STREAM":
            if "DISCONNECTED" in event_type.upper():
                title = f"Camera Stream Offline: Camera {camera_id}"
                description = f"Video stream disconnected on camera {camera_id}. Reconnect attempts initiated."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.HARDWARE
            elif "RECOVERED" in event_type.upper():
                title = f"Camera Stream Recovered: Camera {camera_id}"
                description = f"Video stream successfully re-established on camera {camera_id}."
                severity = AlarmSeverity.INFORMATIONAL
                priority = AlarmPriority.P4_LOW
                category = AlarmCategory.OPERATIONAL
            elif "FROZEN" in event_type.upper():
                duration = data.get("duration", 0.0)
                title = f"Video Stream Frozen: Camera {camera_id}"
                description = f"Frozen video frames detected for {duration:.1f} seconds on camera {camera_id}."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P3_NORMAL
                category = AlarmCategory.OPERATIONAL

        # 4. Network Intelligence Events
        elif subsystem_upper == "NETWORK":
            fault_type = (data.get("fault_type") or event_type).upper()
            if "GATEWAY" in fault_type or "OUTAGE" in fault_type:
                title = "Network Gateway Offline Outage"
                description = f"Default gateway {data.get('gateway_ip', '192.168.1.1')} unreachable. Downstream camera communication severed."
                severity = AlarmSeverity.CRITICAL
                priority = AlarmPriority.P1_URGENT
                category = AlarmCategory.NETWORK
            elif "SWITCH" in fault_type:
                title = f"Network Switch Failure: {data.get('switch_ip', 'Switch')}"
                description = "Cluster of cameras attached to switch reported simultaneous packet drop."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P1_URGENT
                category = AlarmCategory.NETWORK
            elif "CONGESTION" in fault_type:
                title = "Network Bandwidth Congestion"
                description = "Severe network congestion detected: RTT latency > 150ms and sustained packet loss."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P3_NORMAL
                category = AlarmCategory.NETWORK
            elif "SECURITY" in fault_type or "CVE" in fault_type:
                cve = data.get("cve_id", "CVE Finding")
                title = f"Network Security Vulnerability: {cve}"
                description = f"Host {data.get('ip_address', 'Device')} confirmed vulnerable: {data.get('vulnerability_title', cve)}."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.NETWORK
            elif "DUPLICATE_IP" in fault_type:
                title = f"Duplicate IP Collision: {data.get('ip_address')}"
                description = "Multiple MAC addresses conflicting over a single surveillance IP address."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.NETWORK

        # 5. Storage & Recording Engine Events
        elif subsystem_upper == "STORAGE":
            if "CRITICAL" in event_type.upper() or "FULL" in event_type.upper():
                title = "Storage Volume Critical / Disk Full"
                description = f"Storage volume {data.get('volume_path', 'Drive')} exceeded 95% threshold. Video recording at risk."
                severity = AlarmSeverity.CRITICAL
                priority = AlarmPriority.P1_URGENT
                category = AlarmCategory.HARDWARE
            elif "ERROR" in event_type.upper() or "FAILURE" in event_type.upper():
                title = f"Recording Interruption on Camera {camera_id}"
                description = f"Video recording failed on camera {camera_id}: {data.get('error', 'I/O failure')}."
                severity = AlarmSeverity.HIGH
                priority = AlarmPriority.P2_HIGH
                category = AlarmCategory.HARDWARE
            else:
                title = "Storage Volume Low Warning"
                description = f"Storage volume {data.get('volume_path', 'Drive')} approaching retention quota."
                severity = AlarmSeverity.MEDIUM
                priority = AlarmPriority.P3_NORMAL
                category = AlarmCategory.HARDWARE

        # 6. Digital Forensics Events
        elif subsystem_upper in ("FORENSIC", "FORENSICS"):
            title = "Digital Forensic Integrity Failure"
            ev_id = data.get("evidence_id")
            ev_str = f" for evidence package '{ev_id}'" if ev_id else ""
            description = f"Cryptographic SHA-256 seal mismatch or evidence tampering detected{ev_str}: {data.get('details', 'Verification failure')}."
            severity = AlarmSeverity.CRITICAL
            priority = AlarmPriority.P1_URGENT
            category = AlarmCategory.FORENSIC

        # 7. System Health Events
        elif subsystem_upper == "SYSTEM":
            title = f"System Resource Alert: {event_type}"
            description = data.get("message") or "System resource constraint detected on server."
            severity = AlarmSeverity.MEDIUM
            priority = AlarmPriority.P3_NORMAL
            category = AlarmCategory.OPERATIONAL

        # Override severity/priority if explicitly supplied in payload
        if "severity" in data:
            try:
                severity = AlarmSeverity(str(data["severity"]).upper())
            except Exception:
                pass
        if "priority" in data:
            try:
                priority = AlarmPriority(str(data["priority"]).upper())
            except Exception:
                pass

        # Formulate stable deduplication key
        # E.g. "STREAM:DISCONNECTED:camera_1" or "ANALYTICS:INTRUSION:camera_1:zone_north"
        dedup_parts = [subsystem_upper, event_type.upper()]
        if camera_id:
            dedup_parts.append(str(camera_id))
        if zone_id:
            dedup_parts.append(str(zone_id))
        dedup_key = ":".join(dedup_parts)

        return NormalizedAlarmEvent(
            event_id=event_id,
            source_subsystem=source_subsystem,
            event_type=event_type,
            title=title,
            description=description,
            category=category,
            severity=severity,
            priority=priority,
            camera_id=camera_id,
            site_id=site_id,
            zone_id=zone_id,
            timestamp=event_ts,
            confidence=confidence,
            evidence_refs=evidence_refs,
            metadata=data,
            dedup_key=dedup_key,
        )
