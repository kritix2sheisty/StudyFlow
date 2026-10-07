/**
 * tests/today_store.test.ts
 * The Today screen's store: loads /api/focus/today, keeps the last good
 * view while refreshing, generates a plan then reloads, and shows the
 * API's or the network's message when a load or generate fails. The API
 * and the clock are fakes.
 */

import { ApiError, NetworkError } from "../src/api/client";
import { createTodayStore, TodayState } from "../src/today/store";
import type { TodayAnswer } from "../src/today/view";

const MATH = { assignment_id: 1, assignment: "Math", subject: "Mathematics", date: "2026-09-13",
  start: "16:00", end: "18:00", duration_minutes: 120, completed: false };

const answer = (sessions = [MATH], reason: TodayAnswer["reason"] = null): TodayAnswer =>
  ({ date: "2026-09-13", sessions, reason });

function store(focusToday: jest.Mock, minute = 17 * 60, generatePlan: jest.Mock = jest.fn(async () => ({}))) {
  return createTodayStore({ api: { focusToday, generatePlan }, nowMinute: () => minute });
}

test("starts loading with no view", () => {
  const s = store(jest.fn(async () => answer()));
  expect(s.getState()).toEqual({ status: "loading", generating: false, view: null, message: null });
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
  expect(s.getState()).toEqual({ status: "error", generating: false, view: null, message: "Can't reach StudyFlow at http://x:8010." });
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
  expect(s.getState()).toEqual({ status: "loading", generating: false, view: null, message: null });
});

test("generate posts a plan then reloads today", async () => {
  const generatePlan = jest.fn(async () => ({ fresh: true }));
  const focusToday = jest.fn(async () => answer());
  const s = store(focusToday, 17 * 60, generatePlan);
  await s.generate();
  expect(generatePlan).toHaveBeenCalledTimes(1);
  expect(focusToday).toHaveBeenCalledTimes(1);
  expect(s.getState().status).toBe("ready");
  expect(s.getState().generating).toBe(false);
  expect(s.getState().view?.kind).toBe("sessions");
  expect(s.getState().message).toBeNull();
});

test("a refused generate keeps no view and shows the API's message", async () => {
  const generatePlan = jest.fn(async () => { throw new ApiError(400, "Add some assignments before generating your study plan."); });
  const focusToday = jest.fn(async () => answer());
  const s = store(focusToday, 17 * 60, generatePlan);
  await s.generate();
  expect(focusToday).not.toHaveBeenCalled();
  expect(s.getState()).toMatchObject({
    status: "error", generating: false, view: null,
    message: "Add some assignments before generating your study plan.",
  });
});

test("a refused generate after a loaded day keeps the last view", async () => {
  const generatePlan = jest.fn(async () => { throw new ApiError(400, "Add your available study times before generating a study plan."); });
  const s = store(jest.fn(async () => answer()), 17 * 60, generatePlan);
  await s.load();
  await s.generate();
  expect(s.getState().view?.kind).toBe("sessions");
  expect(s.getState().message).toBe("Add your available study times before generating a study plan.");
  expect(s.getState().generating).toBe(false);
});

test("generate reports generating while the call is in flight", async () => {
  let release!: () => void;
  const generatePlan = jest.fn(() => new Promise<unknown>((res) => { release = () => res({}); }));
  const s = store(jest.fn(async () => answer()), 17 * 60, generatePlan);
  const seen: boolean[] = [];
  s.subscribe((st) => seen.push(st.generating));
  const pending = s.generate();
  expect(s.getState().generating).toBe(true);
  release();
  await pending;
  expect(s.getState().generating).toBe(false);
  expect(seen[0]).toBe(true);
  expect(seen[seen.length - 1]).toBe(false);
});

test("a second generate while one is in flight is ignored", async () => {
  let release!: () => void;
  const generatePlan = jest.fn(() => new Promise<unknown>((res) => { release = () => res({}); }));
  const s = store(jest.fn(async () => answer()), 17 * 60, generatePlan);
  const first = s.generate();
  const second = s.generate();
  release();
  await Promise.all([first, second]);
  expect(generatePlan).toHaveBeenCalledTimes(1);
});
