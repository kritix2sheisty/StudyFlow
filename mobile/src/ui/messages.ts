/**
 * src/ui/messages.ts
 * What a screen shows when a call fails. The API's messages are already
 * written for students ("Email or password is incorrect."), so they are
 * shown as they are; so is the unreachable-server message, which names
 * the address. Anything else gets one generic line.
 */

import { ApiError, NetworkError } from "../api/client";

export const GENERIC_ERROR = "Something went wrong. Please try again.";

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError || e instanceof NetworkError) return e.message;
  return GENERIC_ERROR;
}
