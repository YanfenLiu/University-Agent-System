/** 统一 API 请求封装，支持 JWT Bearer token 注入和自动刷新 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "https://saizhitong-agent2.onrender.com";

function buildUrl(path: string) {
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export function apiUrl(path: string) {
  return buildUrl(path);
}

// Token provider — set by AuthContext
let tokenProvider: (() => string | null) | null = null;
export function setTokenProvider(provider: () => string | null) {
  tokenProvider = provider;
}

// Refresh callback — set by AuthContext
let refreshCallback: (() => Promise<string | null>) | null = null;
export function setRefreshCallback(cb: () => Promise<string | null>) {
  refreshCallback = cb;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  headers?: Record<string, string>;
  body?: unknown;
  timeout?: number;
}

export async function request<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", headers = {}, body, timeout = 120000 } = options;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  const doFetch = async (): Promise<Response> => {
    const authHeaders: Record<string, string> = {};
    const token = tokenProvider?.();
    if (token) {
      authHeaders["Authorization"] = `Bearer ${token}`;
    }

    return fetch(buildUrl(path), {
      method,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  };

  try {
    let response = await doFetch();

    // Auto-refresh on 401
    if (response.status === 401 && refreshCallback) {
      const newToken = await refreshCallback();
      if (newToken) {
        response = await doFetch();
      }
    }

    const text = await response.text();
    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("saizhitong_refresh_token");
        localStorage.removeItem("saizhitong_user");
      }
      let detail = text;
      try {
        const parsed = JSON.parse(text);
        detail = parsed.detail || text;
      } catch {
        // not JSON, use raw text
      }
      throw new Error(detail);
    }

    return text ? (JSON.parse(text) as T) : ({} as T);
  } finally {
    clearTimeout(timer);
  }
}
