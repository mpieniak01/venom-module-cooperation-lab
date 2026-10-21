export const API = "/api/v1/cooperation-lab";
export class ApiError extends Error {
  constructor(readonly code: string, readonly status: number) { super(code); }
}
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(10000);
  const response = await fetch(API + path, { ...init, signal: init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout, cache: "no-store" });
  if (!response.ok) {
    let code = "request_failed";
    try {
      const body = await response.json();
      const detail = body.detail ?? body;
      const candidate = typeof detail === "string" ? detail : detail.reason_code ?? detail.code;
      if (typeof candidate === "string" && /^[a-z0-9_]{1,80}$/.test(candidate)) code = candidate;
    } catch { /* Never render HTML error responses or arbitrary server paths. */ }
    throw new ApiError(code, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function failureCode(error: unknown) { return error instanceof ApiError ? error.code : "connection_unavailable"; }
