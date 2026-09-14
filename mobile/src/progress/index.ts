/**
 * src/progress/index.ts
 * The one real Progress store on the real API client, reset on
 * sign-out, and the React hook over it.
 */

import { useSyncExternalStore } from "react";

import { api, session } from "../auth";
import { createProgressStore, ProgressState } from "./store";

export const progress = createProgressStore({ api });

session.subscribe((state) => {
  if (state.status === "signed-out") progress.reset();
});

export function useProgress(): ProgressState {
  return useSyncExternalStore(progress.subscribe, progress.getState, progress.getState);
}
