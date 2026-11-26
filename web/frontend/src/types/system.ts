export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
  database: string;
  event_bus: string;
  storage_engine: string;
  stream_manager: string;
}

export interface ReadinessResponse {
  ready: boolean;
  checks: Record<string, boolean>;
}

export interface SystemStatus {
  version: string;
  app_name: string;
  server_time: string;
  uptime_seconds: number;
  cpu_percent: number;
  memory_used_mb: number;
  memory_total_mb: number;
  memory_percent: number;
  openvino_device: string;
  active_stream_count: number;
  active_session_count: number;
}
