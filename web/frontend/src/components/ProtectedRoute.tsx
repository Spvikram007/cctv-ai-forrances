import React from 'react';
import { Navigate, Outlet, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ShieldAlert, Loader2, ArrowLeft } from 'lucide-react';

interface ProtectedRouteProps {
  permission?: string;
  anyPermissions?: string[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ permission, anyPermissions }) => {
  const { user, isAuthenticated, isLoading, hasPermission, hasAnyPermission } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-slate-950 text-slate-100">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-sky-500" />
          <p className="text-xs font-medium text-slate-400">Verifying surveillance session...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const isDenied =
    (permission && !hasPermission(permission)) ||
    (anyPermissions && !hasAnyPermission(anyPermissions));

  if (isDenied) {
    return (
      <div className="flex h-full min-h-[60vh] w-full flex-col items-center justify-center p-6 text-center">
        <div className="rounded-2xl bg-rose-500/10 p-5 text-rose-500 mb-4 border border-rose-500/20">
          <ShieldAlert className="h-12 w-12" />
        </div>
        <h2 className="text-xl font-bold text-slate-100">403 — Unauthorized Surveillance Access</h2>
        <p className="mt-2 max-w-md text-xs text-slate-400">
          Operator <strong className="text-slate-200">{user?.username}</strong> with role{' '}
          <span className="font-mono text-sky-400">{user?.role_name}</span> is not authorized to access this workspace.
        </p>
        {permission && (
          <div className="mt-3">
            <span className="text-[11px] text-slate-500 mr-2">Required Permission:</span>
            <code className="rounded bg-slate-900 border border-slate-800 px-2 py-1 font-mono text-xs text-rose-400">
              {permission}
            </code>
          </div>
        )}
        <Link
          to="/dashboard"
          className="mt-6 flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition-colors border border-slate-700"
        >
          <ArrowLeft className="h-4 w-4" />
          Return to Operations Dashboard
        </Link>
      </div>
    );
  }

  return <Outlet />;
};
