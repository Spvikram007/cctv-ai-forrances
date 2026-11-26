import { apiClient } from './client';
import { UserAccount, RoleInfo } from '../types/users';

export const usersApi = {
  listUsers: async (): Promise<UserAccount[]> => {
    return apiClient.get<UserAccount[]>('/users');
  },

  listRoles: async (): Promise<RoleInfo[]> => {
    return apiClient.get<RoleInfo[]>('/roles');
  },
};
