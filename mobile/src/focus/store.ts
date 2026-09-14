/**
 * src/focus/store.ts
 * What the Focus screen needs from the server: the session on now and
 * the one after it, read together from /api/focus/current and
 * /api/focus/next, with the API's reasons (no_plan, plan_stale,
 * nothing_now, nothing_next) when there is none. The countdown is not
 * here; see timer.ts. A failed refresh keeps what was known and carries
 * the message; reset() goes back to loading for a new sign-in.
 */

import type { TodaySession } from "../today/view";
import { errorMessage } from "../ui/messages";

export type CurrentReason = null | "no_plan" | "plan_stale" | "nothing_now";
export type NextReason = null | "no_plan" | "plan_stale" | "nothing_next";

export interface CurrentSession extends TodaySession {
  remaining_minutes?: number;
}

export interface CurrentAnswer {
  active: boolean;
  session: CurrentSession | null;
  reason: CurrentReason;
}

export interface NextAnswer {
  session: TodaySession | null;
  reason: NextReason;
}

export interface FocusState {
  status: "loading" | "refreshing" | "ready" | "error";
  current: CurrentSession | null;
  currentReason: CurrentReason;
  next: TodaySession | null;
  nextReason: NextReason;
  message: string | null;
}

export interface FocusStore {
  getState(): FocusState;
  subscribe(listener: (state: FocusState) => void): () => void;
  load(): Promise<void>;
  reset(): void;
}

const INITIAL: FocusState = { status: "loading", current: null, currentReason: null, next: null, nextReason: null, message: null };

export function createFocusStore({ api }: {
  api: { focusCurrent(): Promise<CurrentAnswer>; focusNext(): Promise<NextAnswer> };
}): FocusStore {
  let state: FocusState = INITIAL;
  const listeners = new Set<(state: FocusState) => void>();

  function set(next: FocusState) {
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
      const known = state.status === "ready" || state.status === "refreshing";
      if (known) set({ ...state, status: "refreshing" });
      try {
        const [current, next] = await Promise.all([api.focusCurrent(), api.focusNext()]);
        set({
          status: "ready",
          current: current.session,
          currentReason: current.reason,
          next: next.session,
          nextReason: next.reason,
          message: null,
        });
      } catch (e) {
        const message = errorMessage(e);
        if (known) set({ ...state, status: "ready", message });
        else set({ ...INITIAL, status: "error", message });
      }
    },

    reset() {
      set(INITIAL);
    },
  };
}
