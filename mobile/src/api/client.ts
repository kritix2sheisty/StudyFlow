/**
 * src/api/client.ts
 * The phone's client for the StudyFlow API. Every call is a plain HTTP
 * request to baseUrl + path with JSON in and out. A bearer token goes on
 * the request whenever getToken() has one. Errors are typed:
 *
 *   ApiError(status, message)  the API refused; message is the API's own
 *                              {"error": ...} text, or the plain body for
 *                              a non-JSON answer (unknown routes are text)
 *   NetworkError(message)      the phone could not reach the server, or
 *                              no server is configured; names the address
 *
 * A 401 on a call that carried a token means the session is gone
 * (revoked or expired): onUnauthorized() runs before the error is thrown.
 * Login and register are sent without a token even if one is still on
 * the phone, so a 401 there is only ever a wrong password.
 * Mirrors StudyFlow/api_client.py; later milestones add methods below
 * the marker as one-liners.
 */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

export interface User {
  id: string;
  email: string;
  created_at: string;
}

export interface LoginAnswer {
  token: string;
  expires_at: string;
}

export interface RequestOptions {
  /** false for calls that never need a session (login, register). */
  auth?: boolean;
}

export interface ApiClientOptions {
  baseUrl: string;
  getToken: () => string | null;
  onUnauthorized?: () => void;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export interface ApiClient {
  request<T = unknown>(method: string, path: string, body?: unknown, options?: RequestOptions): Promise<T>;
  register(email: string, password: string): Promise<{ id: string; email: string }>;
  login(email: string, password: string): Promise<LoginAnswer>;
  logout(): Promise<void>;
  me(): Promise<User>;
}

export const DEFAULT_TIMEOUT_MS = 15_000;

export function unreachableMessage(baseUrl: string): string {
  return `Can't reach StudyFlow at ${baseUrl}. Check the API is running and this phone is on the same Wi-Fi.`;
}

export const NO_SERVER_MESSAGE =
  "No server configured. Set EXPO_PUBLIC_API_URL in mobile/.env (see .env.example).";

function messageFrom(status: number, text: string): string {
  const trimmed = text.trim();
  if (trimmed) {
    try {
      const parsed = JSON.parse(trimmed);
      if (parsed && typeof parsed.error === "string") return parsed.error;
    } catch {
      // not JSON: the body itself is the message
    }
    return trimmed;
  }
  return `The server answered ${status}.`;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const { baseUrl, getToken, onUnauthorized } = options;
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(method: string, path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
    if (!baseUrl) throw new NetworkError(NO_SERVER_MESSAGE);
    const token = options.auth === false ? null : getToken();
    const headers: Record<string, string> = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let response: Response;
    try {
      response = await fetchImpl(`${baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch {
      throw new NetworkError(unreachableMessage(baseUrl));
    } finally {
      clearTimeout(timer);
    }

    const text = await response.text();
    if (response.status >= 400) {
      if (response.status === 401 && token) onUnauthorized?.();
      throw new ApiError(response.status, messageFrom(response.status, text));
    }
    if (response.status === 204 || !text) return undefined as T;
    return JSON.parse(text) as T;
  }

  return {
    request,

    // ---- Accounts
    register: (email, password) => request("POST", "/api/auth/register", { email, password }, { auth: false }),
    login: (email, password) => request("POST", "/api/auth/login", { email, password }, { auth: false }),
    logout: () => request("POST", "/api/auth/logout"),
    me: () => request("GET", "/api/me"),

    // ---- Plan, progress, focus (M2 onward)
  };
}
