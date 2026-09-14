/**
 * src/config.ts
 * Where the StudyFlow API is. One source: EXPO_PUBLIC_API_URL, set in
 * mobile/.env (see .env.example) to the laptop's LAN address, e.g.
 * http://192.168.100.24:8010. Expo inlines EXPO_PUBLIC_* at bundle time,
 * so a change needs `npx expo start -c`. Empty when unset; the API
 * client turns that into a message rather than a bad request.
 */

export function apiBaseUrl(env: Record<string, string | undefined> = process.env): string {
  return (env.EXPO_PUBLIC_API_URL ?? "").trim().replace(/\/+$/, "");
}
