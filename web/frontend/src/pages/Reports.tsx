import React, { useEffect, useState, useCallback } from 'react';
import {
  FileText,
  Download,
  ShieldCheck,
  ShieldAlert,
  RefreshCw,
  Search,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { reportsApi } from '../api/reports';
import { AuditLogEntry, AuditIntegrity } from '../types/reports';

export const Reports: React.FC = () => {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [integrity, setIntegrity] = useState<AuditIntegrity | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [verifying, setVerifying] = useState<boolean>(false);
  const [search, setSearch] = useState<string>('');

  const loadReportData = useCallback(async () => {
    setLoading(true);
    try {
      const [logsData, integrityData] = await Promise.all([
        reportsApi.listAuditLogs({ limit: 50 }),
        reportsApi.verifyIntegrity(),
      ]);
      setLogs(logsData);
      setIntegrity(integrityData);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReportData();
  }, [loadReportData]);

  const handleVerifyNow = async () => {
    setVerifying(true);
    try {
      const res = await reportsApi.verifyIntegrity();
      setIntegrity(res);
    } finally {
      setVerifying(false);
    }
  };

  const handleExportCSV = () => {
    if (logs.length === 0) return;

    const headers = ['Timestamp', 'Username', 'Action', 'Category', 'Status', 'Record Hash', 'Prev Hash'];
    const rows = logs.map((l) => [
      `"${l.created_at}"`,
      `"${l.username}"`,
      `"${l.action}"`,
      `"${l.category}"`,
      `"${l.status}"`,
      `"${l.record_hash ?? ''}"`,
      `"${l.prev_hash ?? ''}"`,
    ]);

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `cctv_audit_ledger_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const filteredLogs = logs.filter(
    (l) =>
      l.action.toLowerCase().includes(search.toLowerCase()) ||
      l.username.toLowerCase().includes(search.toLowerCase()) ||
      l.category.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      {/* Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <FileText className="h-5 w-5 text-sky-400" />
            Cryptographic Audit Ledger & Compliance Reports
          </h1>
          <p className="text-xs text-slate-400">
            Forensic incident dossiers, compliance verification, and tamper-evident CSV exports.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-500 transition-colors shadow-sm"
          >
            <Download className="h-3.5 w-3.5" />
            Export CSV
          </button>
          <button
            onClick={handleVerifyNow}
            disabled={verifying}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${verifying ? 'animate-spin' : ''}`} />
            Verify Hash Chain
          </button>
        </div>
      </div>

      {/* Merkle Hash Chain Integrity Banner */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-start gap-3">
            <div
              className={`rounded-lg p-2.5 border ${
                integrity?.is_valid
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              }`}
            >
              {integrity?.is_valid ? <ShieldCheck className="h-6 w-6" /> : <ShieldAlert className="h-6 w-6" />}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-slate-100">
                  SHA-256 Merkle Chain Integrity
                </span>
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-mono font-bold border ${
                    integrity?.is_valid
                      ? 'bg-emerald-950/70 text-emerald-400 border-emerald-800/40'
                      : 'bg-rose-950/70 text-rose-400 border-rose-800/40'
                  }`}
                >
                  {integrity?.is_valid ? 'CRYPTOGRAPHICALLY VERIFIED' : 'INTEGRITY ALERT'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {integrity?.details || 'Validating cryptographic audit chain against tamper-evident ledger...'}
              </p>
              <div className="text-[11px] font-mono text-slate-500 mt-1">
                Verified Records: <span className="text-slate-300">{integrity?.record_count ?? '--'}</span> • Algorithm:{' '}
                <span className="text-sky-400">{integrity?.algorithm || 'SHA-256'}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Search Filter */}
      <div className="flex items-center gap-3 bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
        <Search className="h-4 w-4 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter audit log by action, username, or category..."
          className="w-full bg-transparent text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none"
        />
      </div>

      {/* Audit Logs Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            <tr>
              <th className="py-3 px-4">Status</th>
              <th className="py-3 px-4">Timestamp</th>
              <th className="py-3 px-4">Operator</th>
              <th className="py-3 px-4">Action</th>
              <th className="py-3 px-4">Category</th>
              <th className="py-3 px-4">Record Hash (SHA-256)</th>
              <th className="py-3 px-4">Previous Hash</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
            {loading ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500 font-sans">
                  Querying immutable audit ledger...
                </td>
              </tr>
            ) : filteredLogs.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500 font-sans">
                  No audit log entries matched the filter criteria.
                </td>
              </tr>
            ) : (
              filteredLogs.map((entry) => (
                <tr key={entry.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-2.5 px-4 font-sans">
                    {entry.status === 'success' ? (
                      <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-bold">
                        <CheckCircle className="h-3 w-3" />
                        SUCCESS
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-rose-400 text-[10px] font-bold">
                        <XCircle className="h-3 w-3" />
                        FAILED
                      </span>
                    )}
                  </td>
                  <td className="py-2.5 px-4 text-slate-300">
                    {new Date(entry.created_at).toLocaleString()}
                  </td>
                  <td className="py-2.5 px-4 font-sans font-medium text-slate-200">
                    {entry.username}
                  </td>
                  <td className="py-2.5 px-4 text-sky-400 font-bold">{entry.action}</td>
                  <td className="py-2.5 px-4 text-slate-400 font-sans">{entry.category}</td>
                  <td className="py-2.5 px-4 text-slate-400 truncate max-w-[120px]" title={entry.record_hash ?? ''}>
                    {entry.record_hash ? `${entry.record_hash.slice(0, 16)}...` : '--'}
                  </td>
                  <td className="py-2.5 px-4 text-slate-500 truncate max-w-[120px]" title={entry.prev_hash ?? ''}>
                    {entry.prev_hash ? `${entry.prev_hash.slice(0, 16)}...` : '--'}
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
