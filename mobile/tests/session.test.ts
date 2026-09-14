/**
 * tests/session.test.ts
 * The session store: who is signed in on this phone. It talks to a fake
 * API and a fake token store, so these tests pin the rules, not the
 * network: restore without a flash, sign in saves the token, any 401 or
 * a sign-out clears it, a network error never signs anyone out.
 */

import { ApiError, NetworkError } from "../src/api/client";
import { createSession, SessionState } from "../src/auth/session";
import type { TokenStore } from "../src/auth/tokenStore";

const ANA = { id: "u1", email: "ana@example.com", created_at: "2026-09-13T00:00:00" };
const LOGIN = { token: "tok-1", expires_at: "2026-10-13T00:00:00" };

function memoryTokens(initial: { token: string; email: string } | null = null): TokenStore & { saved: () => typeof initial } {
  let stored = initial;
  return {
    load: jest.fn(async () => stored),
    save: jest.fn(async (token: string, email: string) => { stored = { token, email }; }),
    clear: jest.fn(async () => { stored = null; }),
    saved: () => stored,
  };
}

function fakeApi(overrides: Partial<Record<"register" | "login" | "logout" | "me", jest.Mock>> = {}) {
  return {
    register: jest.fn(async () => ({ id: ANA.id, email: ANA.email })),
    login: jest.fn(async () => LOGIN),
    logout: jest.fn(async () => undefined),
    me: jest.fn(async () => ANA),
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function statuses(session: { subscribe: (fn: (s: SessionState) => void) => () => void }) {
  const seen: string[] = [];
  session.subscribe((s) => seen.push(s.status));
  return seen;
}

test("starts loading and becomes signed-out when no token is stored", async () => {
  const session = createSession({ api: fakeApi(), tokens: memoryTokens() });
  expect(session.getState().status).toBe("loading");
  await session.restore();
  expect(session.getState()).toEqual({ status: "signed-out", email: null, user: null, token: null });
});

test("restore with a stored token is signed in before me() resolves", async () => {
  const me = deferred<typeof ANA>();
  const api = fakeApi({ me: jest.fn(() => me.promise) });
  const session = createSession({ api, tokens: memoryTokens({ token: "tok-0", email: "ana@example.com" }) });
  const seen = statuses(session);
  const restoring = session.restore();
  await Promise.resolve();
  await Promise.resolve();
  expect(seen).toContain("signed-in");
  expect(session.getState().email).toBe("ana@example.com");
  expect(session.getState().token).toBe("tok-0");
  me.resolve(ANA);
  await restoring;
});

test("restore fetches me and stores the user", async () => {
  const api = fakeApi();
  const session = createSession({ api, tokens: memoryTokens({ token: "tok-0", email: "ana@example.com" }) });
  await session.restore();
  expect(api.me).toHaveBeenCalledTimes(1);
  expect(session.getState()).toEqual({ status: "signed-in", email: ANA.email, user: ANA, token: "tok-0" });
});

test("restore clears the token and signs out when me() answers 401", async () => {
  const api = fakeApi({ me: jest.fn(async () => { throw new ApiError(401, "Your session has expired. Sign in again."); }) });
  const tokens = memoryTokens({ token: "tok-old", email: "ana@example.com" });
  const session = createSession({ api, tokens });
  await session.restore();
  expect(session.getState().status).toBe("signed-out");
  expect(tokens.saved()).toBeNull();
});

test("restore keeps the session when me() fails with a network error", async () => {
  const api = fakeApi({ me: jest.fn(async () => { throw new NetworkError("Can't reach StudyFlow"); }) });
  const tokens = memoryTokens({ token: "tok-0", email: "ana@example.com" });
  const session = createSession({ api, tokens });
  await session.restore();
  expect(session.getState().status).toBe("signed-in");
  expect(session.getState().email).toBe("ana@example.com");
  expect(tokens.saved()).toEqual({ token: "tok-0", email: "ana@example.com" });
});

test("signIn saves the token and email to the token store", async () => {
  const tokens = memoryTokens();
  const session = createSession({ api: fakeApi(), tokens });
  await session.restore();
  await session.signIn("ana@example.com", "a long enough password");
  expect(tokens.saved()).toEqual({ token: "tok-1", email: "ana@example.com" });
  expect(session.getState().status).toBe("signed-in");
  expect(session.getState().token).toBe("tok-1");
});

test("signIn fetches me after login", async () => {
  const api = fakeApi();
  const session = createSession({ api, tokens: memoryTokens() });
  await session.restore();
  await session.signIn("ana@example.com", "a long enough password");
  expect(api.login).toHaveBeenCalledWith("ana@example.com", "a long enough password");
  expect(api.me).toHaveBeenCalledTimes(1);
  expect(session.getState().user).toEqual(ANA);
});

test("signIn with a wrong password rethrows the ApiError and stores nothing", async () => {
  const api = fakeApi({ login: jest.fn(async () => { throw new ApiError(401, "Email or password is incorrect."); }) });
  const tokens = memoryTokens();
  const session = createSession({ api, tokens });
  await session.restore();
  await expect(session.signIn("ana@example.com", "wrong")).rejects.toMatchObject({ status: 401, message: "Email or password is incorrect." });
  expect(tokens.saved()).toBeNull();
  expect(session.getState().status).toBe("signed-out");
});

test("register then signs in with the same credentials", async () => {
  const api = fakeApi();
  const tokens = memoryTokens();
  const session = createSession({ api, tokens });
  await session.restore();
  await session.register("ana@example.com", "a long enough password");
  expect(api.register).toHaveBeenCalledWith("ana@example.com", "a long enough password");
  expect(api.login).toHaveBeenCalledWith("ana@example.com", "a long enough password");
  expect(session.getState().status).toBe("signed-in");
  expect(tokens.saved()?.token).toBe("tok-1");
});

test("register with a taken email rethrows and stays signed out", async () => {
  const api = fakeApi({ register: jest.fn(async () => { throw new ApiError(409, "That email is already registered."); }) });
  const session = createSession({ api, tokens: memoryTokens() });
  await session.restore();
  await expect(session.register("ana@example.com", "a long enough password")).rejects.toMatchObject({ status: 409 });
  expect(api.login).not.toHaveBeenCalled();
  expect(session.getState().status).toBe("signed-out");
});

test("signOut calls logout, clears the store and signs out", async () => {
  const api = fakeApi();
  const tokens = memoryTokens({ token: "tok-0", email: "ana@example.com" });
  const session = createSession({ api, tokens });
  await session.restore();
  await session.signOut();
  expect(api.logout).toHaveBeenCalledTimes(1);
  expect(tokens.saved()).toBeNull();
  expect(session.getState()).toEqual({ status: "signed-out", email: null, user: null, token: null });
});

test("signOut still clears the store when logout fails", async () => {
  const api = fakeApi({ logout: jest.fn(async () => { throw new NetworkError("Can't reach StudyFlow"); }) });
  const tokens = memoryTokens({ token: "tok-0", email: "ana@example.com" });
  const session = createSession({ api, tokens });
  await session.restore();
  await expect(session.signOut()).resolves.toBeUndefined();
  expect(tokens.saved()).toBeNull();
  expect(session.getState().status).toBe("signed-out");
});

test("handleUnauthorized clears the store and signs out", async () => {
  const tokens = memoryTokens({ token: "tok-0", email: "ana@example.com" });
  const session = createSession({ api: fakeApi(), tokens });
  await session.restore();
  await session.handleUnauthorized();
  expect(tokens.saved()).toBeNull();
  expect(session.getState().status).toBe("signed-out");
});

test("subscribers are notified on every state change and can unsubscribe", async () => {
  const session = createSession({ api: fakeApi(), tokens: memoryTokens() });
  const seen: SessionState[] = [];
  const stop = session.subscribe((s) => seen.push(s));
  await session.restore();
  await session.signIn("ana@example.com", "a long enough password");
  expect(seen.map((s) => s.status)).toEqual(["signed-out", "signed-in", "signed-in"]);
  stop();
  await session.signOut();
  expect(seen).toHaveLength(3);
});
