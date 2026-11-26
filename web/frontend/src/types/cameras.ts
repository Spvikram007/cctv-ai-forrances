export interface CameraResponse {
  id: string;
  name: string;
  device_type: string;
  manufacturer: string;
  ip_address: string;
  port: number;
  rtsp_port: number;
  onvif_port?: number | null;
  is_online: boolean;
  channel_id?: string | null;
  rtsp_url?: string | null;
  created_at: string;
}

export interface CameraCreateRequest {
  name: string;
  ip_address: string;
  port?: number;
  rtsp_port?: number;
  onvif_port?: number;
  manufacturer?: string;
  username?: string;
  password?: string;
  rtsp_path?: string;
}
