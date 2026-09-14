/**
 * src/today/view.ts
 * What the Today screen shows, computed from the API's /api/focus/today
 * answer and the minute of the day. Pure and clock-free: callers pass
 * the minute, so a screen can recompute when the app comes back to the
 * front. Per session:
 *
 *   done      recorded as completed (wins over the clock)
 *   now       start <= minute < end
 *   past      ended and not recorded
 *   upcoming  starts later today
 *
 * The kind says which screen to draw: no_plan and plan_stale point the
 * student to the laptop, empty means a fresh plan with nothing today.
 */

export type TodayReason = null | "no_plan" | "plan_stale";

export interface TodaySession {
  assignment_id: number | null;
  assignment: string;
  subject: string;
  date: string;
  start: string;
  end: string;
  duration_minutes: number;
  completed: boolean;
}

export interface TodayAnswer {
  date: string;
  sessions: TodaySession[];
  reason: TodayReason;
}

export type RowState = "done" | "now" | "past" | "upcoming";

export interface TodayRow extends TodaySession {
  state: RowState;
}

export interface TodayView {
  kind: "no_plan" | "plan_stale" | "empty" | "sessions";
  date: string;
  rows: TodayRow[];
  done: number;
  total: number;
}

export function minuteOf(clock: string): number {
  const [h, m] = clock.split(":").map(Number);
  return h * 60 + m;
}

/** Minutes since midnight on the phone's wall clock. Never counted, always read. */
export function nowMinute(now: Date = new Date()): number {
  return now.getHours() * 60 + now.getMinutes();
}

function stateOf(s: TodaySession, minute: number): RowState {
  if (s.completed) return "done";
  const start = minuteOf(s.start);
  const end = minuteOf(s.end);
  if (minute >= start && minute < end) return "now";
  if (minute >= end) return "past";
  return "upcoming";
}

export function buildTodayView(answer: TodayAnswer, minute: number): TodayView {
  if (answer.reason) return { kind: answer.reason, date: answer.date, rows: [], done: 0, total: 0 };
  const rows = answer.sessions.map((s) => ({ ...s, state: stateOf(s, minute) }));
  return {
    kind: rows.length ? "sessions" : "empty",
    date: answer.date,
    rows,
    done: rows.filter((r) => r.state === "done").length,
    total: rows.length,
  };
}
