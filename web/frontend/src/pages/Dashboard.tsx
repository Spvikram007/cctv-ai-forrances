import React, { useEffect, useState, useCallback } from 'react';
import {
  Camera,
  Video,
  Activity,
  HardDrive,
  Cpu,
  ShieldCheck,
  Bell,
  AlertTriangle,
  RefreshCw,
  Server,
  Radio,
  CheckCircle2,
} from 'lucide-react';
import { systemApi } from '../api/system';
import { camerasApi } from '../api/cameras';
import { alarmsApi } from '../api/alarms';
import { storageApi } from '../api/storage';
import { wsClient, WebSocketEventMessage } from '../api/ws';
import { SystemStatus, HealthResponse } from '../types/system';
import { CameraResponse } from '../types/cameras';
import { Alarm, AlarmSummary } from '../types/alarms';
import { StorageStatus } from '../types/storage';

export const Dashboard: React.FC = () => {
  const [telemetry, setTelemetry] = useState<SystemStatus | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [cameras, setCameras] = useState<CameraResponse[]>([]);
  const [alarmSummary, setAlarmSummary] = useState<AlarmSummary | null>(null);
  const [recentAlarms, setRecentAlarms] = useState<Alarm[]>([]);
  const [storageStatus, setStorageStatus] = useState<StorageStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [wsConnected, setWsConnected] = useState<boolean>(false);

  const fetchDashboardData = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      const [statusRes, healthRes, camsRes, alarmsSumRes, alarmsListRes, storageRes] =
        await Promise.allSettled([
          systemApi.getSystemStatus(),
          systemApi.getHealth(),
          camerasApi.listCameras({ limit: 12 }),
          alarmsApi.getSummary(),
          alarmsApi.listAlarms({ limit: 5 }),
          storageApi.getStatus(),
        ]);

      if (statusRes.status === 'fulfilled') setTelemetry(statusRes.value);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value);
      if (camsRes.status === 'fulfilled') setCameras(camsRes.value);
      if (alarmsSumRes.status === 'fulfilled') setAlarmSummary(alarmsSumRes.value);
      if (alarmsListRes.status === 'fulfilled') setRecentAlarms(alarmsListRes.value);
      if (storageRes.status === 'fulfilled') setStorageStatus(storageRes.value);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();

    // Connect to real-time events WebSocket
    wsClient.connect();

    const unsubscribe = wsClient.subscribe((event: WebSocketEventMessage) => {
      setWsConnected(true);
      if (event.topic.startsWith('alarm.')) {
        alarmsApi.getSummary().then(setAlarmSummary).catch(() => {});
        alarmsApi.listAlarms({ limit: 5 }).then(setRecentAlarms).catch(() => {});
      } else if (event.topic.startsWith('camera.')) {
        camerasApi.listCameras({ limit: 12 }).then(setCameras).catch(() => {});
      } else if (event.topic.startsWith('system.')) {
        systemApi.getSystemStatus().then(setTelemetry).catch(() => {});
      }
    });

    return () => {
      unsubscribe();
    };
  }, [fetchDashboardData]);

  const handleAcknowledgeAlarm = async (alarmId: string) => {
    try {
      const updated = await alarmsApi.acknowledgeAlarm(alarmId);
      setRecentAlarms((prev) => prev.map((a) => (a.id === alarmId ? updated : a)));
      alarmsApi.getSummary().then(setAlarmSummary).catch(() => {});
    } catch {
      alarmsApi.listAlarms({ limit: 5 }).then(setRecentAlarms).catch(() => {});
    }
  };

  const totalCameras = cameras.length;
  const onlineCameras = cameras.filter((c) => c.is_online).length;
  const offlineCameras = totalCameras - onlineCameras;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
            Surveillance Operations Dashboard
          </h1>
          <p className="text-xs sm:text-sm text-slate-400">
            Real-time telemetry, camera status, incident stream, and platform health.
          </p>
        </div>
        <div className="flex items-center gap-3 self-start sm:self-auto">
          {/* WebSocket Status Indicator */}
          <div className="flex items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1 text-xs font-mono border border-slate-800">
            <Radio className={`h-3 w-3 ${wsConnected ? 'text-emerald-400 animate-pulse' : 'text-amber-400'}`} />
            <span className={wsConnected ? 'text-emerald-400' : 'text-amber-400'}>
              {wsConnected ? 'WS LIVE' : 'WS POLLING'}
            </span>
          </div>

          <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-400 border border-emerald-500/20">
            <ShieldCheck className="h-3.5 w-3.5" />
            Active Surveillance
          </span>

          <button
            onClick={() => fetchDashboardData(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50"
            title="Refresh Dashboard Data"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Total Cameras */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>TOTAL CAMERAS</span>
            <Camera className="h-4 w-4 text-sky-400" />
          </div>
          <div className="my-2 text-2xl font-bold text-slate-100">{loading ? '--' : totalCameras}</div>
          <div className="text-[11px] text-slate-500 font-mono">Registered devices</div>
        </div>

        {/* Online Channels */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>ONLINE CHANNELS</span>
            <Video className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="my-2 text-2xl font-bold text-emerald-400">{loading ? '--' : onlineCameras}</div>
          <div className="text-[11px] text-slate-500 font-mono">{offlineCameras} offline / standby</div>
        </div>

        {/* Active Alarms */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>ACTIVE ALARMS</span>
            <Bell className="h-4 w-4 text-rose-400" />
          </div>
          <div className="my-2 text-2xl font-bold text-rose-400">
            {loading ? '--' : alarmSummary?.active ?? 0}
          </div>
          <div className="text-[11px] text-rose-400/80 font-mono">
            {alarmSummary?.critical ?? 0} critical incidents
          </div>
        </div>

        {/* CPU Utilization */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>CPU UTILIZATION</span>
            <Cpu className="h-4 w-4 text-amber-400" />
          </div>
          <div className="my-2 text-2xl font-bold text-slate-100">
            {telemetry ? `${telemetry.cpu_percent.toFixed(1)}%` : '--'}
          </div>
          <div className="text-[11px] text-slate-500 truncate" title={telemetry?.openvino_device || 'OpenVINO Ready'}>
            {telemetry?.openvino_device || 'OpenVINO Ready'}
          </div>
        </div>

        {/* Memory Load */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>MEMORY LOAD</span>
            <Activity className="h-4 w-4 text-purple-400" />
          </div>
          <div className="my-2 text-2xl font-bold text-slate-100">
            {telemetry ? `${telemetry.memory_percent.toFixed(1)}%` : '--'}
          </div>
          <div className="text-[11px] text-slate-500 font-mono">
            {telemetry ? `${telemetry.memory_used_mb} / ${telemetry.memory_total_mb} MB` : 'Telemetry loading'}
          </div>
        </div>

        {/* Storage Pool */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-medium">
            <span>STORAGE LEDGER</span>
            <HardDrive className="h-4 w-4 text-sky-400" />
          </div>
          <div className="my-2 text-2xl font-bold text-slate-100">
            {storageStatus?.hot_tier_status ? storageStatus.hot_tier_status.toUpperCase() : 'OK'}
          </div>
          <div className="text-[11px] text-slate-500 font-mono">
            {storageStatus?.wal_file_size_mb !== undefined
              ? `${storageStatus.wal_file_size_mb.toFixed(1)} MB WAL`
              : 'Continuous WAL'}
          </div>
        </div>
      </div>

      {/* Subsystem Health Status Bar */}
      {health && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 text-slate-300 font-medium">
            <Server className="h-4 w-4 text-sky-400" />
            <span>Platform Core Status:</span>
            <span
              className={`font-bold uppercase ${
                health.status === 'ok' ? 'text-emerald-400' : 'text-amber-400'
              }`}
            >
              {health.status}
            </span>
            <span className="text-slate-500 font-mono text-[11px] hidden sm:inline">
              (Uptime: {telemetry?.uptime_seconds ? `${(telemetry.uptime_seconds / 60).toFixed(0)}m` : 'Active'})
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono">
            {[
              { name: 'DATABASE', stat: health.database },
              { name: 'EVENT BUS', stat: health.event_bus },
              { name: 'STORAGE', stat: health.storage_engine },
              { name: 'STREAM MGR', stat: health.stream_manager },
            ].map(({ name, stat }) => (
              <span
                key={name}
                className={`flex items-center gap-1 rounded px-2 py-0.5 border ${
                  stat === 'ok' || stat === 'ready' || stat === 'healthy'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                }`}
              >
                <CheckCircle2 className="h-3 w-3" />
                {name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Two Column Grid: Camera Overview & Recent Incident Queue */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quick Camera Grid Overview */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <Video className="h-4 w-4 text-sky-400" />
                Live Camera Registry ({onlineCameras}/{totalCameras} Online)
              </h2>
              <span className="text-xs text-sky-400 font-mono">W4 Gateway Ready</span>
            </div>

            {loading ? (
              <div className="py-12 text-center text-slate-500 text-xs">Loading camera streams...</div>
            ) : cameras.length === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 text-slate-500 text-xs">
                <Camera className="h-8 w-8 mb-2 text-slate-600" />
                <span>No cameras registered in inventory.</span>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {cameras.slice(0, 6).map((cam) => (
                  <div
                    key={cam.id}
                    className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 flex flex-col justify-between hover:border-slate-700 transition-colors"
                  >
                    <div>
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-xs text-slate-200 truncate">{cam.name}</span>
                        <span
                          className={`inline-block h-2 w-2 rounded-full ${
                            cam.is_online
                              ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50'
                              : 'bg-slate-600'
                          }`}
                        />
                      </div>
                      <div className="mt-1 text-[11px] font-mono text-slate-400">{cam.ip_address}</div>
                    </div>
                    <div className="mt-2.5 flex items-center justify-between text-[10px] text-slate-500 border-t border-slate-900 pt-1.5">
                      <span>{cam.manufacturer}</span>
                      <span className="font-mono text-sky-400">{cam.is_online ? 'RTSP STREAM' : 'STANDBY'}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800/80 text-right">
            <a
              href="/devices"
              className="text-xs text-sky-400 hover:text-sky-300 font-medium inline-flex items-center gap-1"
            >
              View All Cameras &rarr;
            </a>
          </div>
        </div>

        {/* Real-time Alarm / Incident Stream */}
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-rose-400" />
                Incident & Alarm Queue
              </h2>
              <span className="text-xs text-slate-400 font-mono">
                {alarmSummary ? `${alarmSummary.total} Total` : 'Real-Time'}
              </span>
            </div>

            {loading ? (
              <div className="py-12 text-center text-slate-500 text-xs">Loading incident feed...</div>
            ) : recentAlarms.length === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 text-slate-500 text-xs">
                <CheckCircle2 className="h-8 w-8 mb-2 text-emerald-500/50" />
                <span>Zero active alarms. All camera zones secure.</span>
              </div>
            ) : (
              <div className="divide-y divide-slate-800/80">
                {recentAlarms.map((alarm) => (
                  <div key={alarm.id} className="py-2.5 flex items-start justify-between gap-3">
                    <div className="flex items-start gap-2.5">
                      <div
                        className={`rounded p-1.5 mt-0.5 border ${
                          alarm.severity === 'CRITICAL'
                            ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                            : alarm.severity === 'WARNING' || alarm.severity === 'HIGH'
                            ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                            : 'bg-sky-500/10 text-sky-400 border-sky-500/20'
                        }`}
                      >
                        <AlertTriangle className="h-3.5 w-3.5" />
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-slate-200">
                          {alarm.title}
                        </div>
                        <div className="text-[11px] text-slate-400 font-mono">
                          {alarm.camera_id ? `Cam: ${alarm.camera_id.slice(0, 8)}` : `Subsystem: ${alarm.source_subsystem}`}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-0.5">
                          {new Date(alarm.first_detected_at).toLocaleTimeString()}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-1.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-mono font-bold border ${
                          alarm.severity === 'CRITICAL'
                            ? 'bg-rose-950/80 text-rose-400 border-rose-800/50'
                            : 'bg-amber-950/80 text-amber-400 border-amber-800/50'
                        }`}
                      >
                        {alarm.severity}
                      </span>

                      {alarm.status === 'NEW' ? (
                        <button
                          onClick={() => handleAcknowledgeAlarm(alarm.id)}
                          className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700 transition-colors border border-slate-700"
                        >
                          Acknowledge
                        </button>
                      ) : (
                        <span className="text-[10px] font-mono text-emerald-400">{alarm.status}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="mt-4 pt-3 border-t border-slate-800/80 text-right">
            <a
              href="/alarms"
              className="text-xs text-rose-400 hover:text-rose-300 font-medium inline-flex items-center gap-1"
            >
              Open Alarm Center &rarr;
            </a>
          </div>
        </div>
      </div>
    </div>
  );
};
