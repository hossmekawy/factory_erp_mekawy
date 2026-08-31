"use client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

export function getAccess() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access");
}

export function setTokens(access: string, refresh?: string) {
  localStorage.setItem("access", access);
  if (refresh) localStorage.setItem("refresh", refresh);
}

export function clearTokens() {
  localStorage.removeItem("access");
  localStorage.removeItem("refresh");
}

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem("refresh");
  if (!refresh) return false;
  const res = await fetch(`${API_BASE}/api/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) return false;
  const data = await res.json();
  setTokens(data.access, data.refresh);
  return true;
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, data: unknown) {
    super(`API ${status}`);
    this.status = status;
    this.data = data;
  }
}

export async function api(
  path: string,
  options: RequestInit = {},
  retry = true
): Promise<any> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  const token = getAccess();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401 && retry && (await tryRefresh())) {
    return api(path, options, false);
  }
  if (res.status === 401) {
    clearTokens();
    if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
      location.href = "/login";
    }
  }
  if (!res.ok) {
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {}
    throw new ApiError(res.status, data);
  }
  if (res.status === 204) return null;
  return res.json();
}

export async function downloadFile(path: string, filename: string) {
  const token = getAccess();
  const res = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, null);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError && e.data && typeof e.data === "object") {
    const d = e.data as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    const parts: string[] = [];
    for (const [k, v] of Object.entries(d)) {
      parts.push(`${k}: ${Array.isArray(v) ? v.join("، ") : String(v)}`);
    }
    if (parts.length) return parts.join(" — ");
  }
  return "حدث خطأ غير متوقع، حاول مرة أخرى";
}
