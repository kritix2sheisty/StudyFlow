/**
 * src/history/index.ts
 * The one real History store on the real API client, reset on
 * sign-out, and the React hook over it. Progress reads it too for the
 * week's numbers, so one load serves both screens.
 */

import { useSyncExternalStore } from "react";

import { api, session } from "../auth";
import { createHistoryStore, HistoryState } from "./store";

export const history = createHistoryStore({ api });

session.subscribe((state) => {
  if (state.status === "signed-out") history.reset();
});

export function useHistory(): HistoryState {
  return useSyncExternalStore(history.subscribe, history.getState, history.getState);
}
