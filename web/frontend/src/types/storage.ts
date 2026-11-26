export interface StorageVolumeInfo {
  id: string;
  name: string;
  mount_path: string;
  volume_type: string;
  filesystem: string;
  volume_status: string;
  total_gb: number;
  used_gb: number;
  free_gb: number;
  used_percent: number;
  is_active: boolean;
  is_default: boolean;
}

export interface StorageStatus {
  hot_tier_status: string;
  retention_policy_days: number;
  database_file: string;
  database_size_mb: number;
  wal_file_size_mb: number;
  encryption_algorithm: string;
  merkle_chain_integrity: string;
}
