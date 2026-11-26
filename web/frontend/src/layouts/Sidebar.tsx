import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { PermissionCodes } from '../utils/permissions';
import {
  LayoutDashboard,
  Video,
  Camera,
  Film,
  Bell,
  Cpu,
  HardDrive,
  FileText,
  Users,
  Settings,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

export interface NavItemConfig {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  permission?: string;
}

export const navItems: NavItemConfig[] = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard, permission: PermissionCodes.DASHBOARD_VIEW },
  { name: 'Live Monitoring', path: '/live', icon: Video, permission: PermissionCodes.LIVE_VIEW },
  { name: 'Camera Devices', path: '/devices', icon: Camera, permission: PermissionCodes.LIVE_VIEW },
  { name: 'Video Playback', path: '/playback', icon: Film, permission: PermissionCodes.PLAYBACK_VIEW },
  { name: 'Alarm Center', path: '/alarms', icon: Bell, permission: PermissionCodes.ALARM_VIEW },
  { name: 'AI Intelligence', path: '/analytics', icon: Cpu, permission: PermissionCodes.AI_VIEW },
  { name: 'Storage Pools', path: '/storage', icon: HardDrive, permission: PermissionCodes.STORAGE_MANAGE },
  { name: 'Audit & Reports', path: '/reports', icon: FileText, permission: PermissionCodes.AUDIT_VIEW },
  { name: 'User Management', path: '/users', icon: Users, permission: PermissionCodes.USER_MANAGE },
  { name: 'System Settings', path: '/settings', icon: Settings, permission: PermissionCodes.SYSTEM_CONFIG },
];

export const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle }) => {
  const { hasPermission } = useAuth();

  // Filter navigation items based on current operator's RBAC permissions
  const authorizedItems = navItems.filter((item) => !item.permission || hasPermission(item.permission));

  return (
    <aside
      className={`hidden md:flex flex-col border-r border-slate-800 bg-slate-900/60 transition-all duration-300 z-20 select-none ${
        collapsed ? 'w-16' : 'w-56'
      }`}
    >
      {/* Navigation links */}
      <nav className="flex-1 space-y-1 p-2 overflow-y-auto">
        {authorizedItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-xs font-medium transition-colors ${
                isActive
                  ? 'bg-sky-500/10 text-sky-400 border border-sky-500/30 font-semibold'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
              }`
            }
            title={collapsed ? item.name : undefined}
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{item.name}</span>}
          </NavLink>
        ))}
      </nav>

      {/* RBAC Active Role Indicator */}
      {!collapsed && (
        <div className="mx-2 mb-2 rounded-lg bg-slate-950/70 border border-slate-800 p-2 text-[10px] text-slate-400">
          <div className="flex items-center gap-1.5 text-sky-400 font-semibold mb-0.5">
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>RBAC ENFORCED</span>
          </div>
          <div>{authorizedItems.length} of 10 Workspaces Active</div>
        </div>
      )}

      {/* Collapse Toggle Footer */}
      <div className="border-t border-slate-800 p-2">
        <button
          onClick={onToggle}
          className="flex w-full items-center justify-center gap-2 rounded-lg p-2 text-xs font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
          title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
};
