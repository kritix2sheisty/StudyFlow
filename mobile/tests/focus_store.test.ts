/**
 * tests/focus_store.test.ts
 * What the Focus screen needs from the server: which session is on now
 * and which comes next, with the API's reasons when there is none. The
 * countdown itself is not here (see focus_timer). The API is a fake.
 */

import { NetworkError } from "../src/api/client";
import { createFocusStore } from "../src/focus/store";

const MATH = { assignment_id: 1, assignment: "Math", subject: "Mathematics", date: "2026-09-13",
  start: "16:00", end: "18:00", duration_minutes: 120, completed: false };
const CS = { ...MATH, assignment_id: 2, assignment: "CS", subject: "Computer Science", start: "19:00", end: "20:00", duration_minutes: 60 };

function store(current: jest.Mock, next: jest.Mock) {
  return createFocusStore({ api: { focusCurrent: current, focusNext: next } });
}

test("starts loading with nothing known", () => {
  const s = store(jest.fn(), jest.fn());
  expect(s.getState()).toEqual({ status: "loading", current: null, currentReason: null, next: null, nextReason: null, message: null });
});

test("load reads the current and the next session together", async () => {
  const s = store(
    jest.fn(async () => ({ active: true, session: { ...MATH, remaining_minutes: 73 }, reason: null })),
    jest.fn(async () => ({ session: CS, reason: null })),
  );
  await s.load();
  const st = s.getState();
  expect(st.status).toBe("ready");
  expect(st.current).toMatchObject({ assignment: "Math", remaining_minutes: 73 });
  expect(st.next).toMatchObject({ assignment: "CS" });
  expect(st.currentReason).toBeNull();
  expect(st.nextReason).toBeNull();
});

test("nothing on now and nothing next carry the API's reasons", async () => {
  const s = store(
    jest.fn(async () => ({ active: false, session: null, reason: "nothing_now" })),
    jest.fn(async () => ({ session: null, reason: "nothing_next" })),
  );
  await s.load();
  expect(s.getState()).toMatchObject({ status: "ready", current: null, currentReason: "nothing_now", next: null, nextReason: "nothing_next" });
});

test("a stale plan is reported on both", async () => {
  const s = store(
    jest.fn(async () => ({ active: false, session: null, reason: "plan_stale" })),
    jest.fn(async () => ({ session: null, reason: "plan_stale" })),
  );
  await s.load();
  expect(s.getState().currentReason).toBe("plan_stale");
  expect(s.getState().nextReason).toBe("plan_stale");
});

test("a failed load keeps what was known and reports the message", async () => {
  const current = jest.fn(async () => ({ active: true, session: MATH, reason: null }));
  const next = jest.fn(async () => ({ session: CS, reason: null }));
  const s = store(current, next);
  await s.load();
  current.mockImplementationOnce(async () => { throw new NetworkError("Can't reach StudyFlow at http://x:8010."); });
  await s.load();
  expect(s.getState().status).toBe("ready");
  expect(s.getState().current).toMatchObject({ assignment: "Math" });
  expect(s.getState().message).toBe("Can't reach StudyFlow at http://x:8010.");
});

test("a failed first load is an error", async () => {
  const s = store(jest.fn(async () => { throw new NetworkError("down"); }), jest.fn(async () => ({ session: null, reason: "nothing_next" })));
  await s.load();
  expect(s.getState()).toMatchObject({ status: "error", current: null, message: "down" });
});

test("reset returns to loading", async () => {
  const s = store(jest.fn(async () => ({ active: false, session: null, reason: "no_plan" })), jest.fn(async () => ({ session: null, reason: "no_plan" })));
  await s.load();
  s.reset();
  expect(s.getState().status).toBe("loading");
});
