import { apiClient } from './client';
import { LoginRequest, LoginResponse, UserProfile, SessionInfo } from '../types/auth';

export const authApi = {
  login: async (payload: LoginRequest): Promise<LoginResponse> => {
    const res = await apiClient.post<LoginResponse>('/auth/login', payload);
    if (res?.session_token) {
      sessionStorage.setItem('cctv_session_token', res.session_token);
    }
    return res;
  },

  logout: async (): Promise<{ message: string }> => {
    try {
      return await apiClient.post<{ message: string }>('/auth/logout');
    } finally {
      sessionStorage.removeItem('cctv_session_token');
    }
  },

  getProfile: async (): Promise<UserProfile> => {
    return apiClient.get<UserProfile>('/auth/me');
  },

  refreshSession: async (): Promise<{ status: string; username: string }> => {
    return apiClient.post<{ status: string; username: string }>('/auth/refresh');
  },

  listSessions: async (): Promise<SessionInfo[]> => {
    return apiClient.get<SessionInfo[]>('/auth/sessions');
  },

  revokeSession: async (sessionId: string): Promise<{ message: string }> => {
    return apiClient.delete<{ message: string }>(`/auth/sessions/${sessionId}`);
  },

  getWebSocketTicket: async (): Promise<{ ticket: string; expires_in: number }> => {
    return apiClient.post<{ ticket: string; expires_in: number }>('/auth/ws-ticket');
  },
};
