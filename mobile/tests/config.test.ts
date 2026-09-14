/**
 * tests/config.test.ts
 * The API address comes from EXPO_PUBLIC_API_URL and nothing else.
 */

import { apiBaseUrl } from "../src/config";

test("apiBaseUrl strips whitespace and a trailing slash", () => {
  expect(apiBaseUrl({ EXPO_PUBLIC_API_URL: "  http://192.168.100.24:8010/ " })).toBe("http://192.168.100.24:8010");
  expect(apiBaseUrl({ EXPO_PUBLIC_API_URL: "http://192.168.100.24:8010" })).toBe("http://192.168.100.24:8010");
});

test("apiBaseUrl is empty when EXPO_PUBLIC_API_URL is unset or blank", () => {
  expect(apiBaseUrl({})).toBe("");
  expect(apiBaseUrl({ EXPO_PUBLIC_API_URL: "   " })).toBe("");
});
