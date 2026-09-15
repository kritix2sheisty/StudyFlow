/**
 * tests/history_store.test.ts
 * The History store: loads /api/focus/history for a number of days,
 * keeps the answer as sent, and follows the same load rules as Today
 * and Progress. The API is a fake.
 */

import { NetworkError } from "../src/api/client";
import { createHistoryStore } from "../src/history/store";
import type { HistoryAnswer } from "../src/history/view";

const EMPTY: HistoryAnswer = {
  days: 7, from: "2026-09-08", to: "2026-09-14", sessions: [], minutes: 0, sessions_count: 0,
  by_day: [], by_subject: [], streak_days: 0,
  today: { minutes: 0, sessions: 0, planned_minutes: 0, planned_sessions: 0 },
};

test("starts loading and load asks for seven days by default", async () => {
  const history = jest.fn(async () => EMPTY);
  const s = createHistoryStore({ api: { history } });
  expect(s.getState()).toEqual({ status: "loading", history: null, message: null });
  await s.load();
  expect(history).toHaveBeenCalledWith(7);
  expect(s.getState()).toEqual({ status: "ready", history: EMPTY, message: null });
});

test("load can ask for a wider window", async () => {
  const history = jest.fn(async () => ({ ...EMPTY, days: 30 }));
  const s = createHistoryStore({ api: { history } });
  await s.load(30);
  expect(history).toHaveBeenCalledWith(30);
  expect(s.getState().history?.days).toBe(30);
});

test("a failed first load is an error; a failed refresh keeps the last answer", async () => {
  const history = jest.fn<Promise<HistoryAnswer>, [number?]>(async () => { throw new NetworkError("down"); });
  const s = createHistoryStore({ api: { history } });
  await s.load();
  expect(s.getState()).toEqual({ status: "error", history: null, message: "down" });
  history.mockImplementationOnce(async () => EMPTY);
  await s.load();
  expect(s.getState().status).toBe("ready");
  history.mockImplementationOnce(async () => { throw new NetworkError("down again"); });
  await s.load();
  expect(s.getState()).toEqual({ status: "ready", history: EMPTY, message: "down again" });
});

test("reset returns to loading", async () => {
  const s = createHistoryStore({ api: { history: jest.fn(async () => EMPTY) } });
  await s.load();
  s.reset();
  expect(s.getState().status).toBe("loading");
});
