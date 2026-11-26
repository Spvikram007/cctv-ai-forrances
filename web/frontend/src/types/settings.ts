export interface SystemSettings {
  allowed_subnets: string[];
  cors_origins: string[];
  ssl_enabled: boolean;
  session_cookie_name: string;
  session_lifetime_minutes: number;
  cookie_samesite: string;
  cookie_secure: boolean;
  lockout_threshold: number;
  lockout_duration_minutes: number;
  super_admin_immunity: boolean;
  audit_chain_algorithm: string;
  storage_encryption: string;
}
