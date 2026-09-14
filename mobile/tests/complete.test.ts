/**
 * tests/complete.test.ts
 * Marking a session complete: one call to the API for the block the
 * student just did, then Today and Progress refresh so the tick, the
 * count and the hours are right everywhere. A refusal (stale plan,
 * unknown block) is rethrown untouched and nothing refreshes.
 */

import { ApiError } from "../src/api/client";
import { completeSession } from "../src/focus/complete";

const BLOCK = { date: "2026-09-13", start: "16:00", end: "18:00" };
const ANSWER = {
  recorded: true, already_recorded: false,
  session: { assignment_id: 1, assignment: "Math", subject: "Mathematics", ...BLOCK, duration_minutes: 120, completed: true },
  assignment: { id: 1, name: "Math", required_hours: 2, done_hours: 2, done_percent: 100 },
};

function deps(focusComplete = jest.fn(async () => ANSWER)) {
  const today = { load: jest.fn(async () => undefined) };
  const progress = { load: jest.fn(async () => undefined) };
  return { api: { focusComplete }, today, progress };
}

test("records the block, then refreshes Today and Progress, and returns the answer", async () => {
  const d = deps();
  const answer = await completeSession(d, BLOCK);
  expect(d.api.focusComplete).toHaveBeenCalledWith(BLOCK);
  expect(d.today.load).toHaveBeenCalledTimes(1);
  expect(d.progress.load).toHaveBeenCalledTimes(1);
  expect(answer).toEqual(ANSWER);
});

test("recording twice is fine and still refreshes", async () => {
  const d = deps(jest.fn(async () => ({ ...ANSWER, already_recorded: true })));
  const answer = await completeSession(d, BLOCK);
  expect(answer.already_recorded).toBe(true);
  expect(d.today.load).toHaveBeenCalledTimes(1);
});

test("a refusal is rethrown untouched and nothing refreshes", async () => {
  const d = deps(jest.fn(async () => { throw new ApiError(409, "Your plan needs to be regenerated before a session can be recorded."); }));
  await expect(completeSession(d, BLOCK)).rejects.toMatchObject({ status: 409 });
  expect(d.today.load).not.toHaveBeenCalled();
  expect(d.progress.load).not.toHaveBeenCalled();
});

test("a failed refresh does not undo the recording", async () => {
  const d = deps();
  d.today.load.mockImplementationOnce(async () => { throw new Error("today down"); });
  await expect(completeSession(d, BLOCK)).resolves.toEqual(ANSWER);
});
