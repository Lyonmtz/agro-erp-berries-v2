const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export function extractErrorMessage(detail: unknown, fallback: string): string {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === "string") return obj.code ? `[${obj.code}] ${obj.message}` : obj.message;
    if (typeof obj.detail === "string") return obj.detail;
    if (obj.detail && typeof obj.detail === "object") {
      return extractErrorMessage(obj.detail, fallback);
    }
    if (Array.isArray(obj.detail)) {
      return obj.detail
        .map((e: Record<string, unknown>) => `${(e.loc as string[] | undefined)?.join(".") || ""}: ${e.msg}`)
        .join(" | ");
    }
  }
  return fallback;
}

export async function apiRequest<T>(
  path: string,
  options: {
    method?: string;
    token?: string | null;
    body?: unknown;
  } = {}
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const text = await resp.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!resp.ok) {
    const msg = extractErrorMessage(parsed, `HTTP ${resp.status}`);
    throw new ApiError(resp.status, msg, parsed);
  }
  return parsed as T;
}
