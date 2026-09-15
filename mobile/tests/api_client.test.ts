/**
 * tests/api_client.test.ts
 * The phone's API client: a bearer token on authenticated calls, JSON in
 * and out, the API's own error message when it gives one, and a message
 * that names the server when the phone cannot reach it. fetch is faked.
 */

import { ApiError, NetworkError, createApiClient } from "../src/api/client";

const BASE = "http://192.168.100.24:8010";

type Call = { url: string; init: RequestInit };

/** A fetch that answers every call with one canned reply and records what it got. */
function fakeFetch(status: number, body: string | object | null = null) {
  const calls: Call[] = [];
  const text = body === null ? "" : typeof body === "string" ? body : JSON.stringify(body);
  const impl = jest.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return { status, ok: status >= 200 && status < 300, text: async () => text } as unknown as Response;
  });
  return { impl: impl as unknown as typeof fetch, calls };
}

function headersOf(call: Call): Record<string, string> {
  return (call.init.headers ?? {}) as Record<string, string>;
}

function client(fetchImpl: typeof fetch, token: string | null = null, onUnauthorized = jest.fn()) {
  return {
    api: createApiClient({ baseUrl: BASE, getToken: () => token, onUnauthorized, fetchImpl }),
    onUnauthorized,
  };
}

test("sends the bearer header only when a token is present", async () => {
  const anon = fakeFetch(200, { token: "t", expires_at: "2026-10-13T00:00:00" });
  await client(anon.impl).api.login("ana@example.com", "a long enough password");
  expect(headersOf(anon.calls[0]).Authorization).toBeUndefined();

  const signedIn = fakeFetch(200, { id: "u1", email: "ana@example.com", created_at: "2026-09-13T00:00:00" });
  await client(signedIn.impl, "secret-token").api.me();
  expect(headersOf(signedIn.calls[0]).Authorization).toBe("Bearer secret-token");
});

test("posts JSON and parses a JSON answer", async () => {
  const f = fakeFetch(200, { token: "abc", expires_at: "2026-10-13T00:00:00" });
  const answer = await client(f.impl).api.login("Ana@Example.com", "a long enough password");
  expect(answer).toEqual({ token: "abc", expires_at: "2026-10-13T00:00:00" });
  const call = f.calls[0];
  expect(call.url).toBe(`${BASE}/api/auth/login`);
  expect(call.init.method).toBe("POST");
  expect(headersOf(call)["Content-Type"]).toBe("application/json");
  expect(JSON.parse(call.init.body as string)).toEqual({ email: "Ana@Example.com", password: "a long enough password" });
});

test("returns undefined for a 204", async () => {
  const f = fakeFetch(204);
  await expect(client(f.impl, "tok").api.logout()).resolves.toBeUndefined();
  expect(f.calls[0].url).toBe(`${BASE}/api/auth/logout`);
  expect(f.calls[0].init.method).toBe("POST");
});

test("throws ApiError with the API's status and message for a JSON error", async () => {
  const f = fakeFetch(409, { error: "That email is already registered." });
  const err = await client(f.impl).api.register("ana@example.com", "a long enough password").catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(409);
  expect(err.message).toBe("That email is already registered.");
});

test("throws ApiError with the plain text for a non-JSON error body", async () => {
  const f = fakeFetch(404, "Not Found");
  const err = (await client(f.impl, "tok").api.request("GET", "/api/nothing").catch((e) => e)) as ApiError;
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(404);
  expect(err.message).toBe("Not Found");
});

test("falls back to a generic message when the error body is empty", async () => {
  const f = fakeFetch(500);
  const err = await client(f.impl).api.login("a@b.co", "x").catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.message).toBe("The server answered 500.");
});

test("a 401 on an authenticated call invokes onUnauthorized before throwing", async () => {
  const f = fakeFetch(401, { error: "Your session has expired. Sign in again." });
  const { api, onUnauthorized } = client(f.impl, "old-token");
  const err = await api.me().catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(401);
  expect(onUnauthorized).toHaveBeenCalledTimes(1);
});

test("a 401 on login does not invoke onUnauthorized", async () => {
  const f = fakeFetch(401, { error: "Email or password is incorrect." });
  const { api, onUnauthorized } = client(f.impl);
  const err = await api.login("ana@example.com", "wrong").catch((e) => e);
  expect(err.message).toBe("Email or password is incorrect.");
  expect(onUnauthorized).not.toHaveBeenCalled();
});

test("login and register never carry a token, so a 401 there never signs out", async () => {
  // Found by the live check: with a stale token still on the phone, a wrong password
  // must read as a wrong password, not as a dead session.
  const f = fakeFetch(401, { error: "Email or password is incorrect." });
  const { api, onUnauthorized } = client(f.impl, "still-on-the-phone");
  await api.login("ana@example.com", "wrong").catch(() => undefined);
  await api.register("ana@example.com", "pw").catch(() => undefined);
  expect(f.calls.map((c) => headersOf(c).Authorization)).toEqual([undefined, undefined]);
  expect(onUnauthorized).not.toHaveBeenCalled();
});

test("a fetch failure becomes a NetworkError naming the configured server", async () => {
  const failing = jest.fn(async () => {
    throw new TypeError("Network request failed");
  }) as unknown as typeof fetch;
  const err = await client(failing).api.login("ana@example.com", "pw").catch((e) => e);
  expect(err).toBeInstanceOf(NetworkError);
  expect(err.message).toContain(BASE);
  expect(err.message).toContain("same Wi-Fi");
});

test("a timeout becomes a NetworkError", async () => {
  jest.useFakeTimers();
  try {
    const hanging = jest.fn((_url: string, init: RequestInit) => new Promise<Response>((_, reject) => {
      init.signal?.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    })) as unknown as typeof fetch;
    const api = createApiClient({ baseUrl: BASE, getToken: () => null, fetchImpl: hanging, timeoutMs: 1000 });
    const pending = api.login("ana@example.com", "pw").catch((e) => e);
    jest.advanceTimersByTime(1000);
    const err = await pending;
    expect(err).toBeInstanceOf(NetworkError);
    expect(err.message).toContain(BASE);
  } finally {
    jest.useRealTimers();
  }
});

test("an empty base URL fails before fetching with a message naming EXPO_PUBLIC_API_URL", async () => {
  const f = fakeFetch(200, {});
  const api = createApiClient({ baseUrl: "", getToken: () => null, fetchImpl: f.impl });
  const err = await api.me().catch((e) => e);
  expect(err).toBeInstanceOf(NetworkError);
  expect(err.message).toContain("EXPO_PUBLIC_API_URL");
  expect(f.calls).toHaveLength(0);
});

test("the auth methods hit the documented paths and verbs", async () => {
  const f = fakeFetch(200, { id: "u1", email: "ana@example.com", created_at: "2026-09-13T00:00:00" });
  const { api } = client(f.impl, "tok");
  await api.register("ana@example.com", "pw");
  await api.login("ana@example.com", "pw");
  await api.me();
  expect(f.calls.map((c) => [c.init.method, c.url.slice(BASE.length)])).toEqual([
    ["POST", "/api/auth/register"],
    ["POST", "/api/auth/login"],
    ["GET", "/api/me"],
  ]);
  expect(f.calls[2].init.body).toBeUndefined();
});

test("focusCurrent and focusNext read the documented paths with a token", async () => {
  const f = fakeFetch(200, { active: false, session: null, reason: "nothing_now" });
  const { api } = client(f.impl, "tok");
  await api.focusCurrent();
  await api.focusNext();
  expect(f.calls.map((c) => [c.init.method, c.url.slice(BASE.length), headersOf(c).Authorization])).toEqual([
    ["GET", "/api/focus/current", "Bearer tok"],
    ["GET", "/api/focus/next", "Bearer tok"],
  ]);
});

test("focusComplete posts the block and progress reads the documented path", async () => {
  const f = fakeFetch(200, { recorded: true });
  const { api } = client(f.impl, "tok");
  await api.focusComplete({ date: "2026-09-13", start: "16:00", end: "18:00" });
  await api.progress();
  expect(f.calls.map((c) => [c.init.method, c.url.slice(BASE.length), headersOf(c).Authorization])).toEqual([
    ["POST", "/api/focus/complete", "Bearer tok"],
    ["GET", "/api/plan/progress", "Bearer tok"],
  ]);
  expect(JSON.parse(f.calls[0].init.body as string)).toEqual({ date: "2026-09-13", start: "16:00", end: "18:00" });
});

test("history reads the documented path with the days query and a token", async () => {
  const f = fakeFetch(200, { days: 30, sessions: [] });
  const { api } = client(f.impl, "tok");
  await api.history(30);
  await api.history();
  expect(f.calls.map((c) => [c.init.method, c.url.slice(BASE.length), headersOf(c).Authorization])).toEqual([
    ["GET", "/api/focus/history?days=30", "Bearer tok"],
    ["GET", "/api/focus/history?days=7", "Bearer tok"],
  ]);
});

test("focusToday reads today's sessions with a token", async () => {
  const today = { date: "2026-09-13", sessions: [], reason: "no_plan" };
  const f = fakeFetch(200, today);
  const { api } = client(f.impl, "tok");
  await expect(api.focusToday()).resolves.toEqual(today);
  expect([f.calls[0].init.method, f.calls[0].url]).toEqual(["GET", `${BASE}/api/focus/today`]);
  expect(headersOf(f.calls[0]).Authorization).toBe("Bearer tok");
});
