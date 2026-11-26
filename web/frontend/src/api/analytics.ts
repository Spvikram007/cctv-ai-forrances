import { apiClient } from './client';
import { AnalyticsRule, AnalyticsStatus } from '../types/analytics';

export const analyticsApi = {
  listRules: async (): Promise<AnalyticsRule[]> => {
    return apiClient.get<AnalyticsRule[]>('/analytics/rules');
  },

  getStatus: async (): Promise<AnalyticsStatus> => {
    return apiClient.get<AnalyticsStatus>('/analytics/status');
  },
};
