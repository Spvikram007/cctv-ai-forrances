export interface LoginRequest {
  username: string;
  password: string;
  client_name?: string;
}

export interface LoginResponse {
  session_id: string;
  session_token: string;
  user_id: string;
  username: string;
  full_name: string;
  role_name: string;
  expires_at: string;
}

export interface UserProfile {
  user_id: string;
  username: string;
  full_name: string;
  email?: string | null;
  role_id: string;
  role_name: string;
  is_active: boolean;
  permissions: string[];
  last_login_at?: string | null;
}

export interface SessionInfo {
  session_id: string;
  user_id: string;
  username: string;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  is_current: boolean;
}
