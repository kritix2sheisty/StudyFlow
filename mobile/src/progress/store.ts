/**
 * src/progress/store.ts
 * The Progress screen's data: /api/plan/progress kept exactly as the
 * server sent it (the engine already computed hours, percentages and
 * risk; the phone only shows them). Same load rules as Today: loading
 * until the first answer, a failed first load is an error, a failed
 * refresh keeps the last answer and carries the message.
 */

import { errorMessage } from "../ui/messages";

export interface ProgressAssignment {
  id: number;
  name: string;
  subject: string;
  due_date: string;
  status: string;
  required_hours: number;
  scheduled_hours: number;
  remaining_hours: number;
  percent: number;
  risk: string;
  done_hours: number;
  done_percent: number;
}

export interface ProgressAnswer {
  fresh: boolean;
  required_hours: number;
  scheduled_hours: number;
  unscheduled_hours: number;
  completion_percentage: number;
  assignments: ProgressAssignment[];
  completed: string[];
  active_count: number;
  completed_count: number;
  done_hours: number;
  sessions_completed: number;
}

export interface ProgressState {
  status: "loading" | "refreshing" | "ready" | "error";
  progress: ProgressAnswer | null;
  message: string | null;
}

export interface ProgressStore {
  getState(): ProgressState;
  subscribe(listener: (state: ProgressState) => void): () => void;
  load(): Promise<void>;
  reset(): void;
}

const INITIAL: ProgressState = { status: "loading", progress: null, message: null };

export function createProgressStore({ api }: { api: { progress(): Promise<ProgressAnswer> } }): ProgressStore {
  let state: ProgressState = INITIAL;
  const listeners = new Set<(state: ProgressState) => void>();

  function set(next: ProgressState) {
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
      if (state.progress) set({ ...state, status: "refreshing" });
      try {
        const progress = await api.progress();
        set({ status: "ready", progress, message: null });
      } catch (e) {
        const message = errorMessage(e);
        if (state.progress) set({ status: "ready", progress: state.progress, message });
        else set({ status: "error", progress: null, message });
      }
    },

    reset() {
      set(INITIAL);
    },
  };
}
