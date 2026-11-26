import React, { useEffect, useState, useCallback } from 'react';
import {
  Camera,
  Search,
  RefreshCw,
  CheckCircle,
  XCircle,
  Plus,
  Trash2,
  X,
  AlertCircle,
  Lock,
} from 'lucide-react';
import { camerasApi } from '../api/cameras';
import { CameraResponse, CameraCreateRequest } from '../types/cameras';

export const Devices: React.FC = () => {
  const [cameras, setCameras] = useState<CameraResponse[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [search, setSearch] = useState<string>('');
  const [showAddModal, setShowAddModal] = useState<boolean>(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<boolean>(false);

  // New camera form state
  const [formData, setFormData] = useState<CameraCreateRequest>({
    name: '',
    ip_address: '',
    rtsp_port: 554,
    manufacturer: 'Hikvision',
    username: 'admin',
    password: '',
    rtsp_path: '/h264Preview_01_main',
  });

  const loadCameras = useCallback(async () => {
    setLoading(true);
    try {
      const data = await camerasApi.listCameras({
        search: search.trim() || undefined,
        limit: 100,
      });
      setCameras(data);
    } catch {
      setCameras([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    loadCameras();
  }, [loadCameras]);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Validation
    if (!formData.name.trim()) {
      setFormError('Camera name is required.');
      return;
    }
    if (!formData.ip_address.trim()) {
      setFormError('IP address is required.');
      return;
    }

    setSubmitting(true);
    try {
      await camerasApi.registerCamera(formData);
      setShowAddModal(false);
      setFormData({
        name: '',
        ip_address: '',
        rtsp_port: 554,
        manufacturer: 'Hikvision',
        username: 'admin',
        password: '',
        rtsp_path: '/h264Preview_01_main',
      });
      loadCameras();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to register camera device.';
      setFormError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await camerasApi.deleteCamera(id);
      setDeleteConfirmId(null);
      loadCameras();
    } catch {
      setDeleteConfirmId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Camera className="h-5 w-5 text-sky-400" />
            Camera & Device Management
          </h1>
          <p className="text-xs text-slate-400">Inventory of ONVIF, RTSP, and physical surveillance hardware.</p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-500 transition-colors shadow-sm"
          >
            <Plus className="h-4 w-4" />
            Add Camera
          </button>
          <button
            onClick={loadCameras}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-3 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
        <Search className="h-4 w-4 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && loadCameras()}
          placeholder="Filter by camera name, IP address, or manufacturer..."
          className="w-full bg-transparent text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none"
        />
        {search && (
          <button
            onClick={() => {
              setSearch('');
            }}
            className="text-xs text-slate-400 hover:text-slate-200"
          >
            Clear
          </button>
        )}
      </div>

      {/* Camera Inventory Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <tr>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Device Name</th>
              <th className="py-3 px-4">IP Address</th>
              <th className="py-3 px-4">Manufacturer / Type</th>
              <th className="py-3 px-4">RTSP Port</th>
              <th className="py-3 px-4">Stream Channel</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {loading ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500">
                  Loading device registry...
                </td>
              </tr>
            ) : cameras.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500">
                  No camera devices found. Click "Add Camera" to register one.
                </td>
              </tr>
            ) : (
              cameras.map((cam) => (
                <tr key={cam.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-2.5 px-4 font-mono">
                    {cam.is_online ? (
                      <span className="flex items-center gap-1.5 text-emerald-400 text-[11px] font-medium">
                        <CheckCircle className="h-3.5 w-3.5" />
                        ONLINE
                      </span>
                    ) : (
                      <span className="flex items-center gap-1.5 text-slate-500 text-[11px] font-medium">
                        <XCircle className="h-3.5 w-3.5" />
                        STANDBY
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 font-medium text-slate-200">
                    <div>{cam.name}</div>
                    <div className="text-[10px] text-slate-500 font-mono">{cam.id}</div>
                  </td>
                  <td className="py-2.5 px-4 font-mono text-slate-300">{cam.ip_address}</td>
                  <td className="py-2.5 px-4 text-slate-400">
                    <div>{cam.manufacturer}</div>
                    <div className="text-[10px] text-slate-500">{cam.device_type}</div>
                  </td>
                  <td className="py-2.5 px-4 font-mono text-slate-400">{cam.rtsp_port}</td>
                  <td className="py-2.5 px-4 font-mono text-[11px] text-sky-400">
                    {cam.channel_id ? cam.channel_id.slice(0, 8) : 'Default Channel'}
                  </td>
                  <td className="py-2.5 px-4 text-right">
                    <button
                      onClick={() => setDeleteConfirmId(cam.id)}
                      className="rounded p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 transition-colors"
                      title="Delete Camera"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Add Camera Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <Camera className="h-4 w-4 text-sky-400" />
                Register New Camera Device
              </h2>
              <button
                onClick={() => setShowAddModal(false)}
                className="rounded p-1 text-slate-400 hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleRegister} className="mt-4 space-y-4">
              {formError && (
                <div className="flex items-center gap-2 rounded-lg bg-rose-500/10 p-3 text-xs text-rose-400 border border-rose-500/20">
                  <AlertCircle className="h-4 w-4 flex-shrink-0" />
                  <span>{formError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block font-medium text-slate-300 mb-1">Camera Name *</label>
                  <input
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g. North Gate Entrance"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200 focus:border-sky-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-medium text-slate-300 mb-1">IP Address *</label>
                  <input
                    type="text"
                    required
                    value={formData.ip_address}
                    onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                    placeholder="192.168.1.100"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-slate-200 focus:border-sky-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-medium text-slate-300 mb-1">RTSP Port</label>
                  <input
                    type="number"
                    value={formData.rtsp_port}
                    onChange={(e) => setFormData({ ...formData, rtsp_port: parseInt(e.target.value) || 554 })}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-slate-200 focus:border-sky-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-medium text-slate-300 mb-1">Manufacturer</label>
                  <select
                    value={formData.manufacturer}
                    onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200 focus:border-sky-500 focus:outline-none"
                  >
                    <option value="Hikvision">Hikvision</option>
                    <option value="Dahua">Dahua</option>
                    <option value="Axis">Axis Communications</option>
                    <option value="Hanwha">Hanwha Vision</option>
                    <option value="Uniview">Uniview</option>
                    <option value="Generic ONVIF">Generic ONVIF / RTSP</option>
                  </select>
                </div>

                <div>
                  <label className="block font-medium text-slate-300 mb-1">RTSP Stream Path</label>
                  <input
                    type="text"
                    value={formData.rtsp_path || ''}
                    onChange={(e) => setFormData({ ...formData, rtsp_path: e.target.value })}
                    placeholder="/h264Preview_01_main"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 font-mono text-slate-200 focus:border-sky-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block font-medium text-slate-300 mb-1">RTSP Username</label>
                  <input
                    type="text"
                    value={formData.username || ''}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    placeholder="admin"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200 focus:border-sky-500 focus:outline-none"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="block font-medium text-slate-300 mb-1 flex items-center gap-1">
                    <Lock className="h-3 w-3 text-emerald-400" />
                    RTSP Password
                  </label>
                  <input
                    type="password"
                    value={formData.password || ''}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    placeholder="Encrypted at rest"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-slate-200 focus:border-sky-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
                >
                  {submitting ? 'Registering...' : 'Register Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirmId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl border border-rose-900/60 bg-slate-900 p-6 shadow-2xl">
            <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Trash2 className="h-5 w-5 text-rose-500" />
              Confirm Camera Deletion
            </h3>
            <p className="mt-2 text-xs text-slate-400">
              Are you sure you want to delete this camera from the system? The camera session will be closed and
              historical stream references marked inactive.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirmId(null)}
                className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirmId)}
                className="rounded-lg bg-rose-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-rose-500"
              >
                Delete Device
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
