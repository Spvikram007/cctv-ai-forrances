import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Shield, Clock, LogOut, Activity, Wifi } from 'lucide-react';

export const Header: React.FC = () => {
  const { user, logout } = useAuth();
  const [timeStr, setTimeStr] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-slate-800 bg-slate-900/90 px-4 backdrop-blur-md">
      {/* Brand & System Mode */}
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
          <Shield className="h-5 w-5" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm tracking-wide text-slate-100">CCTV AI</span>
            <span className="rounded bg-sky-950 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-400 border border-sky-800/40">
              LAN Web v1.5
            </span>
          </div>
        </div>
      </div>

      {/* Center System Telemetry Indicators */}
      <div className="hidden sm:flex items-center gap-6 text-xs text-slate-400">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
          </span>
          <span className="font-mono text-emerald-400 font-medium">CORE ONLINE</span>
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          <Wifi className="h-3.5 w-3.5 text-sky-400" />
          <span>LAN SECURE</span>
        </div>
        <div className="flex items-center gap-1.5 font-mono text-slate-300 bg-slate-950/60 px-2.5 py-1 rounded border border-slate-800">
          <Clock className="h-3.5 w-3.5 text-sky-400" />
          <span>{timeStr || '--:--:--'}</span>
        </div>
      </div>

      {/* Operator Profile & Logout */}
      <div className="flex items-center gap-3">
        {user ? (
          <div className="flex items-center gap-2.5">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-medium text-slate-200">{user.full_name || user.username}</div>
              <div className="text-[10px] font-mono text-sky-400">{user.role_name}</div>
            </div>
            <button
              onClick={() => logout()}
              title="Sign Out"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:border-rose-500/50 hover:bg-rose-500/10 hover:text-rose-400 transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <Activity className="h-4 w-4 text-slate-500 animate-pulse" />
            <span>Standby Mode</span>
          </div>
        )}
      </div>
    </header>
  );
};
