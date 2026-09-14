/**
 * src/app/(app)/_layout.tsx
 * The signed-in screens. M1 has only Home; M2 adds Today, M3 Focus,
 * M4 Progress here. Reachable only while the session is signed in.
 */

import { Stack } from "expo-router";

export default function AppLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
