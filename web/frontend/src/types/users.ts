export interface UserAccount {
  id: string;
  username: string;
  full_name: string;
  email?: string | null;
  role_id: string;
  role_name: string;
  is_active: boolean;
  failed_login_attempts: number;
  locked_until?: string | null;
  last_login_at?: string | null;
  created_at?: string | null;
}

export interface RoleInfo {
  id: string;
  name: string;
  description: string;
  is_system: boolean;
  permissions: string[];
  permission_count: number;
}
