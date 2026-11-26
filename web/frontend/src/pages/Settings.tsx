import React, { useEffect, useState } from 'react';
import { Settings as SettingsIcon, Wifi, Lock, ShieldCheck, Database, RefreshCw } from 'lucide-react';
import { systemApi } from '../api/system';
import { SystemSettings } from '../types/settings';

export const Settings: React.FC = () => {
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await systemApi.getSettings();
      setSettings(data);
    } catch {
      setSettings(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <SettingsIcon className="h-5 w-5 text-sky-400" />
            Platform & Network Security Settings
          </h1>
          <p className="text-xs text-slate-400">
            Dynamic LAN subnet whitelisting, TLS encryption parameters, cookie policies, and lockout rules.
          </p>
        </div>

        <button
          onClick={loadSettings}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="space-y-4">
        {/* Dynamic LAN Subnet Whitelist */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
            <Wifi className="h-4 w-4 text-sky-400" />
            Authorized LAN Subnets (CIDR Notation)
          </div>
          <p className="text-xs text-slate-400">
            Incoming LAN traffic is filtered by CIDR network notation. Access is strictly restricted to authorized local network subnets:
          </p>
          <div className="flex flex-wrap gap-2 pt-1 font-mono text-xs">
            {settings?.allowed_subnets?.map((subnet) => (
              <span key={subnet} className="rounded bg-slate-950 px-2.5 py-1 text-slate-300 border border-slate-800">
                {subnet}
              </span>
            )) || (
              ['127.0.0.1/32', '192.168.0.0/16', '10.0.0.0/8', '172.16.0.0/12'].map((subnet) => (
                <span key={subnet} className="rounded bg-slate-950 px-2.5 py-1 text-slate-300 border border-slate-800">
                  {subnet}
                </span>
              ))
            )}
          </div>
        </div>

        {/* Security & Authentication Policies */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
            <Lock className="h-4 w-4 text-emerald-400" />
            Security & Authentication Policies
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-slate-400">
            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
              <div className="font-semibold text-slate-200 mb-1 flex items-center justify-between">
                <span>Brute-Force Lockout Policy</span>
                <span className="font-mono text-sky-400 text-[10px]">
                  {settings?.lockout_threshold ?? 5} ATTEMPTS
                </span>
              </div>
              <div>
                Threshold: <span className="font-mono text-slate-200">{settings?.lockout_threshold ?? 5}</span> consecutive failed logins.
              </div>
              <div>
                Duration: <span className="font-mono text-slate-200">{settings?.lockout_duration_minutes ?? 15}</span> minutes lockout window.
              </div>
              <div className="text-[11px] text-slate-500">
                Super Administrator account immunity:{' '}
                <span className="text-emerald-400 font-semibold">
                  {settings?.super_admin_immunity ? 'ENABLED' : 'DISABLED'}
                </span>
              </div>
            </div>

            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
              <div className="font-semibold text-slate-200 mb-1 flex items-center justify-between">
                <span>Session Cookie Security</span>
                <span className="font-mono text-emerald-400 text-[10px]">HTTPONLY</span>
              </div>
              <div>
                Cookie Name: <span className="font-mono text-slate-200">{settings?.session_cookie_name || 'cctv_session'}</span>
              </div>
              <div>
                Lifetime: <span className="font-mono text-slate-200">{settings?.session_lifetime_minutes ?? 30}</span> minutes rolling expiry.
              </div>
              <div className="text-[11px] text-slate-500">
                SameSite policy: <span className="text-slate-300 font-mono">{settings?.cookie_samesite || 'Lax'}</span> • Secure flag:{' '}
                <span className="text-slate-300 font-mono">{settings?.cookie_secure ? 'true' : 'false'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Cryptography & Ledger Parameters */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 space-y-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
            <ShieldCheck className="h-4 w-4 text-purple-400" />
            Cryptographic Integrity & Ledger Architecture
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs text-slate-400">
            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
              <div className="font-semibold text-slate-200 mb-1">Merkle Hash Chain Ledger</div>
              <div>
                Algorithm: <span className="font-mono text-emerald-400">{settings?.audit_chain_algorithm || 'SHA-256'}</span>
              </div>
              <div className="text-[11px] text-slate-500">
                Continuous hash chaining across all operator, configuration, and security events.
              </div>
            </div>

            <div className="rounded-lg bg-slate-950 p-3 border border-slate-800 space-y-1">
              <div className="font-semibold text-slate-200 mb-1 flex items-center gap-1.5">
                <Database className="h-3.5 w-3.5 text-sky-400" />
                <span>Storage Encryption at Rest</span>
              </div>
              <div>
                Cipher: <span className="font-mono text-sky-400">{settings?.storage_encryption || 'AES-256-CBC'}</span>
              </div>
              <div className="text-[11px] text-slate-500">
                Chunk-level payload encryption for video segments and recording index files.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
