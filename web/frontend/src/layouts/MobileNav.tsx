import React from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { PermissionCodes } from '../utils/permissions';
import { LayoutDashboard, Video, Camera, Bell, Settings } from 'lucide-react';

interface MobileNavItem {
  name: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
  permission?: string;
}

const mobileNavItems: MobileNavItem[] = [
  { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard, permission: PermissionCodes.DASHBOARD_VIEW },
  { name: 'Live', path: '/live', icon: Video, permission: PermissionCodes.LIVE_VIEW },
  { name: 'Devices', path: '/devices', icon: Camera, permission: PermissionCodes.LIVE_VIEW },
  { name: 'Alarms', path: '/alarms', icon: Bell, permission: PermissionCodes.ALARM_VIEW },
  { name: 'Settings', path: '/settings', icon: Settings, permission: PermissionCodes.SYSTEM_CONFIG },
];

export const MobileNav: React.FC = () => {
  const { hasPermission } = useAuth();
  const authorized = mobileNavItems.filter((i) => !i.permission || hasPermission(i.permission));

  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-slate-800 bg-slate-900/95 backdrop-blur-md px-2 py-1.5 flex justify-around items-center">
      {authorized.map((item) => (
        <NavLink
          key={item.path}
          to={item.path}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 rounded-md px-3 py-1 text-[10px] font-medium transition-colors ${
              isActive ? 'text-sky-400 font-bold' : 'text-slate-400 hover:text-slate-200'
            }`
          }
        >
          <item.icon className="h-4 w-4" />
          <span>{item.name}</span>
        </NavLink>
      ))}
    </nav>
  );
};
