import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { UserInfo } from '../services/authTypes';
import {
  getStoredRefreshToken,
  getStoredUser,
  clearAuth as clearStoredAuth,
  refreshAccessToken,
} from '../services/authService';
import { setTokenProvider, setRefreshCallback } from '../services/apiClient';

interface AuthContextType {
  user: UserInfo | null;
  accessToken: string | null;
  loading: boolean;
  setAuth: (accessToken: string, user: UserInfo) => void;
  clearAuth: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserInfo | null>(getStoredUser);
  const [loading, setLoading] = useState(!!getStoredRefreshToken());

  const doClearAuth = useCallback(() => {
    clearStoredAuth();
    setAccessToken(null);
    setUser(null);
  }, []);

  const setAuth = useCallback((token: string, u: UserInfo) => {
    setAccessToken(token);
    setUser(u);
  }, []);

  // Wire token provider and refresh callback into apiClient
  useEffect(() => {
    setTokenProvider(() => accessToken);
    setRefreshCallback(async () => {
      const result = await refreshAccessToken();
      if (result) {
        setAccessToken(result.access_token);
        setUser(result.user);
        return result.access_token;
      }
      clearStoredAuth();
      setAccessToken(null);
      setUser(null);
      return null;
    });
  }, [accessToken]);

  // On mount: try to refresh using stored refresh token
  useEffect(() => {
    const storedRefresh = getStoredRefreshToken();
    if (!storedRefresh) {
      setLoading(false);
      return;
    }
    refreshAccessToken()
      .then((result) => {
        if (result) {
          setAccessToken(result.access_token);
          setUser(result.user);
        } else {
          clearStoredAuth();
          setUser(null);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        loading,
        setAuth,
        clearAuth: doClearAuth,
        isAdmin: user?.role === 'admin',
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
