import { request } from './apiClient';
import type { LoginRequest, RegisterRequest, TokenResponse, UserInfo, UserPortrait } from './authTypes';

const TOKEN_KEY = 'saizhitong_refresh_token';
const USER_KEY = 'saizhitong_user';

// ---- Token storage ----

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): UserInfo | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function storeAuth(refreshToken: string, user: UserInfo): void {
  localStorage.setItem(TOKEN_KEY, refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

// ---- API calls ----

export async function login(req: LoginRequest): Promise<TokenResponse> {
  const data = await request<TokenResponse>('/api/auth/login', {
    method: 'POST',
    body: req,
  });
  storeAuth(data.refresh_token, data.user);
  return data;
}

export async function register(req: RegisterRequest): Promise<TokenResponse> {
  const data = await request<TokenResponse>('/api/auth/register', {
    method: 'POST',
    body: req,
  });
  storeAuth(data.refresh_token, data.user);
  return data;
}

export async function refreshAccessToken(): Promise<TokenResponse | null> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) return null;
  try {
    const data = await request<TokenResponse>('/api/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
      // Don't use auth header for refresh calls — no access token yet
    });
    storeAuth(data.refresh_token, data.user);
    return data;
  } catch {
    clearAuth();
    return null;
  }
}

export async function logout(): Promise<void> {
  const refreshToken = getStoredRefreshToken();
  try {
    await request('/api/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken || '' },
    });
  } catch {
    // Even if the server call fails, clear local state
  }
  clearAuth();
}

export async function fetchCurrentUser(): Promise<UserInfo | null> {
  try {
    return await request<UserInfo>('/api/auth/me');
  } catch {
    return null;
  }
}

export async function updateProfile(fields: { display_name?: string; avatar?: string }): Promise<UserInfo | null> {
  try {
    const user = await request<UserInfo>('/api/auth/me', { method: 'PATCH', body: fields });
    const stored = getStoredUser();
    if (stored) {
      localStorage.setItem(USER_KEY, JSON.stringify({ ...stored, ...user }));
    }
    return user;
  } catch {
    return null;
  }
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await request('/api/auth/me/password', {
    method: 'PUT',
    body: { old_password: oldPassword, new_password: newPassword },
  });
}

export async function deleteAccount(): Promise<void> {
  await request('/api/auth/me', { method: 'DELETE' });
  clearAuth();
}

export async function fetchPortrait(): Promise<UserPortrait | null> {
  try {
    const data = await request<{ portrait: UserPortrait }>('/api/auth/me/portrait');
    return data.portrait;
  } catch {
    return null;
  }
}
