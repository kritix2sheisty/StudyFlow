/**
 * src/auth/index.ts
 * The one real session for the app: the API client pointed at
 * EXPO_PUBLIC_API_URL, the phone's secure token store, and the session
 * store wired so that any 401 on an authenticated call signs out.
 * Screens import `session` and `api` from here; tests build their own
 * with fakes.
 */

import { createApiClient } from "../api/client";
import { apiBaseUrl } from "../config";
import { createSession } from "./session";
import { createSecureTokenStore } from "./tokenStore";

export const baseUrl = apiBaseUrl();

const tokens = createSecureTokenStore();

export const api = createApiClient({
  baseUrl,
  getToken: () => session.getState().token,
  onUnauthorized: () => {
    void session.handleUnauthorized();
  },
});

export const session = createSession({ api, tokens });
