import React, { useEffect, useState, useCallback } from 'react';
import {
  Film,
  Calendar,
  Play,
  Pause,
  FastForward,
  Rewind,
  Camera,
  RefreshCw,
  HardDrive,
  Clock,
  Download,
} from 'lucide-react';
import { camerasApi } from '../api/cameras';
import { playbackApi } from '../api/playback';
import { CameraResponse } from '../types/cameras';
import { RecordingSegment } from '../types/playback';

export const Playback: React.FC = () => {
  const [cameras, setCameras] = useState<CameraResponse[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');
  const [recordings, setRecordings] = useState<RecordingSegment[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedDate, setSelectedDate] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [scrubPositionPercent, setScrubPositionPercent] = useState<number>(35);

  const loadCameras = async () => {
    try {
      const data = await camerasApi.listCameras({ limit: 50 });
      setCameras(data);
      if (data.length > 0 && !selectedCameraId) {
        setSelectedCameraId(data[0].id);
      }
    } catch {
      setCameras([]);
    }
  };

  const loadRecordings = useCallback(async () => {
    setLoading(true);
    try {
      const data = await playbackApi.listRecordings({
        channel_id: selectedCameraId || undefined,
        limit: 50,
      });
      setRecordings(data);
    } catch {
      setRecordings([]);
    } finally {
      setLoading(false);
    }
  }, [selectedCameraId]);

  useEffect(() => {
    loadCameras();
  }, []);

  useEffect(() => {
    if (selectedCameraId) {
      loadRecordings();
    }
  }, [selectedCameraId, loadRecordings]);

  const togglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const cycleSpeed = () => {
    const speeds = [0.5, 1.0, 2.0, 4.0, 8.0, 16.0];
    const currentIndex = speeds.indexOf(playbackSpeed);
    const nextSpeed = speeds[(currentIndex + 1) % speeds.length];
    setPlaybackSpeed(nextSpeed);
  };

  const selectedCamera = cameras.find((c) => c.id === selectedCameraId);

  return (
    <div className="space-y-4">
      {/* Title & Filter Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Film className="h-5 w-5 text-sky-400" />
            Synchronized Playback & Historical Search
          </h1>
          <p className="text-xs text-slate-400">
            Timeline scrubbing, segment retrieval, and incident evidence extraction.
          </p>
        </div>

        {/* Filter Selectors */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Camera Dropdown */}
          <div className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs">
            <Camera className="h-3.5 w-3.5 text-sky-400" />
            <select
              value={selectedCameraId}
              onChange={(e) => setSelectedCameraId(e.target.value)}
              className="bg-transparent text-slate-200 focus:outline-none"
            >
              {cameras.map((c) => (
                <option key={c.id} value={c.id} className="bg-slate-900 text-slate-200">
                  {c.name} ({c.ip_address})
                </option>
              ))}
            </select>
          </div>

          {/* Date Picker */}
          <div className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs">
            <Calendar className="h-3.5 w-3.5 text-emerald-400" />
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-transparent text-slate-200 focus:outline-none font-mono"
            />
          </div>

          <button
            onClick={loadRecordings}
            className="rounded p-1.5 bg-slate-800 border border-slate-700 text-slate-300 hover:bg-slate-700"
            title="Reload recordings"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Video Playback Container */}
      <div className="flex aspect-video w-full max-h-[50vh] flex-col items-center justify-center rounded-xl border border-slate-800 bg-slate-950 p-6 text-center relative overflow-hidden">
        <Film className="h-12 w-12 text-slate-600 mb-3" />
        <h3 className="text-sm font-semibold text-slate-200">
          {selectedCamera ? `${selectedCamera.name} Playback Feed` : 'Synchronized Playback Viewport'}
        </h3>
        <p className="text-xs text-slate-400 mt-1 max-w-md">
          {selectedCamera
            ? `Indexed timeline for ${selectedCamera.ip_address} (${selectedDate}). Segment metadata ready.`
            : 'Select a camera channel and date above to load recorded segments.'}
        </p>

        <div className="mt-3 rounded bg-slate-900/90 border border-slate-800 px-3 py-1.5 text-xs text-sky-400 font-mono">
          Milestone W4 Gateway Boundary — HLS / MP4 Video Slice Pipeline Ready
        </div>
      </div>

      {/* Scrubbing & Timeline Controls */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-4 space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-sky-400" />
            <span>Target Date: {selectedDate}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={cycleSpeed}
              className="rounded bg-slate-800 px-2 py-0.5 text-xs font-mono text-sky-400 hover:bg-slate-700"
            >
              Speed: {playbackSpeed}x
            </button>
            <span className="text-slate-500">|</span>
            <span>{recordings.length} Segments Found</span>
          </div>
        </div>

        {/* Timeline representation bar */}
        <div
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const clickX = e.clientX - rect.left;
            const pct = Math.max(0, Math.min(100, (clickX / rect.width) * 100));
            setScrubPositionPercent(pct);
          }}
          className="h-10 w-full rounded-lg bg-slate-950 border border-slate-800 relative overflow-hidden flex items-center px-2 cursor-pointer group"
        >
          {recordings.length > 0 ? (
            recordings.map((rec, i) => {
              const leftPct = (i * 18 + 5) % 80;
              const widthPct = Math.max(8, Math.min(25, rec.duration_sec / 60));
              return (
                <div
                  key={rec.id}
                  style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                  className="absolute h-full bg-emerald-500/25 border-l border-r border-emerald-500/50 hover:bg-emerald-500/40 transition-colors"
                  title={`Segment ${rec.id}: ${rec.duration_sec}s`}
                />
              );
            })
          ) : (
            <div
              style={{ left: '20%', width: '35%' }}
              className="absolute h-full bg-emerald-500/20 border-l border-r border-emerald-500/40"
            />
          )}

          {/* Current scrubber needle */}
          <div
            style={{ left: `${scrubPositionPercent}%` }}
            className="absolute top-0 bottom-0 w-0.5 bg-rose-500 shadow-sm shadow-rose-500/50 z-20 pointer-events-none"
          />

          <span className="text-[10px] font-mono text-slate-500 z-10 select-none">00:00:00</span>
          <span className="text-[10px] font-mono text-slate-500 z-10 mx-auto select-none">12:00:00</span>
          <span className="text-[10px] font-mono text-slate-500 z-10 select-none">23:59:59</span>
        </div>

        {/* Action Controls */}
        <div className="flex items-center justify-center gap-3 pt-1">
          <button
            onClick={() => setScrubPositionPercent((p) => Math.max(0, p - 5))}
            className="rounded-lg p-2 bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
            title="Step Backward"
          >
            <Rewind className="h-4 w-4" />
          </button>

          <button
            onClick={togglePlay}
            className={`rounded-lg p-2 text-white font-semibold transition-colors ${
              isPlaying ? 'bg-amber-600 hover:bg-amber-500' : 'bg-sky-600 hover:bg-sky-500'
            }`}
            title={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
          </button>

          <button
            onClick={() => setScrubPositionPercent((p) => Math.min(100, p + 5))}
            className="rounded-lg p-2 bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
            title="Step Forward"
          >
            <FastForward className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Recording Segments Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <HardDrive className="h-4 w-4 text-sky-400" />
            Recorded Segments Index
          </h2>
          <span className="text-[11px] text-slate-500 font-mono">
            {recordings.length} Indexed Clips
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 text-[11px] font-semibold uppercase text-slate-400">
              <tr>
                <th className="py-2.5 px-3">Segment ID</th>
                <th className="py-2.5 px-3">Start Time</th>
                <th className="py-2.5 px-3">End Time</th>
                <th className="py-2.5 px-3">Duration</th>
                <th className="py-2.5 px-3">File Size</th>
                <th className="py-2.5 px-3">Codec</th>
                <th className="py-2.5 px-3 text-right">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-500 font-sans">
                    Querying recording ledger...
                  </td>
                </tr>
              ) : recordings.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-6 text-center text-slate-500 font-sans">
                    No recorded segments indexed for this camera on the selected date.
                  </td>
                </tr>
              ) : (
                recordings.map((rec) => (
                  <tr key={rec.id} className="hover:bg-slate-800/30">
                    <td className="py-2 px-3 text-slate-400 truncate max-w-[120px]">{rec.id}</td>
                    <td className="py-2 px-3 text-slate-300">
                      {new Date(rec.start_time).toLocaleTimeString()}
                    </td>
                    <td className="py-2 px-3 text-slate-300">
                      {rec.end_time ? new Date(rec.end_time).toLocaleTimeString() : 'In Progress'}
                    </td>
                    <td className="py-2 px-3 text-slate-400">{rec.duration_sec.toFixed(0)}s</td>
                    <td className="py-2 px-3 text-slate-400">{rec.file_size_mb.toFixed(1)} MB</td>
                    <td className="py-2 px-3 text-sky-400">{rec.codec.toUpperCase()}</td>
                    <td className="py-2 px-3 text-right">
                      <button
                        className="rounded p-1 text-slate-400 hover:text-sky-400 transition-colors"
                        title="Download segment clip"
                      >
                        <Download className="h-3.5 w-3.5 inline" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
