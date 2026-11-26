import React from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, ArrowLeft } from 'lucide-react';

export const NotFound: React.FC = () => {
  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-slate-950 p-6 text-center text-slate-100">
      <div className="rounded-full bg-slate-800 p-4 text-slate-400 mb-4">
        <AlertCircle className="h-10 w-10 text-sky-400" />
      </div>
      <h1 className="text-2xl font-bold">404 — Workspace Not Found</h1>
      <p className="mt-2 text-xs text-slate-400 max-w-sm">
        The requested surveillance view does not exist or has been relocated within the platform.
      </p>
      <Link
        to="/dashboard"
        className="mt-5 flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-xs font-medium text-white hover:bg-sky-500 transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Return to Operations Dashboard
      </Link>
    </div>
  );
};
