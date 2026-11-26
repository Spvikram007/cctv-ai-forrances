/**
 * CCTV AI Platform — Standard RBAC Permission Codes.
 * Parity with core/security/rbac.py (22 operational permissions).
 */
export const PermissionCodes = {
  DASHBOARD_VIEW: 'dashboard:view',
  LIVE_VIEW: 'live:view',
  CAMERA_MANAGE: 'camera:manage',
  PTZ_CONTROL: 'ptz:control',
  PLAYBACK_VIEW: 'playback:view',
  PLAYBACK_EXPORT: 'playback:export',
  AI_VIEW: 'ai:view',
  AI_CONFIGURE: 'ai:configure',
  BIOMETRICS_VIEW: 'biometrics:view',
  BIOMETRICS_MANAGE: 'biometrics:manage',
  ALARM_VIEW: 'alarm:view',
  ALARM_MANAGE: 'alarm:manage',
  FORENSIC_VIEW: 'forensic:view',
  EVIDENCE_EXPORT: 'evidence:export',
  STORAGE_MANAGE: 'storage:manage',
  NETWORK_VIEW: 'network:view',
  NETWORK_SCAN: 'network:scan',
  USER_MANAGE: 'user:manage',
  ROLE_MANAGE: 'role:manage',
  AUDIT_VIEW: 'audit:view',
  AUDIT_EXPORT: 'audit:export',
  SYSTEM_CONFIG: 'system:config',
} as const;

export type PermissionCode = typeof PermissionCodes[keyof typeof PermissionCodes];
