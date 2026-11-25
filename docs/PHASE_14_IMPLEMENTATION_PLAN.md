# Phase 14 Implementation Plan: User Management, RBAC, Audit Reporting & Multi-Format Evidence Export

**Feature ID:** `F-022`, `F-025`, `F-048`  
**Change ID:** `CHG-20261125-013`  
**Baseline Release:** `1.3.0-alpha` (Commit: `bca625c`, 464 tests passed)  
**Target Release:** `1.4.0-alpha`  
**Status:** Approved for Implementation  

---

## 1. Overview & Architectural Boundaries

Phase 14 delivers an enterprise-grade security and administrative backbone for the CCTV AI Intelligence Platform:
1. **User Management**: Lifecycle administration, modern `bcrypt` password hashing, failed attempt tracking, automatic account lockout, and session expiration.
2. **Granular RBAC**: 10 default hierarchical roles, 22 fine-grained permissions across 15 operational categories, backend enforcement decorators, least-privilege defaults, and protection against Super Administrator lockout and privilege escalation.
3. **Audit Reporting & Tamper-Evident Integrity**: Multi-category activity logging (Auth, User, Role, Camera, PTZ, Playback, Evidence, Storage, System), rolling SHA-256 Merkle hash chaining, independent ledger verification, and Asia/Kolkata timezone presentation.
4. **Multi-Format Evidence & Report Export**: Native high-resolution PDF generation via `QPdfWriter`, CSV export with spreadsheet formula-injection protection (CWE-1236), and cryptographic evidence integrity validation.
5. **Native PySide6 Workspaces**:
   - `UserManagementWidget` mounted at View 13 (`Administration` / `User Management`).
   - `ReportingWorkspaceWidget` mounted at View 11 (`Reports` / `Audit & Export Center`).

---

## 2. File-Level Implementation Inventory

```
cctv ai/
├── database/
│   ├── models/
│   │   ├── users.py                      # [MODIFIED] Add lockout, session, audit chaining fields
│   │   └── __init__.py                   # [VERIFIED] Ensure all symbols exported
│   └── migrations/versions/
│       └── 78a12e9b04f1_phase14_user_mgmt_rbac_audit.py # [NEW] Alembic migration script
├── core/
│   └── security/
│       ├── password.py                   # [NEW] Bcrypt hashing, complexity check, migration helper
│       ├── rbac.py                       # [NEW] RBACService, permission codes, 10 default roles
│       ├── decorators.py                 # [NEW] @require_permission, @audit_action decorators
│       ├── user_service.py               # [NEW] UserCRUD, lockout logic, session manager
│       └── audit_service.py              # [NEW] Audit logging, hash chaining, integrity verification
├── modules/
│   ├── user_management/
│   │   ├── __init__.py                   # [NEW] Package exports
│   │   ├── user_management_widget.py     # [NEW] PySide6 User & RBAC Management Command Center
│   │   ├── user_dialog.py                # [NEW] Create/Edit User modal dialog
│   │   └── role_dialog.py                # [NEW] Role & Permission configuration dialog
│   └── reporting/
│       ├── __init__.py                   # [NEW] Package exports
│       ├── pdf_generator.py              # [NEW] QPdfWriter HTML-to-PDF report generator
│       ├── csv_exporter.py               # [NEW] Sanitized CSV exporter with formula injection defense
│       ├── report_service.py             # [NEW] Report data aggregation service
│       └── reporting_widget.py           # [NEW] PySide6 Reports & Audit Center Workspace
├── app/
│   ├── bootstrap.py                      # [MODIFIED] Seed 10 roles, default permissions, migration check
│   └── main.py                           # [MODIFIED] Wire View 11 (Reports) and View 13 (User Mgmt)
├── docs/
│   ├── PHASE_14_IMPLEMENTATION_PLAN.md   # [NEW] This specification
│   ├── PHASE_14_IMPLEMENTATION_REPORT.md # [NEW] Completion report upon execution
│   └── FEATURE_REGISTER.md               # [MODIFIED] Update F-022, F-025, F-048 status
└── tests/
    ├── unit/
    │   ├── test_user_management.py       # [NEW] User CRUD, bcrypt, lockout, session tests
    │   ├── test_rbac_service.py          # [NEW] Role hierarchy, permission checks, escalation blocks
    │   ├── test_audit_service.py         # [NEW] Audit generation, rolling hash chaining, tamper detection
    │   └── test_reporting_export.py      # [NEW] PDF generation, CSV injection protection, hash checks
    └── integration/
        └── test_phase14_workspaces.py    # [NEW] PySide6 UI integration and interaction smoke tests
```

---

## 3. Detailed Module Specifications

### 3.1 Module 14.1 — User Management & Authentication
- **Hashing**: `bcrypt.hashpw` with salt (cost factor 12).
- **Legacy Migration**: Bootstrap SHA-256 hash verified and automatically upgraded to bcrypt upon first successful login.
- **Lockout Policy**:
  - Maximum failed login attempts: 5.
  - Lockout window: 15 minutes.
  - Super Administrator lockout immunity: Super Administrator accounts cannot be locked by brute force attacks; alerts are flagged to audit ledger instead.
- **Session Management**:
  - Session tokens generated via `secrets.token_urlsafe(32)`.
  - Default idle session timeout: 30 minutes.
  - Active session tracking with IP address and user agent.
  - Session revocation capability.

### 3.2 Module 14.2 — Granular Role-Based Access Control (RBAC)
- **10 Default Hierarchical Roles**:
  1. `Super Administrator` (is_system=True, unrestricted access, immune to lockout, cannot be deleted)
  2. `Administrator` (user/camera/storage administration, policy management)
  3. `Security Manager` (operational supervision, policy edits, incident investigation)
  4. `Supervisor` (team oversight, alarm triage, shift reports)
  5. `CCTV Operator` (live grid monitoring, PTZ control, manual recording)
  6. `Investigator` (playback search, forensic analysis, report export)
  7. `Evidence Manager` (evidence locker access, cryptographic export, custody review)
  8. `Technician` (camera discovery, network tools, diagnostics)
  9. `Auditor` (read-only access to audit logs, compliance reports, integrity checks)
  10. `Read-Only Viewer` (live viewing of permitted streams only)
- **22 Operational Permissions**:
  `dashboard:view`, `live:view`, `camera:manage`, `ptz:control`, `playback:view`, `playback:export`, `ai:view`, `ai:configure`, `biometrics:view`, `biometrics:manage`, `alarm:view`, `alarm:manage`, `forensic:view`, `evidence:export`, `storage:manage`, `network:view`, `network:scan`, `user:manage`, `role:manage`, `audit:view`, `audit:export`, `system:config`.
- **Backend Enforcement**:
  - `@require_permission("...")` function decorator.
  - Explicit privilege escalation checks: only Super Administrators can grant `user:manage` or `role:manage`.
  - At least one active Super Administrator must remain active at all times.

### 3.3 Module 14.3 — Audit Reporting & Hash-Chained Integrity
- **Audit Logging Scope**:
  - `AUTH`: Login, logout, session expiration, lockout, password change.
  - `USER`: User creation, profile edit, deactivation, activation, unlock.
  - `ROLE`: Role creation, permission grant/revoke.
  - `CAMERA`: Device add/edit/delete, stream profile modifications.
  - `PTZ`: Pan/tilt/zoom movements, preset recalls.
  - `PLAYBACK`: Search, playback session, clip download.
  - `EVIDENCE`: Access, view, packaging, standalone verification.
  - `STORAGE`: Pool configuration, quota change, failover event.
  - `ALARM`: Acknowledgement, resolution, escalation.
  - `SYSTEM`: Network scans, diagnostics, configuration change.
- **Tamper-Evident Hash Chaining**:
  - `record_hash = SHA256(prev_hash + ":" + timestamp_utc + ":" + user_id + ":" + action + ":" + category + ":" + resource_id + ":" + status + ":" + details_json)`
  - Stored sequentially in `audit_logs` table and mirrored to append-only `storage/logs/audit_ledger.jsonl`.
  - Verification API `audit_service.verify_audit_integrity()` detects record deletion, insertion, modification, or tail truncation.

### 3.4 Module 14.4 — Multi-Format Evidence Export
- **PDF Report Generation**:
  - High-resolution A4 layout generated via `PySide6.QtGui.QPdfWriter` + `QTextDocument`.
  - Header branding: CCTV AI Intelligence Platform, Report ID, Generation Date (Asia/Kolkata), Generated By.
  - Structured HTML tables, color-coded status badges, and page footer with confidentiality disclaimer.
  - 5 report templates: Incident Report, Audit Log Report, User & Access Report, Evidence Manifest Report, Device Inventory Report.
- **CSV Export Engine**:
  - Standard RFC 4180 CSV with UTF-8 BOM encoding.
  - Formula Injection Protection: values starting with `=, +, -, @, \t, \r` are prepended with `'` to neutralize executable macros in Excel.
  - Credential masking: zero password hashes, encryption keys, or session tokens are exported.
- **Evidence Verification**:
  - Verifies source video SHA-256 and ECDSA P-256 signature before embedding in evidence reports.

---

## 4. Execution Sequence

1. **Step 1**: Update `database/models/users.py` with non-breaking fields and create Alembic migration.
2. **Step 2**: Implement `core/security/password.py` and `core/security/rbac.py`.
3. **Step 3**: Implement `core/security/user_service.py` and `core/security/decorators.py`.
4. **Step 4**: Implement `core/security/audit_service.py` with hash-chaining and verification.
5. **Step 5**: Implement `modules/reporting/pdf_generator.py`, `csv_exporter.py`, and `report_service.py`.
6. **Step 6**: Update `app/bootstrap.py` to seed 10 roles, default permissions, and run schema migration.
7. **Step 7**: Build PySide6 UI widgets: `modules/user_management/` and `modules/reporting/`.
8. **Step 8**: Wire Views 11 and 13 in `app/main.py`.
9. **Step 9**: Author comprehensive test suite (`tests/unit/test_user_management.py`, `test_rbac_service.py`, `test_audit_service.py`, `test_reporting_export.py`, `tests/integration/test_phase14_workspaces.py`).
10. **Step 10**: Execute full regression test suite (464 baseline + new Phase 14 tests) and verify process exit code 0.
11. **Step 11**: Update documentation and create `PHASE_14_IMPLEMENTATION_REPORT.md`.
