import { apiClient } from './client';
import { Alarm, AlarmSummary } from '../types/alarms';

export const alarmsApi = {
  listAlarms: async (params?: { status?: string; severity?: string; limit?: number; offset?: number }): Promise<Alarm[]> => {
    return apiClient.get<Alarm[]>('/alarms', params);
  },

  getSummary: async (): Promise<AlarmSummary> => {
    return apiClient.get<AlarmSummary>('/alarms/summary');
  },

  acknowledgeAlarm: async (id: string): Promise<Alarm> => {
    return apiClient.post<Alarm>(`/alarms/${id}/acknowledge`);
  },

  resolveAlarm: async (id: string): Promise<Alarm> => {
    return apiClient.post<Alarm>(`/alarms/${id}/resolve`);
  },
};
