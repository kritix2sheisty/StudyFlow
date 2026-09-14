/**
 * src/app/_layout.tsx
 * The root of the app. Holds the native splash screen until the session
 * has been read from the phone, so a signed-in student never sees the
 * sign-in screen flash past. Then one of two groups is reachable:
 * (app) when signed in, (auth) when not. expo-router's Protected
 * redirects between them on its own whenever the session changes.
 */

import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";

import { session } from "../auth";
import { useSession } from "../auth/useSession";

SplashScreen.preventAutoHideAsync().catch(() => {
  // already hidden or not available: nothing to hold
});

export default function RootLayout() {
  const { status } = useSession();

  useEffect(() => {
    void session.restore();
  }, []);

  useEffect(() => {
    if (status !== "loading") SplashScreen.hideAsync().catch(() => {});
  }, [status]);

  if (status === "loading") return null;

  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Protected guard={status === "signed-in"}>
        <Stack.Screen name="(app)" />
      </Stack.Protected>
      <Stack.Protected guard={status === "signed-out"}>
        <Stack.Screen name="(auth)" />
      </Stack.Protected>
    </Stack>
  );
}
