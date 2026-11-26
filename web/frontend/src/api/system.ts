import { apiClient } from './client';
import { HealthResponse, ReadinessResponse, SystemStatus } from '../types/system';
import { SystemSettings } from '../types/settings';

export const systemApi = {
  getHealth: async (): Promise<HealthResponse> => {
    return apiClient.get<HealthResponse>('/health');
  },

  getReadiness: async (): Promise<ReadinessResponse> => {
    return apiClient.get<ReadinessResponse>('/ready');
  },

  getSystemStatus: async (): Promise<SystemStatus> => {
    return apiClient.get<SystemStatus>('/system/status');
  },

  getSettings: async (): Promise<SystemSettings> => {
    return apiClient.get<SystemSettings>('/system/settings');
  },
};
