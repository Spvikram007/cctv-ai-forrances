# CCTV AI INTELLIGENCE PLATFORM — PHASE 13 PHYSICAL VALIDATION CHECKLIST
## Enterprise Storage, Hardware RAID, Physical NAS, and Failover Field Verification

**Document ID**: CHK-20261125-013  
**Feature ID**: F-047  
**Change ID**: CHG-20261125-012  
**Platform Version**: 1.3.0-alpha  
**Date**: 2026-11-25  
**Scope**: Physical Hardware & Field Deployment Verification Procedures  

---

### Purpose

This checklist defines the mandatory field verification procedures required to certify Phase 13 Enterprise Storage Management on physical surveillance hardware prior to customer sign-off. While automated mock and unit tests confirm software logic, **physical hardware validation cannot be simulated**.

Field technicians and deployment engineers must complete and sign every section of this document.

---

### 1. Physical Local Storage & Filesystem Verification

| Item | Validation Step | Expected Physical Behavior | Technician Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **ST-01** | Connect NVMe M.2 and SATA 3.5" surveillance hard drives (e.g. WD Purple / Seagate SkyHawk). | Windows Disk Management detects physical disks; `LocalStorageAdapter` discovers volumes with correct drive letters. | Observed drive paths and serial numbers match device labels. | [ ] PASS  [ ] FAIL |
| **ST-02** | Format primary surveillance volume with NTFS (64KB allocation unit size). | `LocalStorageAdapter.get_filesystem_capabilities()` reports `NTFS`, transaction support, and proper cluster size. | Cluster size: 64 KB; FS: NTFS. | [ ] PASS  [ ] FAIL |
| **ST-03** | Format archival tier volume with ReFS (Windows Server / Windows 11 Enterprise). | Capability detection reports `ReFS` with integrity streams enabled. | ReFS detected; integrity streams verified. | [ ] PASS  [ ] FAIL |
| **ST-04** | Run sustained continuous write test across 64 camera streams for 6 hours. | Volume write latency remains $< 35\text{ ms}$; no dropped frames reported in `StreamDiagnostics`. | Avg write latency: ____ ms; Drops: ____. | [ ] PASS  [ ] FAIL |
| **ST-05** | Simulate drive fill beyond 85% warning threshold. | EventBus publishes `storage.volume_low`; View 10 KPI card updates to amber; warning alert logged. | Warning event generated at 85.0% used. | [ ] PASS  [ ] FAIL |
| **ST-06** | Simulate drive fill beyond 95% critical threshold. | EventBus publishes `storage.volume_critical`; red badge displayed; new writes gated to failover target. | Critical alert generated; streams redirected. | [ ] PASS  [ ] FAIL |

---

### 2. Hardware RAID & Storage Spaces Field Validation

| Item | Validation Step | Expected Physical Behavior | Technician Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **RD-01** | Configure physical hardware RAID 5 array (e.g., LSI / Broadcom MegaRAID or Intel VROC). | `RAIDMonitoringAdapter` queries controller CLI/WMI; reports `OPTIMAL` with correct disk count. | Array status: OPTIMAL; Disks: 4/4 online. | [ ] PASS  [ ] FAIL |
| **RD-02** | Configure Windows Storage Spaces two-way mirror or parity pool. | Windows Storage Spaces cmdlets (`Get-StoragePool`, `Get-VirtualDisk`) return healthy status. | Pool: StoragePoolSurveillance; Status: OK. | [ ] PASS  [ ] FAIL |
| **RD-03** | Physical Drive Pull Test: Disconnect 1 SATA drive during active recording. | Controller beeper activates; RAID status transitions to `DEGRADED`; EventBus alert published; recording continues without data loss. | Degradation detected within $< 2\text{ s}$; 0 frame loss. | [ ] PASS  [ ] FAIL |
| **RD-04** | Re-insert replacement drive and trigger administrative rebuild gate from UI. | UI prompts for Administrator authorization; rebuild progress bar tracks from 0% to 100%. | Rebuild authorized; completed in ____ hours. | [ ] PASS  [ ] FAIL |
| **RD-05** | Verify array returns to `OPTIMAL` state post-rebuild. | `RAIDMonitoringAdapter` verifies array status is `OPTIMAL`; telemetry updates across all UI tabs. | Verified OPTIMAL. | [ ] PASS  [ ] FAIL |

---

### 3. Physical NAS Appliance Integration (SMB/CIFS & NFS)

| Item | Validation Step | Expected Physical Behavior | Technician Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **NAS-01** | Connect enterprise NAS (Synology, QNAP, or TrueNAS) on dedicated 10GbE surveillance VLAN. | Network reachability probe succeeds; ping latency $< 1.5\text{ ms}$; throughput $> 800\text{ MB/s}$. | Ping: ____ ms; Throughput: ____ MB/s. | [ ] PASS  [ ] FAIL |
| **NAS-02** | Configure SMB 3.1.1 share with DPAPI-encrypted service account credentials. | Credentials stored securely via Windows DPAPI; share mounts cleanly; zero plaintext in DB or logs. | DPAPI blob verified; share mounted at `Z:\`. | [ ] PASS  [ ] FAIL |
| **NAS-03** | Physical Network Cable Pull: Disconnect NAS 10GbE network link during active archival job. | Subsystem detects timeout within 3s; retry mechanism triggers exponential backoff; alarm generated. | Connection dropped alert logged; retry backoff active. | [ ] PASS  [ ] FAIL |
| **NAS-04** | Reconnect NAS network link. | Subsystem automatically reconnects within 10s; queued transfer resumes without file corruption. | Reconnection confirmed; transfers resumed. | [ ] PASS  [ ] FAIL |
| **NAS-05** | Verify NFS 4.1 share mount on Windows 11 Enterprise (Client for NFS enabled). | NFS export mounted; directory creation and file permissions verified. | NFS mount operational. | [ ] PASS  [ ] FAIL |

---

### 4. Automated Recording Failover & Transition Gap Audit

| Item | Validation Step | Expected Physical Behavior | Technician Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **FO-01** | Assign primary volume to Drive D: and failover target to Drive E: for Camera Channel 1. | `StorageAllocation` table confirms `primary_volume_id` (D:) and `failover_volume_id` (E:). | Allocation verified in DB. | [ ] PASS  [ ] FAIL |
| **FO-02** | Simulate sudden I/O write block on Drive D: (e.g. disk offline or write permission revoked). | Recording engine catches write error; `StorageFailoverManager` activates; stream redirects to E:. | Redirection completed in $< 1.5\text{ s}$. | [ ] PASS  [ ] FAIL |
| **FO-03** | Inspect transition gap recorded in `StorageFailoverEvent`. | Transition gap explicitly calculated and logged (e.g., $1.2\text{ s}$); gap alert published to Alarm Engine. | Recorded gap: ____ seconds; logged to DB. | [ ] PASS  [ ] FAIL |
| **FO-04** | Verify recording playback across the failover boundary. | Playback engine plays pre-failover clip (D:) and seamlessly switches to post-failover clip (E:). | Playback boundary verified; standby indicator on gap. | [ ] PASS  [ ] FAIL |
| **FO-05** | Restore Drive D: to healthy status and execute controlled failback from UI. | Primary volume health verified; failover event marked `FAILED_BACK`; new segments resume on D:. | Controlled failback confirmed. | [ ] PASS  [ ] FAIL |

---

### 5. Multi-Tier Archival & Evidentiary Protection Field Audit

| Item | Validation Step | Expected Physical Behavior | Technician Result | Pass/Fail |
| :--- | :--- | :--- | :--- | :--- |
| **AR-01** | Configure multi-tier policy: Hot (NVMe, 7 days) $\rightarrow$ Cold (NAS, 90 days). | Policy engine registers tier thresholds and scheduled migration window. | Policy active in `storage_policies`. | [ ] PASS  [ ] FAIL |
| **AR-02** | Execute scheduled archival migration for recordings $> 7$ days old. | Recordings copied to NAS; SHA-256 hashes verified against source before source deletion. | Files migrated: ____; SHA-256 verification 100%. | [ ] PASS  [ ] FAIL |
| **AR-03** | Flag critical incident recording with legal evidence lock (`is_locked=True`). | Database confirms `is_locked=True` in `recordings` table. | Lock confirmed in database. | [ ] PASS  [ ] FAIL |
| **AR-04** | Run archival migration on volume containing locked recording. | Locked recording is duplicated to Cold NAS archive tier; **SOURCE ON HOT TIER IS NEVER DELETED**. | Source file verified present on Hot tier. | [ ] PASS  [ ] FAIL |
| **AR-05** | Trigger manual retention purge on Hot tier. | Routine recordings are pruned; **LOCKED EVIDENCE SOURCE FILE IS PRESERVED INTACT**. | Source file preserved; zero deletion. | [ ] PASS  [ ] FAIL |
| **AR-06** | Execute `restore_archival_copy` from NAS back to Hot tier. | File restored to primary volume; SHA-256 matches original manifest; immediately available in Playback. | Restore successful; hash match verified. | [ ] PASS  [ ] FAIL |

---

### Field Sign-off & Certification

- **Lead Deployment Engineer**: ______________________________________  
- **Lead Storage Administrator**: ____________________________________  
- **Customer Site Name**: ___________________________________________  
- **Date of Physical Certification**: ________________________________  
- **Overall Deployment Verdict**: [ ] ACCEPTED FOR PRODUCTION  [ ] CONDITIONALLY ACCEPTED  [ ] REJECTED  
