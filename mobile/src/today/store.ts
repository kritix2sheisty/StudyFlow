/**
 * src/today/store.ts
 * The Today screen's data: one load of /api/focus/today turned into a
 * TodayView against the current minute. Rules:
 * - loading until the first answer; refreshing while a later load runs
 * - a failed first load is an error with the message to show
 * - a failed refresh keeps the last good view and carries the message
 * - a good load clears any old message
 * - reset() goes back to loading, for a new sign-in
 * The API and the clock are injected so tests stay off the network.
 */

import { errorMessage } from "../ui/messages";
import { buildTodayView, nowMinute as wallClockMinute, TodayAnswer, TodayView } from "./view";

export interface TodayState {
  status: "loading" | "refreshing" | "ready" | "error";
  view: TodayView | null;
  message: string | null;
}

export interface TodayStore {
  getState(): TodayState;
  subscribe(listener: (state: TodayState) => void): () => void;
  load(): Promise<void>;
  reset(): void;
}

const INITIAL: TodayState = { status: "loading", view: null, message: null };

export function createTodayStore({ api, nowMinute = wallClockMinute }: {
  api: { focusToday(): Promise<TodayAnswer> };
  nowMinute?: () => number;
}): TodayStore {
  let state: TodayState = INITIAL;
  const listeners = new Set<(state: TodayState) => void>();

  function set(next: TodayState) {
    state = next;
    listeners.forEach((fn) => fn(state));
  }

  return {
    getState: () => state,

    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    async load() {
      if (state.view) set({ ...state, status: "refreshing" });
      try {
        const answer = await api.focusToday();
        set({ status: "ready", view: buildTodayView(answer, nowMinute()), message: null });
      } catch (e) {
        const message = errorMessage(e);
        if (state.view) set({ status: "ready", view: state.view, message });
        else set({ status: "error", view: null, message });
      }
    },

    reset() {
      set(INITIAL);
    },
  };
}
