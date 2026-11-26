import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Shield, Lock, User, AlertCircle, Loader2, Info } from 'lucide-react';

export const Login: React.FC = () => {
  const { login, isAuthenticated, error: authError, clearError } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleInputChange = (field: 'user' | 'pass', val: string) => {
    if (localError) setLocalError(null);
    if (authError) clearError();
    if (field === 'user') setUsername(val);
    if (field === 'pass') setPassword(val);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setLocalError('Please enter both operator username and password.');
      return;
    }

    setSubmitting(true);
    setLocalError(null);

    const success = await login({ username: username.trim(), password });
    if (success) {
      navigate('/dashboard', { replace: true });
    }
    setSubmitting(false);
  };

  const displayError = localError || authError;
  const isLockout = displayError?.toLowerCase().includes('locked');

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-slate-950 p-4">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900/90 p-6 shadow-2xl backdrop-blur-xl">
        {/* Header */}
        <div className="flex flex-col items-center text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-sky-500/10 border border-sky-500/30 text-sky-400 mb-3">
            <Shield className="h-6 w-6" />
          </div>
          <h1 className="text-lg font-bold text-slate-100">CCTV AI Intelligence Platform</h1>
          <p className="text-xs text-slate-400 mt-1">Authorized Surveillance Operator Console</p>
        </div>

        {/* Error Feedback Banner */}
        {displayError && (
          <div
            className={`mt-4 flex items-start gap-2.5 rounded-lg border p-3 text-xs ${
              isLockout
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
            }`}
          >
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold">{isLockout ? 'Account Lockout Enforced' : 'Authentication Error'}</div>
              <div className="mt-0.5 text-[11px] opacity-90">{displayError}</div>
            </div>
          </div>
        )}

        {/* Credentials Form */}
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Operator Username</label>
            <div className="relative">
              <User className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="text"
                value={username}
                onChange={(e) => handleInputChange('user', e.target.value)}
                placeholder="Operator ID / Username"
                autoComplete="username"
                required
                className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-9 pr-3 text-xs text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none transition-colors"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="password"
                value={password}
                onChange={(e) => handleInputChange('pass', e.target.value)}
                placeholder="••••••••••••"
                autoComplete="current-password"
                required
                className="w-full rounded-lg border border-slate-700 bg-slate-950 py-2 pl-9 pr-3 text-xs text-slate-100 placeholder:text-slate-600 focus:border-sky-500 focus:outline-none transition-colors"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 rounded-lg bg-sky-600 py-2.5 text-xs font-semibold text-white hover:bg-sky-500 disabled:opacity-50 transition-colors shadow-lg shadow-sky-600/20"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Authenticating with Core...</span>
              </>
            ) : (
              <span>Sign In to Surveillance Console</span>
            )}
          </button>
        </form>

        {/* Security Policy Reminder */}
        <div className="mt-5 flex items-start gap-2 rounded-lg bg-slate-950/60 border border-slate-800/80 p-2.5 text-[10px] text-slate-500">
          <Info className="h-3.5 w-3.5 text-sky-400 shrink-0 mt-0.5" />
          <span>
            Brute-force protection active (5 failed attempts = 15m lockout). All login attempts are recorded in the
            immutable Merkle audit ledger.
          </span>
        </div>
      </div>
    </div>
  );
};
