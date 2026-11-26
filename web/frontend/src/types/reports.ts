export interface AuditLogEntry {
  id: string;
  created_at: string;
  action: string;
  category: string;
  status: string;
  username: string;
  resource_type: string;
  resource_id?: string | null;
  correlation_id: string;
  record_hash?: string | null;
  prev_hash?: string | null;
}

export interface AuditIntegrity {
  is_valid: boolean;
  record_count: number;
  algorithm: string;
  details: string;
}
