import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { UserProfile, LoginRequest } from '../types/auth';
import { authApi } from '../api/auth';
import { apiClient, ApiError } from '../api/client';

interface AuthContextType {
  user: UserProfile | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (credentials: LoginRequest) => Promise<boolean>;
  logout: () => Promise<void>;
  hasPermission: (permissionCode: string) => boolean;
  hasAnyPermission: (permissionCodes: string[]) => boolean;
  refreshProfile: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// 10 minutes interval for proactive session refresh
const REFRESH_INTERVAL_MS = 10 * 60 * 1000;

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem('cctv_session_token'));
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const refreshTimerRef = useRef<NodeJS.Timeout | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const handleUnauthorized = useCallback(() => {
    setUser(null);
    setToken(null);
    sessionStorage.removeItem('cctv_session_token');
    setIsLoading(false);
  }, []);

  // Subscribe to 401 Unauthorized notifications from ApiClient
  useEffect(() => {
    const unsubscribe = apiClient.onUnauthorized(handleUnauthorized);
    return () => unsubscribe();
  }, [handleUnauthorized]);

  const refreshProfile = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const profile = await authApi.getProfile();
      setUser(profile);
    } catch {
      handleUnauthorized();
    } finally {
      setIsLoading(false);
    }
  }, [handleUnauthorized]);

  // Initial session restoration on mount
  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  // Proactive periodic session refresh when authenticated
  useEffect(() => {
    if (user) {
      refreshTimerRef.current = setInterval(async () => {
        try {
          await authApi.refreshSession();
        } catch {
          // If refresh fails with 401, handleUnauthorized handles cleanup
        }
      }, REFRESH_INTERVAL_MS);
    } else {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    }

    return () => {
      if (refreshTimerRef.current) {
        clearInterval(refreshTimerRef.current);
      }
    };
  }, [user]);

  const login = async (credentials: LoginRequest): Promise<boolean> => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authApi.login(credentials);
      setToken(res.session_token);
      await refreshProfile();
      return true;
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('Authentication failed. Please verify server reachability.');
      }
      return false;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    setIsLoading(true);
    try {
      await authApi.logout();
    } catch {
      // Ignore network errors on logout
    } finally {
      handleUnauthorized();
    }
  };

  const hasPermission = useCallback(
    (permissionCode: string): boolean => {
      if (!user) return false;
      // Super Administrator has unrestricted system control
      if (user.role_name === 'Super Administrator') return true;
      return user.permissions.includes(permissionCode);
    },
    [user]
  );

  const hasAnyPermission = useCallback(
    (permissionCodes: string[]): boolean => {
      if (!user) return false;
      if (user.role_name === 'Super Administrator') return true;
      return permissionCodes.some((code) => user.permissions.includes(code));
    },
    [user]
  );

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        error,
        login,
        logout,
        hasPermission,
        hasAnyPermission,
        refreshProfile,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
