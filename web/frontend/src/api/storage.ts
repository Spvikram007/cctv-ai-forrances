import { apiClient } from './client';
import { StorageVolumeInfo, StorageStatus } from '../types/storage';

export const storageApi = {
  listPools: async (): Promise<StorageVolumeInfo[]> => {
    return apiClient.get<StorageVolumeInfo[]>('/storage/pools');
  },

  getStatus: async (): Promise<StorageStatus> => {
    return apiClient.get<StorageStatus>('/storage/status');
  },
};
