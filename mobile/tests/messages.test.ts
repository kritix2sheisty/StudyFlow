/**
 * tests/messages.test.ts
 * What a screen shows when something fails: the API's own words when it
 * gave any, the unreachable-server message, and one generic line for
 * anything else.
 */

import { ApiError, NetworkError } from "../src/api/client";
import { errorMessage, GENERIC_ERROR } from "../src/ui/messages";

test("an ApiError is shown verbatim", () => {
  expect(errorMessage(new ApiError(401, "Email or password is incorrect."))).toBe("Email or password is incorrect.");
});

test("a NetworkError is shown verbatim", () => {
  expect(errorMessage(new NetworkError("Can't reach StudyFlow at http://x:8010."))).toBe("Can't reach StudyFlow at http://x:8010.");
});

test("anything else becomes the generic line", () => {
  expect(errorMessage(new TypeError("boom"))).toBe(GENERIC_ERROR);
  expect(errorMessage("nonsense")).toBe(GENERIC_ERROR);
  expect(errorMessage(undefined)).toBe(GENERIC_ERROR);
});
