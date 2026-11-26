import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { AppLayout } from './layouts/AppLayout';
import { PermissionCodes } from './utils/permissions';

// Workspaces
import { Dashboard } from './pages/Dashboard';
import { LiveView } from './pages/LiveView';
import { Devices } from './pages/Devices';
import { Playback } from './pages/Playback';
import { Alarms } from './pages/Alarms';
import { Analytics } from './pages/Analytics';
import { Storage } from './pages/Storage';
import { Reports } from './pages/Reports';
import { Users } from './pages/Users';
import { Settings } from './pages/Settings';
import { Login } from './pages/Login';
import { NotFound } from './pages/NotFound';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public Authentication Route */}
          <Route path="/login" element={<Login />} />

          {/* Protected Surveillance Console Shell */}
          <Route element={<ProtectedRoute />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />

              {/* 1. Dashboard Workspace */}
              <Route element={<ProtectedRoute permission={PermissionCodes.DASHBOARD_VIEW} />}>
                <Route path="/dashboard" element={<Dashboard />} />
              </Route>

              {/* 2. Live Multi-Camera Monitoring */}
              <Route element={<ProtectedRoute permission={PermissionCodes.LIVE_VIEW} />}>
                <Route path="/live" element={<LiveView />} />
              </Route>

              {/* 3. Camera Devices Inventory */}
              <Route element={<ProtectedRoute permission={PermissionCodes.LIVE_VIEW} />}>
                <Route path="/devices" element={<Devices />} />
              </Route>

              {/* 4. Video Playback & Scrubbing */}
              <Route element={<ProtectedRoute permission={PermissionCodes.PLAYBACK_VIEW} />}>
                <Route path="/playback" element={<Playback />} />
              </Route>

              {/* 5. Alarms & Incident Center */}
              <Route element={<ProtectedRoute permission={PermissionCodes.ALARM_VIEW} />}>
                <Route path="/alarms" element={<Alarms />} />
              </Route>

              {/* 6. AI Behavioral Analytics */}
              <Route element={<ProtectedRoute permission={PermissionCodes.AI_VIEW} />}>
                <Route path="/analytics" element={<Analytics />} />
              </Route>

              {/* 7. Enterprise Storage Pools */}
              <Route element={<ProtectedRoute permission={PermissionCodes.STORAGE_MANAGE} />}>
                <Route path="/storage" element={<Storage />} />
              </Route>

              {/* 8. Audit Ledger & Compliance Reports */}
              <Route element={<ProtectedRoute permission={PermissionCodes.AUDIT_VIEW} />}>
                <Route path="/reports" element={<Reports />} />
              </Route>

              {/* 9. User Accounts & Active Sessions */}
              <Route element={<ProtectedRoute permission={PermissionCodes.USER_MANAGE} />}>
                <Route path="/users" element={<Users />} />
              </Route>

              {/* 10. Platform Settings & LAN Whitelist */}
              <Route element={<ProtectedRoute permission={PermissionCodes.SYSTEM_CONFIG} />}>
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Route>
          </Route>

          {/* Fallback 404 Route */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
