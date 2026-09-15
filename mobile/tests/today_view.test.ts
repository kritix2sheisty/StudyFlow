/**
 * tests/today_view.test.ts
 * Turning the API's /api/focus/today answer into what the Today screen
 * shows: which kind of day it is (no plan, stale plan, nothing today, or
 * sessions) and, per session, whether it is done, on now, already past,
 * or still to come. Pure: the clock is a minute of the day passed in.
 */

import { buildTodayView, minuteOf, nowMinute, TodayAnswer } from "../src/today/view";

const session = (start: string, end: string, completed = false, assignment = "Math") => ({
  assignment_id: 1, assignment, subject: "Mathematics", date: "2026-09-13", start, end,
  duration_minutes: minuteOf(end) - minuteOf(start), completed,
});

const day = (sessions: ReturnType<typeof session>[], reason: TodayAnswer["reason"] = null): TodayAnswer =>
  ({ date: "2026-09-13", sessions, reason });

test("minuteOf turns HH:MM into minutes of the day", () => {
  expect(minuteOf("00:00")).toBe(0);
  expect(minuteOf("16:30")).toBe(990);
  expect(minuteOf("23:59")).toBe(1439);
});

test("nowMinute reads the wall clock, not a counter", () => {
  expect(nowMinute(new Date(2026, 8, 13, 16, 47))).toBe(16 * 60 + 47);
});

test("no plan and a stale plan are their own kinds with nothing to list", () => {
  expect(buildTodayView(day([], "no_plan"), 600)).toEqual({ kind: "no_plan", date: "2026-09-13", rows: [], done: 0, total: 0 });
  expect(buildTodayView(day([], "plan_stale"), 600).kind).toBe("plan_stale");
});

test("a fresh plan with nothing today is empty", () => {
  expect(buildTodayView(day([]), 600)).toEqual({ kind: "empty", date: "2026-09-13", rows: [], done: 0, total: 0 });
});

test("each session is done, now, past or upcoming by the clock", () => {
  const view = buildTodayView(day([
    session("09:00", "10:00", true),            // done
    session("11:00", "12:00"),                  // past, not done
    session("16:00", "18:00", false, "CS"),     // on now
    session("19:00", "20:00", false, "Bio"),    // upcoming
  ]), 16 * 60 + 47);
  expect(view.kind).toBe("sessions");
  expect(view.rows.map((r) => [r.assignment, r.state])).toEqual([
    ["Math", "done"], ["Math", "past"], ["CS", "now"], ["Bio", "upcoming"],
  ]);
  expect(view.done).toBe(1);
  expect(view.total).toBe(4);
});

test("a completed session is done even while it is on now", () => {
  const view = buildTodayView(day([session("16:00", "18:00", true)]), 17 * 60);
  expect(view.rows[0].state).toBe("done");
  expect(view.done).toBe(1);
});

test("the end minute is not inside the session", () => {
  const rows = (m: number) => buildTodayView(day([session("16:00", "18:00")]), m).rows[0].state;
  expect(rows(16 * 60 - 1)).toBe("upcoming");
  expect(rows(16 * 60)).toBe("now");
  expect(rows(18 * 60 - 1)).toBe("now");
  expect(rows(18 * 60)).toBe("past");
});

test("rows keep the session fields the Focus screen will need", () => {
  const view = buildTodayView(day([session("16:00", "18:00")]), 600);
  expect(view.rows[0]).toMatchObject({
    assignment_id: 1, assignment: "Math", subject: "Mathematics", date: "2026-09-13",
    start: "16:00", end: "18:00", duration_minutes: 120, completed: false, state: "upcoming",
  });
});

test("clock12 shows the API's 24-hour times the way students read them", () => {
  const { clock12 } = require("../src/today/view");
  expect(clock12("16:00")).toBe("4:00");
  expect(clock12("09:30")).toBe("9:30");
  expect(clock12("12:00")).toBe("12:00");
  expect(clock12("00:15")).toBe("12:15");
  expect(clock12("23:59")).toBe("11:59");
});

test("the first upcoming session is marked next, the rest stay upcoming", () => {
  const { buildTodayView: build } = require("../src/today/view");
  const view = build(day([
    session("09:00", "10:00", true),
    session("16:00", "18:00", false, "CS"),
    session("19:00", "20:00", false, "Bio"),
    session("20:30", "21:00", false, "French"),
  ]), 12 * 60);
  expect(view.rows.map((r) => [r.assignment, r.state])).toEqual([
    ["Math", "done"], ["CS", "next"], ["Bio", "upcoming"], ["French", "upcoming"],
  ]);
  expect(view.next?.assignment).toBe("CS");
  expect(view.now).toBeNull();
});

test("now and next are exposed together, and next skips done sessions", () => {
  const { buildTodayView: build } = require("../src/today/view");
  const view = build(day([
    session("16:00", "18:00", false, "CS"),
    session("19:00", "20:00", true, "Bio"),
    session("20:30", "21:00", false, "French"),
  ]), 17 * 60);
  expect(view.now?.assignment).toBe("CS");
  expect(view.next?.assignment).toBe("French");
  expect(view.rows.map((r) => r.state)).toEqual(["now", "done", "next"]);
});

test("the day's goal is done minutes against all planned minutes", () => {
  const { buildTodayView: build } = require("../src/today/view");
  const view = build(day([
    session("09:00", "10:00", true),              // 60 done
    session("16:00", "18:00", false, "CS"),       // 120
    session("19:00", "20:00", false, "Bio"),      // 60
  ]), 12 * 60);
  expect(view.goal).toEqual({ doneMinutes: 60, plannedMinutes: 240, percent: 25 });
  expect(build(day([]), 600).goal).toEqual({ doneMinutes: 0, plannedMinutes: 0, percent: 0 });
});

test("todayTotals feeds the motivation sentences from the rows alone", () => {
  const { buildTodayView: build, todayTotals } = require("../src/today/view");
  const { todayLines } = require("../src/history/view");
  const view = build(day([
    session("09:00", "10:00", true),
    session("10:15", "11:00", true, "CS"),
    session("16:00", "18:00", false, "Bio"),
  ]), 12 * 60);
  expect(todayTotals(view)).toEqual({ minutes: 105, sessions: 2, planned_minutes: 225, planned_sessions: 3 });
  expect(todayLines(todayTotals(view))).toEqual(["2 sessions completed today 🎉", "You completed 1h 45m of planned study."]);
});
