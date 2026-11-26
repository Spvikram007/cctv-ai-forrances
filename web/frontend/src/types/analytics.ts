export interface AnalyticsRule {
  id: string;
  name: string;
  rule_type: string;
  channel_id: string;
  severity: string;
  confidence_threshold: number;
  is_active: boolean;
  min_dwell_time_sec: number;
  trigger_recording: boolean;
}

export interface AnalyticsStatus {
  hardware_tier: string;
  active_device: string;
  openvino_enabled: boolean;
  onnx_runtime_enabled: boolean;
  primary_model: string;
  tracker: string;
  target_fps: number;
  avg_latency_ms: number;
  status: string;
}
