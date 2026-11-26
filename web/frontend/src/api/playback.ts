import { apiClient } from './client';
import { RecordingSegment } from '../types/playback';

export const playbackApi = {
  listRecordings: async (params?: { channel_id?: string; limit?: number; offset?: number }): Promise<RecordingSegment[]> => {
    return apiClient.get<RecordingSegment[]>('/playback/recordings', params);
  },
};
