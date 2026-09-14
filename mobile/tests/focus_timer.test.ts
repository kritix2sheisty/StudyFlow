/**
 * tests/focus_timer.test.ts
 * The Focus countdown. Timestamp-based, as the mentor asked: remaining is
 * always endAt minus now, never a counter minus one, so a locked phone,
 * a backgrounded app or a missed tick cannot drift it. Pure values; the
 * clock is a millisecond timestamp passed in.
 */

import { createTimer, pause, remainingMs, reset, resume, start, isFinished } from "../src/focus/timer";

const MIN = 60_000;
const T0 = 1_700_000_000_000;

test("a new timer is idle at its full length", () => {
  const t = createTimer(25 * MIN);
  expect(t.phase).toBe("idle");
  expect(remainingMs(t, T0)).toBe(25 * MIN);
  expect(isFinished(t, T0)).toBe(false);
});

test("start records the end timestamp; remaining is end minus now", () => {
  const t = start(createTimer(25 * MIN), T0);
  expect(t.phase).toBe("running");
  expect(remainingMs(t, T0)).toBe(25 * MIN);
  expect(remainingMs(t, T0 + 10 * MIN)).toBe(15 * MIN);
  expect(remainingMs(t, T0 + 24 * MIN + 59_000)).toBe(1_000);
});

test("a locked phone or a missed tick cannot drift the countdown", () => {
  const t = start(createTimer(25 * MIN), T0);
  // No ticks happen for 20 minutes; the next read is still exact.
  expect(remainingMs(t, T0 + 20 * MIN)).toBe(5 * MIN);
});

test("pause holds the remaining time; time passing while paused changes nothing", () => {
  const running = start(createTimer(25 * MIN), T0);
  const paused = pause(running, T0 + 10 * MIN);
  expect(paused.phase).toBe("paused");
  expect(remainingMs(paused, T0 + 10 * MIN)).toBe(15 * MIN);
  expect(remainingMs(paused, T0 + 60 * MIN)).toBe(15 * MIN);
});

test("resume continues from where pause held it", () => {
  const paused = pause(start(createTimer(25 * MIN), T0), T0 + 10 * MIN);
  const resumed = resume(paused, T0 + 30 * MIN);
  expect(resumed.phase).toBe("running");
  expect(remainingMs(resumed, T0 + 30 * MIN)).toBe(15 * MIN);
  expect(remainingMs(resumed, T0 + 35 * MIN)).toBe(10 * MIN);
});

test("reset returns to idle at the full length from any phase", () => {
  const running = start(createTimer(25 * MIN), T0);
  expect(reset(running)).toEqual(createTimer(25 * MIN));
  const paused = pause(running, T0 + 5 * MIN);
  expect(reset(paused)).toEqual(createTimer(25 * MIN));
});

test("finished at zero, never negative", () => {
  const t = start(createTimer(25 * MIN), T0);
  expect(isFinished(t, T0 + 25 * MIN - 1)).toBe(false);
  expect(isFinished(t, T0 + 25 * MIN)).toBe(true);
  expect(remainingMs(t, T0 + 40 * MIN)).toBe(0);
  expect(isFinished(t, T0 + 40 * MIN)).toBe(true);
});

test("pausing after the end holds zero, and resume stays finished", () => {
  const t = start(createTimer(25 * MIN), T0);
  const late = pause(t, T0 + 30 * MIN);
  expect(remainingMs(late, T0 + 30 * MIN)).toBe(0);
  expect(isFinished(resume(late, T0 + 31 * MIN), T0 + 31 * MIN)).toBe(true);
});

test("start, pause and resume are no-ops in the wrong phase", () => {
  const idle = createTimer(25 * MIN);
  expect(pause(idle, T0)).toBe(idle);
  expect(resume(idle, T0)).toBe(idle);
  const running = start(idle, T0);
  expect(start(running, T0 + MIN)).toBe(running);
  expect(resume(running, T0 + MIN)).toBe(running);
});

test("formatClock shows h:mm:ss past an hour and m:ss below it, as the mentor sketched", () => {
  const { formatClock } = require("../src/focus/timer");
  expect(formatClock(120 * MIN)).toBe("2:00:00");
  expect(formatClock(102 * MIN + 18_000)).toBe("1:42:18");
  expect(formatClock(25 * MIN)).toBe("25:00");
  expect(formatClock(59_000)).toBe("0:59");
  expect(formatClock(0)).toBe("0:00");
  expect(formatClock(1)).toBe("0:01");                                 // a partial second still counts down, never shows 0:00 early
});
