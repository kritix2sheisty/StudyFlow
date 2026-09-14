/**
 * tests/token_store.test.ts
 * The token lives in the phone's secure storage under fixed keys, and
 * clear() removes both the token and the email. expo-secure-store is
 * mocked with an in-memory map.
 */

jest.mock("expo-secure-store", () => {
  const store = new Map<string, string>();
  return {
    __store: store,
    getItemAsync: jest.fn(async (key: string) => store.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => { store.set(key, value); }),
    deleteItemAsync: jest.fn(async (key: string) => { store.delete(key); }),
  };
});

import * as SecureStore from "expo-secure-store";
import { createSecureTokenStore, EMAIL_KEY, TOKEN_KEY } from "../src/auth/tokenStore";

const store = (SecureStore as unknown as { __store: Map<string, string> }).__store;

beforeEach(() => store.clear());

test("load is null until something is saved", async () => {
  expect(await createSecureTokenStore().load()).toBeNull();
});

test("save keeps the token and email under the fixed keys", async () => {
  const tokens = createSecureTokenStore();
  await tokens.save("tok-1", "ana@example.com");
  expect(store.get(TOKEN_KEY)).toBe("tok-1");
  expect(store.get(EMAIL_KEY)).toBe("ana@example.com");
  expect(await tokens.load()).toEqual({ token: "tok-1", email: "ana@example.com" });
  expect(TOKEN_KEY).toMatch(/^[A-Za-z0-9._-]+$/);
  expect(EMAIL_KEY).toMatch(/^[A-Za-z0-9._-]+$/);
});

test("clear removes both, and a token without an email still restores", async () => {
  const tokens = createSecureTokenStore();
  await tokens.save("tok-1", "ana@example.com");
  await tokens.clear();
  expect(store.size).toBe(0);
  expect(await tokens.load()).toBeNull();
  store.set(TOKEN_KEY, "tok-2");
  expect(await tokens.load()).toEqual({ token: "tok-2", email: "" });
});
