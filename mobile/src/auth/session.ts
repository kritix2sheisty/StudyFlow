/**
 * src/auth/session.ts
 * Who is signed in on this phone. A small store with one state:
 *
 *   loading     the app just started and has not read the phone yet
 *   signed-out  show the sign-in screens
 *   signed-in   show the app; token and email are known
 *
 * Rules:
 * - restore() reads the saved token and, if there is one, is signed in
 *   at once with the saved email (no sign-in flash), then asks /api/me
 *   in the background. A 401 there means the session is gone: clear and
 *   sign out. A network error changes nothing: the student stays in.
 * - signIn() saves the token and email before anything else can fail.
 * - register() creates the account, then signs in with the same details.
 * - signOut() tells the server if it can, and always clears the phone.
 * - handleUnauthorized() is what the API client calls on any 401 that
 *   carried a token: clear and sign out.
 * Errors from signIn/register are rethrown untouched so screens can show
 * the API's own words. Pure: the API and the token store are injected.
 */

import { ApiError, User } from "../api/client";
import type { TokenStore } from "./tokenStore";

export type SessionStatus = "loading" | "signed-out" | "signed-in";

export interface SessionState {
  status: SessionStatus;
  email: string | null;
  user: User | null;
  token: string | null;
}

export interface SessionApi {
  register(email: string, password: string): Promise<unknown>;
  login(email: string, password: string): Promise<{ token: string }>;
  logout(): Promise<unknown>;
  me(): Promise<User>;
}

export interface Session {
  getState(): SessionState;
  subscribe(listener: (state: SessionState) => void): () => void;
  restore(): Promise<void>;
  signIn(email: string, password: string): Promise<void>;
  register(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
  handleUnauthorized(): Promise<void>;
}

const SIGNED_OUT: SessionState = { status: "signed-out", email: null, user: null, token: null };

export function createSession({ api, tokens }: { api: SessionApi; tokens: TokenStore }): Session {
  let state: SessionState = { status: "loading", email: null, user: null, token: null };
  const listeners = new Set<(state: SessionState) => void>();

  function set(next: SessionState) {
    state = next;
    listeners.forEach((fn) => fn(state));
  }

  async function clearAndSignOut() {
    await tokens.clear();
    set(SIGNED_OUT);
  }

  /** Ask the server who this token belongs to. Gone → sign out; unreachable → keep going. */
  async function refreshUser(token: string) {
    try {
      const user = await api.me();
      if (state.token === token) set({ ...state, user, email: user.email });
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) await clearAndSignOut();
    }
  }

  return {
    getState: () => state,

    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    async restore() {
      const saved = await tokens.load();
      if (!saved) {
        set(SIGNED_OUT);
        return;
      }
      set({ status: "signed-in", email: saved.email, user: null, token: saved.token });
      await refreshUser(saved.token);
    },

    async signIn(email, password) {
      const { token } = await api.login(email, password);
      await tokens.save(token, email);
      set({ status: "signed-in", email, user: null, token });
      await refreshUser(token);
    },

    async register(email, password) {
      await api.register(email, password);
      await this.signIn(email, password);
    },

    async signOut() {
      try {
        await api.logout();
      } catch {
        // the phone is signed out either way
      }
      await clearAndSignOut();
    },

    handleUnauthorized: clearAndSignOut,
  };
}
