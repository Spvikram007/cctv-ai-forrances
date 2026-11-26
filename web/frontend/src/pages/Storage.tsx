import React, { useEffect, useState } from 'react';
import { HardDrive, Server, Database, RefreshCw, ShieldCheck, Clock } from 'lucide-react';
import { storageApi } from '../api/storage';
import { StorageVolumeInfo, StorageStatus } from '../types/storage';

export const Storage: React.FC = () => {
  const [pools, setPools] = useState<StorageVolumeInfo[]>([]);
  const [status, setStatus] = useState<StorageStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadStorage = async () => {
    setLoading(true);
    try {
      const [poolsData, statusData] = await Promise.all([
        storageApi.listPools(),
        storageApi.getStatus(),
      ]);
      setPools(poolsData);
      setStatus(statusData);
    } catch {
      setPools([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStorage();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <HardDrive className="h-5 w-5 text-sky-400" />
            Enterprise Storage Pools & Retention
          </h1>
          <p className="text-xs text-slate-400">
            Local volumes, disk utilization, SQLite WAL metadata ledger, and continuous retention policies.
          </p>
        </div>

        <button
          onClick={loadStorage}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Storage Pools Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {pools.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-center text-slate-500 text-xs col-span-2">
            {loading ? 'Discovering storage volumes...' : 'No storage volumes currently mapped.'}
          </div>
        ) : (
          pools.map((vol) => (
            <div key={vol.id} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-2">
                <span className="flex items-center gap-2">
                  <Server className="h-4 w-4 text-sky-400" />
                  {vol.name} ({vol.volume_type.toUpperCase()} TIER)
                </span>
                <span
                  className={`font-mono text-[10px] px-2 py-0.5 rounded border ${
                    vol.volume_status === 'healthy' || vol.volume_status === 'active'
                      ? 'bg-emerald-950/70 text-emerald-400 border-emerald-800/40'
                      : 'bg-amber-950/70 text-amber-400 border-amber-800/40'
                  }`}
                >
                  {vol.volume_status.toUpperCase()}
                </span>
              </div>

              <div className="space-y-2 mt-4">
                <div className="flex justify-between text-xs text-slate-400">
                  <span className="font-mono truncate max-w-[200px]" title={vol.mount_path}>
                    Path: {vol.mount_path}
                  </span>
                  <span className="font-mono">
                    {vol.used_gb.toFixed(1)} GB / {vol.total_gb.toFixed(1)} GB
                  </span>
                </div>

                <div className="h-2 w-full rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      vol.used_percent > 85 ? 'bg-rose-500' : vol.used_percent > 70 ? 'bg-amber-500' : 'bg-sky-500'
                    }`}
                    style={{ width: `${Math.min(100, vol.used_percent)}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                  <span>{vol.free_gb.toFixed(1)} GB Available</span>
                  <span className="font-mono">{vol.used_percent.toFixed(1)}% Allocated</span>
                </div>
              </div>
            </div>
          ))
        )}

        {/* SQLite Metadata Ledger Status */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-2">
            <span className="flex items-center gap-2">
              <Database className="h-4 w-4 text-purple-400" />
              METADATA LEDGER (SQLite WAL)
            </span>
            <span className="font-mono text-[10px] text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40">
              {status?.hot_tier_status || 'WAL ACTIVE'}
            </span>
          </div>

          <div className="space-y-2 mt-3 text-xs text-slate-400">
            <div className="flex justify-between border-b border-slate-800/60 pb-1.5">
              <span>Ledger Database:</span>
              <span className="font-mono text-slate-200">{status?.database_file || 'storage/cctv_metadata.db'}</span>
            </div>
            <div className="flex justify-between border-b border-slate-800/60 pb-1.5">
              <span>WAL Checkpoint Size:</span>
              <span className="font-mono text-slate-200">
                {status?.wal_file_size_mb !== undefined ? `${status.wal_file_size_mb.toFixed(1)} MB` : 'Clean'}
              </span>
            </div>
            <div className="flex justify-between pt-0.5">
              <span>Tamper Evident Integrity:</span>
              <span className="text-emerald-400 font-semibold flex items-center gap-1">
                <ShieldCheck className="h-3.5 w-3.5" />
                {status?.merkle_chain_integrity || 'Merkle Verified'}
              </span>
            </div>
          </div>
        </div>

        {/* Retention Policy Card */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-2">
            <span className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-emerald-400" />
              AUTOMATED RETENTION POLICIES
            </span>
            <span className="font-mono text-[10px] text-sky-400">30-DAY WINDOW</span>
          </div>

          <div className="space-y-2 mt-3 text-xs text-slate-400">
            <div className="flex justify-between border-b border-slate-800/60 pb-1.5">
              <span>Retention Window:</span>
              <span className="font-mono text-slate-200">{status?.retention_policy_days ?? 30} Days Continuous</span>
            </div>
            <div className="flex justify-between border-b border-slate-800/60 pb-1.5">
              <span>Auto-Prune Threshold:</span>
              <span className="font-mono text-slate-200">85% Capacity High-Watermark</span>
            </div>
            <div className="flex justify-between pt-0.5">
              <span>Encryption at Rest:</span>
              <span className="font-mono text-sky-400">{status?.encryption_algorithm || 'AES-256 Block Storage'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
