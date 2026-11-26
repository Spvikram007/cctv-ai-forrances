export interface RecordingSegment {
  id: string;
  channel_id: string;
  recording_type: string;
  stream_type: string;
  start_time: string;
  end_time?: string | null;
  duration_sec: number;
  file_size_mb: number;
  codec: string;
  resolution: string;
  fps: number;
  status: string;
  is_locked: boolean;
}
