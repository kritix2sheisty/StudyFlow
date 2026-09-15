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
 *   next      the first session still to come (after the one on now)
 *   upcoming  any later session
 *
 * The view also exposes now and next directly for the quick-start
 * button, the day's goal (done minutes against planned minutes), and
 * todayTotals(), the same numbers in the shape the motivation
 * sentences take, so Today needs no second fetch for them.
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

export type RowState = "done" | "now" | "past" | "next" | "upcoming";

export interface TodayRow extends TodaySession {
  state: RowState;
}

export interface TodayGoal {
  doneMinutes: number;
  plannedMinutes: number;
  percent: number;
}

export interface TodayView {
  kind: "no_plan" | "plan_stale" | "empty" | "sessions";
  date: string;
  rows: TodayRow[];
  done: number;
  total: number;
  now: TodayRow | null;
  next: TodayRow | null;
  goal: TodayGoal;
}

export function minuteOf(clock: string): number {
  const [h, m] = clock.split(":").map(Number);
  return h * 60 + m;
}

/** "16:00" from the API shown as "4:00", the way students read a timetable. */
export function clock12(clock: string): string {
  const [h, m] = clock.split(":").map(Number);
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${m.toString().padStart(2, "0")}`;
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

const NO_GOAL: TodayGoal = { doneMinutes: 0, plannedMinutes: 0, percent: 0 };

export function buildTodayView(answer: TodayAnswer, minute: number): TodayView {
  if (answer.reason) {
    return { kind: answer.reason, date: answer.date, rows: [], done: 0, total: 0, now: null, next: null, goal: NO_GOAL };
  }
  const rows: TodayRow[] = answer.sessions.map((s) => ({ ...s, state: stateOf(s, minute) }));
  const next = rows.find((r) => r.state === "upcoming") ?? null;
  if (next) next.state = "next";
  const doneRows = rows.filter((r) => r.state === "done");
  const doneMinutes = doneRows.reduce((sum, r) => sum + r.duration_minutes, 0);
  const plannedMinutes = rows.reduce((sum, r) => sum + r.duration_minutes, 0);
  return {
    kind: rows.length ? "sessions" : "empty",
    date: answer.date,
    rows,
    done: doneRows.length,
    total: rows.length,
    now: rows.find((r) => r.state === "now") ?? null,
    next,
    goal: {
      doneMinutes,
      plannedMinutes,
      percent: plannedMinutes ? Math.min(100, Math.round((100 * doneMinutes) / plannedMinutes)) : 0,
    },
  };
}

/** Today's numbers in the shape history's todayLines() takes. */
export function todayTotals(view: TodayView): { minutes: number; sessions: number; planned_minutes: number; planned_sessions: number } {
  return { minutes: view.goal.doneMinutes, sessions: view.done, planned_minutes: view.goal.plannedMinutes, planned_sessions: view.total };
}
