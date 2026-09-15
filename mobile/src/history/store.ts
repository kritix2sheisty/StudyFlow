/**
 * src/history/store.ts
 * The History screen's data (and the Progress dashboard's week numbers):
 * one load of /api/focus/history for a number of days, kept as sent.
 * Same load rules as Today and Progress: loading until the first
 * answer, a failed first load is an error, a failed refresh keeps the
 * last answer and carries the message, reset() for a new sign-in.
 */

import { errorMessage } from "../ui/messages";
import type { HistoryAnswer } from "./view";

export const DEFAULT_DAYS = 7;

export interface HistoryState {
  status: "loading" | "refreshing" | "ready" | "error";
  history: HistoryAnswer | null;
  message: string | null;
}

export interface HistoryStore {
  getState(): HistoryState;
  subscribe(listener: (state: HistoryState) => void): () => void;
  load(days?: number): Promise<void>;
  reset(): void;
}

const INITIAL: HistoryState = { status: "loading", history: null, message: null };

export function createHistoryStore({ api }: { api: { history(days?: number): Promise<HistoryAnswer> } }): HistoryStore {
  let state: HistoryState = INITIAL;
  const listeners = new Set<(state: HistoryState) => void>();

  function set(next: HistoryState) {
    state = next;
    listeners.forEach((fn) => fn(state));
  }

  return {
    getState: () => state,

    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    async load(days = DEFAULT_DAYS) {
      if (state.history) set({ ...state, status: "refreshing" });
      try {
        const history = await api.history(days);
        set({ status: "ready", history, message: null });
      } catch (e) {
        const message = errorMessage(e);
        if (state.history) set({ status: "ready", history: state.history, message });
        else set({ status: "error", history: null, message });
      }
    },

    reset() {
      set(INITIAL);
    },
  };
}
