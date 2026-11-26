import React, { useEffect, useState, useCallback } from 'react';
import {
  Bell,
  AlertTriangle,
  ShieldAlert,
  CheckCircle,
  Filter,
  RefreshCw,
  Radio,
  Clock,
} from 'lucide-react';
import { alarmsApi } from '../api/alarms';
import { wsClient, WebSocketEventMessage } from '../api/ws';
import { Alarm, AlarmSummary } from '../types/alarms';

export const Alarms: React.FC = () => {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [summary, setSummary] = useState<AlarmSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);

  const loadAlarms = useCallback(async () => {
    setLoading(true);
    try {
      const [listData, sumData] = await Promise.all([
        alarmsApi.listAlarms({
          status: statusFilter || undefined,
          severity: severityFilter || undefined,
          limit: 100,
        }),
        alarmsApi.getSummary(),
      ]);
      setAlarms(listData);
      setSummary(sumData);
    } catch {
      setAlarms([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, severityFilter]);

  useEffect(() => {
    loadAlarms();

    wsClient.connect();
    const unsubscribe = wsClient.subscribe((event: WebSocketEventMessage) => {
      setWsConnected(true);
      if (event.topic.startsWith('alarm.')) {
        loadAlarms();
      }
    });

    return () => {
      unsubscribe();
    };
  }, [loadAlarms]);

  const handleAcknowledge = async (id: string) => {
    setActionLoadingId(id);
    try {
      const updated = await alarmsApi.acknowledgeAlarm(id);
      setAlarms((prev) => prev.map((a) => (a.id === id ? updated : a)));
      alarmsApi.getSummary().then(setSummary).catch(() => {});
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleResolve = async (id: string) => {
    setActionLoadingId(id);
    try {
      const updated = await alarmsApi.resolveAlarm(id);
      setAlarms((prev) => prev.map((a) => (a.id === id ? updated : a)));
      alarmsApi.getSummary().then(setSummary).catch(() => {});
    } finally {
      setActionLoadingId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Title & Stats Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Bell className="h-5 w-5 text-rose-400" />
            Surveillance Alarm & Incident Center
          </h1>
          <p className="text-xs text-slate-400">
            Real-time intrusion alerts, tripwire breaches, and incident escalation queue.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* WebSocket Live Indicator */}
          <div className="flex items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1 text-xs font-mono border border-slate-800">
            <Radio className={`h-3 w-3 ${wsConnected ? 'text-emerald-400 animate-pulse' : 'text-amber-400'}`} />
            <span className={wsConnected ? 'text-emerald-400' : 'text-amber-400'}>
              {wsConnected ? 'EVENTBUS LIVE' : 'CONNECTING'}
            </span>
          </div>

          <button
            onClick={loadAlarms}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3.5">
          <div className="text-xs font-medium text-slate-400">ACTIVE INCIDENTS</div>
          <div className="mt-1 text-2xl font-bold text-rose-400">{summary?.active ?? 0}</div>
          <div className="text-[11px] text-slate-500 font-mono">Unresolved alarms</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3.5">
          <div className="text-xs font-medium text-slate-400">CRITICAL BREACHES</div>
          <div className="mt-1 text-2xl font-bold text-rose-500">{summary?.critical ?? 0}</div>
          <div className="text-[11px] text-rose-400/80 font-mono">High priority triage</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3.5">
          <div className="text-xs font-medium text-slate-400">WARNING / HIGH</div>
          <div className="mt-1 text-2xl font-bold text-amber-400">{summary?.warning ?? 0}</div>
          <div className="text-[11px] text-slate-500 font-mono">Secondary alerts</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3.5">
          <div className="text-xs font-medium text-slate-400">RESOLVED INCIDENTS</div>
          <div className="mt-1 text-2xl font-bold text-emerald-400">{summary?.resolved ?? 0}</div>
          <div className="text-[11px] text-slate-500 font-mono">Cleared from queue</div>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-2.5">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <span className="text-xs text-slate-400 font-medium">Status:</span>
          {['', 'NEW', 'ACKNOWLEDGED', 'RESOLVED'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                statusFilter === st
                  ? 'bg-sky-500 text-white font-semibold'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {st || 'ALL'}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-medium">Severity:</span>
          {['', 'CRITICAL', 'WARNING', 'INFO'].map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                severityFilter === sev
                  ? 'bg-rose-600 text-white font-semibold'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {sev || 'ALL'}
            </button>
          ))}
        </div>
      </div>

      {/* Alarms Feed Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <tr>
              <th className="py-3 px-4">Severity</th>
              <th className="py-3 px-4">Event Type / Title</th>
              <th className="py-3 px-4">Camera Channel</th>
              <th className="py-3 px-4">Trigger Timestamp</th>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {loading ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500">
                  Loading surveillance incident stream...
                </td>
              </tr>
            ) : alarms.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-8 text-center text-slate-500 font-sans">
                  No alarms match the active filter criteria.
                </td>
              </tr>
            ) : (
              alarms.map((alarm) => (
                <tr key={alarm.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-mono font-bold border ${
                        alarm.severity === 'CRITICAL'
                          ? 'bg-rose-950/80 text-rose-400 border-rose-800/50'
                          : alarm.severity === 'WARNING' || alarm.severity === 'HIGH'
                          ? 'bg-amber-950/80 text-amber-400 border-amber-800/50'
                          : 'bg-sky-950/80 text-sky-400 border-sky-800/50'
                      }`}
                    >
                      {alarm.severity === 'CRITICAL' && <ShieldAlert className="h-3 w-3" />}
                      {(alarm.severity === 'WARNING' || alarm.severity === 'HIGH') && <AlertTriangle className="h-3 w-3" />}
                      {alarm.severity}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="font-semibold text-slate-200">
                      {alarm.title}
                    </div>
                    <div className="text-[10px] font-mono text-slate-500">{alarm.id}</div>
                  </td>
                  <td className="py-3 px-4">
                    <div className="text-slate-300 font-medium">
                      {alarm.category}
                    </div>
                    <div className="text-[10px] font-mono text-slate-500 truncate max-w-[120px]">
                      {alarm.camera_id || alarm.source_subsystem}
                    </div>
                  </td>
                  <td className="py-3 px-4 font-mono text-slate-400">
                    <div className="flex items-center gap-1">
                      <Clock className="h-3 w-3 text-slate-500" />
                      {new Date(alarm.first_detected_at).toLocaleString()}
                    </div>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-[10px] font-mono font-semibold ${
                        alarm.status === 'NEW'
                          ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          : alarm.status === 'ACKNOWLEDGED'
                          ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                          : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      }`}
                    >
                      {alarm.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      {alarm.status === 'NEW' && (
                        <button
                          onClick={() => handleAcknowledge(alarm.id)}
                          disabled={actionLoadingId === alarm.id}
                          className="rounded bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-200 hover:bg-slate-700 transition-colors border border-slate-700 disabled:opacity-50"
                        >
                          {actionLoadingId === alarm.id ? 'Saving...' : 'Acknowledge'}
                        </button>
                      )}
                      {alarm.status !== 'RESOLVED' && (
                        <button
                          onClick={() => handleResolve(alarm.id)}
                          disabled={actionLoadingId === alarm.id}
                          className="rounded bg-emerald-600/90 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-500 transition-colors disabled:opacity-50"
                        >
                          {actionLoadingId === alarm.id ? 'Saving...' : 'Resolve'}
                        </button>
                      )}
                      {alarm.status === 'RESOLVED' && (
                        <span className="flex items-center gap-1 text-[11px] text-emerald-400 font-mono">
                          <CheckCircle className="h-3 w-3" />
                          Cleared
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
