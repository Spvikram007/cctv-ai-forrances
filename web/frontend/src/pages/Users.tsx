import React, { useEffect, useState } from 'react';
import { Users as UsersIcon, Shield, Key, Clock, RefreshCw, XCircle, CheckCircle2 } from 'lucide-react';
import { authApi } from '../api/auth';
import { usersApi } from '../api/users';
import { SessionInfo } from '../types/auth';
import { UserAccount, RoleInfo } from '../types/users';

export const Users: React.FC = () => {
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'users' | 'roles' | 'sessions'>('users');
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    try {
      const [usersData, rolesData, sessionsData] = await Promise.all([
        usersApi.listUsers().catch(() => []),
        usersApi.listRoles().catch(() => []),
        authApi.listSessions().catch(() => []),
      ]);
      setUsers(usersData);
      setRoles(rolesData);
      setSessions(sessionsData);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRevokeSession = async (sessionId: string) => {
    setRevokingId(sessionId);
    try {
      await authApi.revokeSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <UsersIcon className="h-5 w-5 text-sky-400" />
            Operator Administration & RBAC Management
          </h1>
          <p className="text-xs text-slate-400">
            Manage surveillance accounts, fine-grained permission roles, and active operator sessions.
          </p>
        </div>

        <button
          onClick={loadData}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700 transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <UsersIcon className="h-4 w-4 text-sky-400" />
            Operator Accounts
          </div>
          <div className="mt-2 text-xl font-bold text-slate-100">{loading ? '--' : users.length} Users</div>
          <div className="mt-1 text-xs text-slate-500">Configured in authentication store</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <Shield className="h-4 w-4 text-emerald-400" />
            Configured RBAC Roles
          </div>
          <div className="mt-2 text-xl font-bold text-emerald-400">{loading ? '--' : roles.length} Roles</div>
          <div className="mt-1 text-xs text-slate-500">Granular permission profiles</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
            <Clock className="h-4 w-4 text-purple-400" />
            Active LAN Sessions
          </div>
          <div className="mt-2 text-xl font-bold text-purple-400">{loading ? '--' : sessions.length}</div>
          <div className="mt-1 text-xs text-slate-500">Concurrent operator logins</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 gap-4 text-xs font-medium">
        <button
          onClick={() => setActiveTab('users')}
          className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
            activeTab === 'users'
              ? 'border-sky-500 text-sky-400 font-bold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <UsersIcon className="h-3.5 w-3.5" />
          User Directory ({users.length})
        </button>
        <button
          onClick={() => setActiveTab('roles')}
          className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
            activeTab === 'roles'
              ? 'border-sky-500 text-sky-400 font-bold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Shield className="h-3.5 w-3.5" />
          Roles & Permissions ({roles.length})
        </button>
        <button
          onClick={() => setActiveTab('sessions')}
          className={`pb-2.5 transition-colors border-b-2 flex items-center gap-1.5 ${
            activeTab === 'sessions'
              ? 'border-sky-500 text-sky-400 font-bold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Clock className="h-3.5 w-3.5" />
          Active Sessions ({sessions.length})
        </button>
      </div>

      {/* Tab 1: Users Directory */}
      {activeTab === 'users' && (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase text-slate-400">
              <tr>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Username</th>
                <th className="py-2.5 px-3">Full Name</th>
                <th className="py-2.5 px-3">Role</th>
                <th className="py-2.5 px-3">Email</th>
                <th className="py-2.5 px-3">Created Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-500">Loading users...</td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-slate-500">No user accounts found.</td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-800/30">
                    <td className="py-2.5 px-3 font-mono">
                      {!u.is_active || u.locked_until ? (
                        <span className="flex items-center gap-1 text-rose-400 text-[10px] font-bold">
                          <XCircle className="h-3.5 w-3.5" />
                          LOCKED
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-bold">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          ACTIVE
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-slate-200">{u.username}</td>
                    <td className="py-2.5 px-3 text-slate-300">{u.full_name || '--'}</td>
                    <td className="py-2.5 px-3 text-sky-400 font-medium">{u.role_name}</td>
                    <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">{u.email || '--'}</td>
                    <td className="py-2.5 px-3 text-slate-400 font-mono text-[11px]">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : '--'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Roles */}
      {activeTab === 'roles' && (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase text-slate-400">
              <tr>
                <th className="py-2.5 px-3">Role Name</th>
                <th className="py-2.5 px-3">Description</th>
                <th className="py-2.5 px-3">Permission Count</th>
                <th className="py-2.5 px-3">Permissions Matrix</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {roles.map((r) => (
                <tr key={r.id} className="hover:bg-slate-800/30">
                  <td className="py-3 px-3 font-bold text-slate-200 flex items-center gap-1.5">
                    <Key className="h-3.5 w-3.5 text-emerald-400" />
                    {r.name}
                  </td>
                  <td className="py-3 px-3 text-slate-400">{r.description || 'Standard platform role'}</td>
                  <td className="py-3 px-3 font-mono text-slate-300">{r.permission_count ?? r.permissions?.length ?? 0} Permissions</td>
                  <td className="py-3 px-3">
                    <span className="rounded bg-sky-950/60 px-2 py-0.5 text-[10px] font-mono text-sky-400 border border-sky-800/40">
                      {r.permissions?.length ?? 0} Permissions Granted
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 3: Active Sessions */}
      {activeTab === 'sessions' && (
        <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/40">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 bg-slate-950/80 text-[11px] font-semibold uppercase text-slate-500">
              <tr>
                <th className="py-2.5 px-3">Username</th>
                <th className="py-2.5 px-3">Client IP</th>
                <th className="py-2.5 px-3">Client Agent</th>
                <th className="py-2.5 px-3">Last Seen</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
              {sessions.map((s) => (
                <tr key={s.session_id} className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-sans font-medium text-slate-200">{s.username}</td>
                  <td className="py-2.5 px-3 text-slate-400">{s.ip_address || '127.0.0.1'}</td>
                  <td className="py-2.5 px-3 text-slate-500 max-w-xs truncate">{s.user_agent || 'Web Browser'}</td>
                  <td className="py-2.5 px-3 text-slate-400">{new Date(s.last_seen_at).toLocaleTimeString()}</td>
                  <td className="py-2.5 px-3">
                    {s.is_current ? (
                      <span className="text-emerald-400 font-bold">CURRENT SESSION</span>
                    ) : (
                      <span className="text-slate-400">ACTIVE</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    {!s.is_current && (
                      <button
                        onClick={() => handleRevokeSession(s.session_id)}
                        disabled={revokingId === s.session_id}
                        className="rounded bg-rose-950/80 px-2 py-0.5 text-[10px] text-rose-400 hover:bg-rose-900 border border-rose-800/50 disabled:opacity-50"
                      >
                        {revokingId === s.session_id ? 'Revoking...' : 'Revoke'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
