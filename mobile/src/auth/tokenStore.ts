/**
 * src/auth/tokenStore.ts
 * Where the session token lives on the phone: expo-secure-store, which
 * is the OS keychain / keystore, never AsyncStorage. Two fixed keys
 * (letters, digits, dot, dash, underscore only, as SecureStore requires):
 * the token, and the email so the app can show who is signed in before
 * the network answers. clear() removes both.
 */

import * as SecureStore from "expo-secure-store";

export const TOKEN_KEY = "studyflow.token";
export const EMAIL_KEY = "studyflow.email";

export interface StoredSession {
  token: string;
  email: string;
}

export interface TokenStore {
  load(): Promise<StoredSession | null>;
  save(token: string, email: string): Promise<void>;
  clear(): Promise<void>;
}

export function createSecureTokenStore(): TokenStore {
  return {
    async load() {
      const token = await SecureStore.getItemAsync(TOKEN_KEY);
      if (!token) return null;
      const email = (await SecureStore.getItemAsync(EMAIL_KEY)) ?? "";
      return { token, email };
    },
    async save(token, email) {
      await SecureStore.setItemAsync(TOKEN_KEY, token);
      await SecureStore.setItemAsync(EMAIL_KEY, email);
    },
    async clear() {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
      await SecureStore.deleteItemAsync(EMAIL_KEY);
    },
  };
}
