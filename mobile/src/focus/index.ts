/**
 * src/focus/index.ts
 * The one real Focus store on the real API client, reset on sign-out,
 * plus two hooks: useFocus for the store, and useNow, which re-renders
 * the screen every few hundred milliseconds and on return to the front
 * so the countdown can be read from the wall clock. The interval only
 * triggers a render; the time itself always comes from Date.now().
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { AppState } from "react-native";

import { api, session } from "../auth";
import { createFocusStore, FocusState } from "./store";

export const focus = createFocusStore({ api });

session.subscribe((state) => {
  if (state.status === "signed-out") focus.reset();
});

export function useFocus(): FocusState {
  return useSyncExternalStore(focus.subscribe, focus.getState, focus.getState);
}

export function useNow(active: boolean, everyMs = 250): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const tick = () => setNow(Date.now());
    tick();
    const interval = setInterval(tick, everyMs);
    const sub = AppState.addEventListener("change", (s) => {
      if (s === "active") tick();
    });
    return () => {
      clearInterval(interval);
      sub.remove();
    };
  }, [active, everyMs]);
  return now;
}
