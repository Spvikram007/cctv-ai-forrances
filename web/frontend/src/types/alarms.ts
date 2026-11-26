export interface Alarm {
  id: string;
  title: string;
  description?: string | null;
  category: string;
  source_subsystem: string;
  severity: 'CRITICAL' | 'HIGH' | 'WARNING' | 'MEDIUM' | 'LOW' | 'INFO';
  priority: string;
  status: 'NEW' | 'ACKNOWLEDGED' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED';
  camera_id?: string | null;
  first_detected_at: string;
  last_detected_at: string;
  occurrence_count: number;
  assigned_operator?: string | null;
  acknowledged_at?: string | null;
  acknowledged_by?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
}

export interface AlarmSummary {
  total: number;
  active: number;
  critical: number;
  warning: number;
  acknowledged: number;
  resolved: number;
}
