import { apiClient } from './client';
import { AuditLogEntry, AuditIntegrity } from '../types/reports';

export const reportsApi = {
  listAuditLogs: async (params?: { category?: string; username?: string; status?: string; limit?: number; offset?: number }): Promise<AuditLogEntry[]> => {
    return apiClient.get<AuditLogEntry[]>('/reports/audit-logs', params);
  },

  verifyIntegrity: async (): Promise<AuditIntegrity> => {
    return apiClient.get<AuditIntegrity>('/reports/audit-integrity');
  },
};
