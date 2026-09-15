/**
 * tests/history_view.test.ts
 * Turning /api/focus/history into what History and Progress show:
 * minutes as students read them, sessions grouped by day newest first,
 * the week's numbers, and the two motivation lines the mentor asked
 * for. Pure functions over the API answer.
 */

import {
  formatMinutes, groupByDay, weekSummary, todayLines, HistoryAnswer,
} from "../src/history/view";

const S = (id: number, subject: string, assignment: string, date: string, start: string, end: string, minutes: number) =>
  ({ id, assignment_id: id, assignment, subject, date, start, end, minutes, completed_at: `${date}T18:00:00` });

const ANSWER: HistoryAnswer = {
  days: 7, from: "2026-09-08", to: "2026-09-14",
  sessions: [
    S(4, "Physics", "Lab report", "2026-09-14", "16:00", "17:00", 60),
    S(3, "Mathematics", "Math IA", "2026-09-14", "09:00", "09:45", 45),
    S(2, "Physics", "Lab report", "2026-09-13", "16:00", "16:30", 30),
    S(1, "Mathematics", "Math IA", "2026-09-12", "16:00", "17:00", 60),
  ],
  minutes: 195, sessions_count: 4,
  by_day: [
    { date: "2026-09-08", minutes: 0, sessions: 0 }, { date: "2026-09-09", minutes: 0, sessions: 0 },
    { date: "2026-09-10", minutes: 0, sessions: 0 }, { date: "2026-09-11", minutes: 0, sessions: 0 },
    { date: "2026-09-12", minutes: 60, sessions: 1 }, { date: "2026-09-13", minutes: 30, sessions: 1 },
    { date: "2026-09-14", minutes: 105, sessions: 2 },
  ],
  by_subject: [{ subject: "Mathematics", minutes: 105, sessions: 2 }, { subject: "Physics", minutes: 90, sessions: 2 }],
  streak_days: 3,
  today: { minutes: 105, sessions: 2, planned_minutes: 180, planned_sessions: 3 },
};

test("formatMinutes reads like a student would say it", () => {
  expect(formatMinutes(0)).toBe("0 min");
  expect(formatMinutes(45)).toBe("45 min");
  expect(formatMinutes(60)).toBe("1h");
  expect(formatMinutes(135)).toBe("2h 15m");
  expect(formatMinutes(195)).toBe("3h 15m");
});

test("groupByDay keeps newest day first and labels today and yesterday", () => {
  const groups = groupByDay(ANSWER.sessions, "2026-09-14");
  expect(groups.map((g) => [g.date, g.label, g.minutes, g.sessions.length])).toEqual([
    ["2026-09-14", "Today", 105, 2],
    ["2026-09-13", "Yesterday", 30, 1],
    ["2026-09-12", "Saturday 12 September", 60, 1],
  ]);
  expect(groups[0].sessions.map((s) => `${s.subject} — ${formatMinutes(s.minutes)}`)).toEqual([
    "Physics — 1h", "Mathematics — 45 min",
  ]);
});

test("weekSummary gives the Progress dashboard its numbers", () => {
  expect(weekSummary(ANSWER)).toEqual({
    minutes: 195, sessions: 4, streak: 3, subjects: 2,
    activeDays: 3, daysInWindow: 7,
    today: { done: 105, planned: 180, sessionsDone: 2, sessionsPlanned: 3, percent: 58 },
  });
});

test("today's percent is capped at 100 and is 0 with nothing planned", () => {
  const over = weekSummary({ ...ANSWER, today: { minutes: 200, sessions: 3, planned_minutes: 180, planned_sessions: 3 } });
  expect(over.today.percent).toBe(100);
  const none = weekSummary({ ...ANSWER, today: { minutes: 30, sessions: 1, planned_minutes: 0, planned_sessions: 0 } });
  expect(none.today.percent).toBe(0);
});

test("todayLines are the mentor's two sentences, in the right cases", () => {
  expect(todayLines({ minutes: 135, sessions: 3, planned_minutes: 180, planned_sessions: 4 })).toEqual([
    "3 sessions completed today 🎉",
    "You completed 2h 15m of planned study.",
  ]);
  expect(todayLines({ minutes: 45, sessions: 1, planned_minutes: 180, planned_sessions: 4 })).toEqual([
    "1 session completed today",
    "You completed 45 min of planned study.",
  ]);
  expect(todayLines({ minutes: 180, sessions: 4, planned_minutes: 180, planned_sessions: 4 })).toEqual([
    "4 sessions completed today 🎉",
    "You completed all 3h of planned study. Done for today.",
  ]);
  expect(todayLines({ minutes: 0, sessions: 0, planned_minutes: 180, planned_sessions: 4 })).toEqual([]);
  expect(todayLines({ minutes: 60, sessions: 1, planned_minutes: 0, planned_sessions: 0 })).toEqual([
    "1 session completed today",
    "You completed 1h of study.",
  ]);
});
