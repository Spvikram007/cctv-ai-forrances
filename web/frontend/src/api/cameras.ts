import { apiClient } from './client';
import { CameraResponse, CameraCreateRequest } from '../types/cameras';
import { PaginationQuery } from '../types/api';

export const camerasApi = {
  listCameras: async (query?: PaginationQuery): Promise<CameraResponse[]> => {
    return apiClient.get<CameraResponse[]>('/cameras', {
      search: query?.search,
      online_only: query?.online_only,
      limit: query?.limit,
      offset: query?.offset,
    });
  },

  getCamera: async (id: string): Promise<CameraResponse> => {
    return apiClient.get<CameraResponse>(`/cameras/${id}`);
  },

  registerCamera: async (data: CameraCreateRequest): Promise<CameraResponse> => {
    return apiClient.post<CameraResponse>('/cameras', data);
  },

  deleteCamera: async (id: string): Promise<{ message: string }> => {
    return apiClient.delete<{ message: string }>(`/cameras/${id}`);
  },
};
