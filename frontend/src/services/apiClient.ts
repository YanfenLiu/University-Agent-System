/** 统一 API 请求封装 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "https://saizhitong-agent2.onrender.com";

function buildUrl(path: string) {
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
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

  try {
    const response = await fetch(buildUrl(path), {
      method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const text = await response.text();
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${text}`);
    }

    return (text ? (JSON.parse(text) as T) : ({} as T));
  } finally {
    clearTimeout(timer);
  }
}
