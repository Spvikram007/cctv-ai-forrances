import React, { useEffect, useState } from 'react';
import {
  Video,
  Grid,
  ChevronRight,
  Radio,
  RefreshCw,
  X,
  Layers,
} from 'lucide-react';
import { camerasApi } from '../api/cameras';
import { CameraResponse } from '../types/cameras';

export const LiveView: React.FC = () => {
  const [cameras, setCameras] = useState<CameraResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [gridSize, setGridSize] = useState<number>(4);
  const [selectedSlot, setSelectedSlot] = useState<number>(0);
  const [slotAssignments, setSlotAssignments] = useState<(CameraResponse | null)[]>(
    Array(16).fill(null)
  );
  const [showCameraDrawer, setShowCameraDrawer] = useState<boolean>(true);

  const loadCameras = async () => {
    setLoading(true);
    try {
      const data = await camerasApi.listCameras({ limit: 50 });
      setCameras(data);
      setSlotAssignments((prev) => {
        const next = [...prev];
        data.forEach((cam, idx) => {
          if (idx < 16 && !next[idx]) {
            next[idx] = cam;
          }
        });
        return next;
      });
    } catch {
      setCameras([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCameras();
  }, []);

  const assignCameraToSlot = (camera: CameraResponse) => {
    setSlotAssignments((prev) => {
      const next = [...prev];
      next[selectedSlot] = camera;
      return next;
    });
  };

  const clearSlot = (idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSlotAssignments((prev) => {
      const next = [...prev];
      next[idx] = null;
      return next;
    });
  };

  return (
    <div className="space-y-4">
      {/* Header Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Video className="h-5 w-5 text-sky-400" />
            Live Multi-Channel Monitoring
          </h1>
          <p className="text-xs text-slate-400">
            Real-time multi-tile surveillance matrix with shared frame buffer architecture (W4 Gateway Boundary).
          </p>
        </div>

        {/* Matrix Grid Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 mr-1 hidden sm:inline">Matrix:</span>
          {[1, 4, 9, 16].map((size) => (
            <button
              key={size}
              onClick={() => setGridSize(size)}
              className={`rounded px-2.5 py-1 text-xs font-mono font-medium transition-colors ${
                gridSize === size
                  ? 'bg-sky-500 text-white font-bold'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {Math.sqrt(size)}x{Math.sqrt(size)}
            </button>
          ))}

          <button
            onClick={() => setShowCameraDrawer(!showCameraDrawer)}
            className={`ml-2 flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-medium border transition-colors ${
              showCameraDrawer
                ? 'bg-slate-800 border-sky-500/50 text-sky-400'
                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <Layers className="h-3.5 w-3.5" />
            Cameras
          </button>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Video Viewport Matrix */}
        <div className="flex-1">
          <div
            className={`grid gap-2.5 ${
              gridSize === 1
                ? 'grid-cols-1'
                : gridSize === 4
                ? 'grid-cols-1 sm:grid-cols-2'
                : gridSize === 9
                ? 'grid-cols-2 sm:grid-cols-3'
                : 'grid-cols-2 sm:grid-cols-4'
            }`}
          >
            {Array.from({ length: gridSize }).map((_, idx) => {
              const assigned = slotAssignments[idx];
              const isSelected = selectedSlot === idx;

              return (
                <div
                  key={idx}
                  onClick={() => setSelectedSlot(idx)}
                  className={`relative flex aspect-video flex-col justify-between rounded-lg border bg-slate-950 p-2.5 overflow-hidden shadow-inner cursor-pointer transition-all ${
                    isSelected
                      ? 'border-sky-500 ring-1 ring-sky-500/50'
                      : 'border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Slot Top Bar */}
                  <div className="flex items-center justify-between text-xs text-slate-300 z-10">
                    <span className="font-semibold bg-slate-900/90 px-2 py-0.5 rounded border border-slate-800 truncate max-w-[150px]">
                      {assigned ? assigned.name : `Slot ${idx + 1} (Empty)`}
                    </span>

                    <div className="flex items-center gap-1.5">
                      {assigned ? (
                        <>
                          <span
                            className={`flex items-center gap-1 font-mono text-[10px] px-2 py-0.5 rounded border ${
                              assigned.is_online
                                ? 'bg-emerald-950/70 text-emerald-400 border-emerald-800/40'
                                : 'bg-slate-900 text-slate-500 border-slate-800'
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                assigned.is_online ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'
                              }`}
                            />
                            {assigned.is_online ? 'READY' : 'STANDBY'}
                          </span>
                          <button
                            onClick={(e) => clearSlot(idx, e)}
                            className="rounded p-0.5 text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                            title="Unassign Slot"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </>
                      ) : (
                        <span className="text-[10px] font-mono text-slate-600 bg-slate-900/80 px-1.5 py-0.5 rounded">
                          SELECT
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Video Placeholder / Frame Container */}
                  <div className="flex flex-col items-center justify-center text-slate-500 text-xs my-auto text-center px-4">
                    {assigned ? (
                      <>
                        <Video className="h-7 w-7 text-sky-500/60 mb-2" />
                        <span className="font-mono text-slate-300 font-semibold">{assigned.name}</span>
                        <span className="text-[10px] font-mono text-slate-500">{assigned.ip_address}</span>
                        <div className="mt-2 rounded bg-slate-900/90 border border-slate-800 px-2 py-1 text-[10px] text-sky-400 font-mono">
                          StreamManager Gateway Pipeline (W4 Delivery Boundary)
                        </div>
                        <span className="text-[9px] text-slate-600 mt-1">
                          No duplicate RTSP connections • Consuming decoded frame buffer
                        </span>
                      </>
                    ) : (
                      <>
                        <Grid className="h-6 w-6 text-slate-700 mb-1" />
                        <span className="text-slate-500 text-[11px]">Click to assign camera</span>
                        <span className="text-[10px] text-slate-600">Select from camera sidebar</span>
                      </>
                    )}
                  </div>

                  {/* Slot Bottom Bar */}
                  <div className="flex items-center justify-between text-[10px] text-slate-400 border-t border-slate-900 pt-1.5 z-10">
                    <span className="truncate">
                      {assigned ? `${assigned.manufacturer} • ${assigned.device_type}` : 'Unassigned'}
                    </span>
                    <span className="font-mono text-slate-500">
                      {assigned ? 'MAIN 1080p @ 25 FPS' : '--'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Camera Selector Sidebar */}
        {showCameraDrawer && (
          <div className="w-64 flex-shrink-0 rounded-xl border border-slate-800 bg-slate-900/40 p-3 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-2">
                <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Radio className="h-3.5 w-3.5 text-sky-400" />
                  Cameras ({cameras.length})
                </span>
                <button
                  onClick={loadCameras}
                  className="rounded p-1 text-slate-400 hover:text-slate-200"
                  title="Reload cameras"
                >
                  <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                </button>
              </div>

              <div className="text-[11px] text-slate-400 mb-2">
                Assigning to <span className="font-bold text-sky-400">Slot {selectedSlot + 1}</span>:
              </div>

              <div className="space-y-1.5 max-h-[60vh] overflow-y-auto pr-1">
                {cameras.length === 0 ? (
                  <div className="py-6 text-center text-slate-500 text-xs">No cameras found.</div>
                ) : (
                  cameras.map((cam) => (
                    <button
                      key={cam.id}
                      onClick={() => assignCameraToSlot(cam)}
                      className="w-full text-left rounded-lg border border-slate-800/80 bg-slate-950/70 p-2 hover:border-sky-500/50 hover:bg-slate-800/50 transition-colors flex items-center justify-between group"
                    >
                      <div className="truncate pr-2">
                        <div className="text-xs font-semibold text-slate-200 truncate group-hover:text-sky-300">
                          {cam.name}
                        </div>
                        <div className="text-[10px] font-mono text-slate-400">{cam.ip_address}</div>
                      </div>
                      <ChevronRight className="h-3.5 w-3.5 text-slate-600 group-hover:text-sky-400 flex-shrink-0" />
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="mt-3 pt-2 border-t border-slate-800 text-[10px] text-slate-500">
              Click any camera to bind it to the currently highlighted viewport tile.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
