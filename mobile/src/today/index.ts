/**
 * src/today/index.ts
 * The one real Today store, on the real API client, plus the React hook
 * over it. Reset when the session signs out so the next student starts
 * from loading, not from someone else's day.
 */

import { useSyncExternalStore } from "react";

import { api, session } from "../auth";
import { createTodayStore, TodayState } from "./store";

export const today = createTodayStore({ api });

session.subscribe((state) => {
  if (state.status === "signed-out") today.reset();
});

export function useToday(): TodayState {
  return useSyncExternalStore(today.subscribe, today.getState, today.getState);
}
