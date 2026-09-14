/**
 * tests/today_store.test.ts
 * The Today screen's store: loads /api/focus/today, keeps the last good
 * view while refreshing, and shows the API's or the network's message
 * when a load fails. The API and the clock are fakes.
 */

import { ApiError, NetworkError } from "../src/api/client";
import { createTodayStore, TodayState } from "../src/today/store";
import type { TodayAnswer } from "../src/today/view";

const MATH = { assignment_id: 1, assignment: "Math", subject: "Mathematics", date: "2026-09-13",
  start: "16:00", end: "18:00", duration_minutes: 120, completed: false };

const answer = (sessions = [MATH], reason: TodayAnswer["reason"] = null): TodayAnswer =>
  ({ date: "2026-09-13", sessions, reason });

function store(focusToday: jest.Mock, minute = 17 * 60) {
  return createTodayStore({ api: { focusToday }, nowMinute: () => minute });
}

test("starts loading with no view", () => {
  const s = store(jest.fn(async () => answer()));
  expect(s.getState()).toEqual({ status: "loading", view: null, message: null });
});

test("load builds the view against the clock", async () => {
  const s = store(jest.fn(async () => answer()));
  await s.load();
  const state = s.getState();
  expect(state.status).toBe("ready");
  expect(state.view?.kind).toBe("sessions");
  expect(state.view?.rows[0].state).toBe("now");
  expect(state.message).toBeNull();
});

test("a failed first load is an error with the message", async () => {
  const s = store(jest.fn(async () => { throw new NetworkError("Can't reach StudyFlow at http://x:8010."); }));
  await s.load();
  expect(s.getState()).toEqual({ status: "error", view: null, message: "Can't reach StudyFlow at http://x:8010." });
});

test("a failed refresh keeps the last good view and reports the message", async () => {
  const focusToday = jest.fn(async () => answer());
  const s = store(focusToday);
  await s.load();
  focusToday.mockImplementationOnce(async () => { throw new ApiError(500, "The server answered 500."); });
  await s.load();
  const state = s.getState();
  expect(state.status).toBe("ready");
  expect(state.view?.rows).toHaveLength(1);
  expect(state.message).toBe("The server answered 500.");
});

test("a refresh replaces the view and clears an old message", async () => {
  const focusToday = jest.fn<Promise<TodayAnswer>, []>(async () => { throw new NetworkError("down"); });
  const s = store(focusToday);
  await s.load();
  focusToday.mockImplementation(async () => answer([{ ...MATH, completed: true }]));
  await s.load();
  expect(s.getState().message).toBeNull();
  expect(s.getState().view?.rows[0].state).toBe("done");
  expect(s.getState().view?.done).toBe(1);
});

test("load reports refreshing while a refresh is in flight, then ready", async () => {
  let release!: (a: TodayAnswer) => void;
  const focusToday = jest.fn(async () => answer());
  const s = store(focusToday);
  await s.load();
  focusToday.mockImplementationOnce(() => new Promise<TodayAnswer>((res) => { release = res; }));
  const seen: TodayState["status"][] = [];
  s.subscribe((st) => seen.push(st.status));
  const pending = s.load();
  expect(s.getState().status).toBe("refreshing");
  release(answer());
  await pending;
  expect(seen).toEqual(["refreshing", "ready"]);
});

test("reset returns to loading so a new sign-in starts clean", async () => {
  const s = store(jest.fn(async () => answer()));
  await s.load();
  s.reset();
  expect(s.getState()).toEqual({ status: "loading", view: null, message: null });
});
