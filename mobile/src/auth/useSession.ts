/**
 * src/auth/useSession.ts
 * React's view of the session store: re-renders on every state change,
 * with no state library. Layouts read status to pick the screen group;
 * Home reads the email.
 */

import { useSyncExternalStore } from "react";

import { session } from "./index";
import type { SessionState } from "./session";

export function useSession(): SessionState {
  return useSyncExternalStore(session.subscribe, session.getState, session.getState);
}
