/**
 * src/app/(auth)/_layout.tsx
 * The signed-out screens: sign in and create account. Reachable only
 * while the session is signed out (see the root layout).
 */

import { Stack } from "expo-router";

export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
