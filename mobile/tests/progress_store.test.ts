/**
 * tests/progress_store.test.ts
 * The Progress screen's store: one load of /api/plan/progress, kept as
 * the server sent it, with the same loading/error/refresh rules as
 * Today. The API is a fake.
 */

import { NetworkError } from "../src/api/client";
import { createProgressStore, ProgressAnswer } from "../src/progress/store";

const PROGRESS: ProgressAnswer = {
  fresh: true, required_hours: 3, scheduled_hours: 3, unscheduled_hours: 0, completion_percentage: 100,
  assignments: [
    { id: 1, name: "Math", subject: "Mathematics", due_date: "2026-09-16", status: "SCHEDULED", required_hours: 2,
      scheduled_hours: 2, remaining_hours: 0, percent: 100, risk: "LOW", done_hours: 2, done_percent: 100 },
    { id: 2, name: "CS", subject: "Computer Science", due_date: "2026-09-17", status: "SCHEDULED", required_hours: 1,
      scheduled_hours: 1, remaining_hours: 0, percent: 100, risk: "LOW", done_hours: 0, done_percent: 0 },
  ],
  completed: ["Old lab"], active_count: 2, completed_count: 1, done_hours: 2, sessions_completed: 1,
};

test("starts loading", () => {
  const s = createProgressStore({ api: { progress: jest.fn(async () => PROGRESS) } });
  expect(s.getState()).toEqual({ status: "loading", progress: null, message: null });
});

test("load keeps the answer as sent", async () => {
  const s = createProgressStore({ api: { progress: jest.fn(async () => PROGRESS) } });
  await s.load();
  expect(s.getState()).toEqual({ status: "ready", progress: PROGRESS, message: null });
});

test("a failed first load is an error; a failed refresh keeps the last answer", async () => {
  const progress = jest.fn<Promise<ProgressAnswer>, []>(async () => { throw new NetworkError("down"); });
  const s = createProgressStore({ api: { progress } });
  await s.load();
  expect(s.getState()).toEqual({ status: "error", progress: null, message: "down" });
  progress.mockImplementationOnce(async () => PROGRESS);
  await s.load();
  expect(s.getState().status).toBe("ready");
  progress.mockImplementationOnce(async () => { throw new NetworkError("down again"); });
  await s.load();
  expect(s.getState()).toEqual({ status: "ready", progress: PROGRESS, message: "down again" });
});

test("reset returns to loading", async () => {
  const s = createProgressStore({ api: { progress: jest.fn(async () => PROGRESS) } });
  await s.load();
  s.reset();
  expect(s.getState().status).toBe("loading");
});
