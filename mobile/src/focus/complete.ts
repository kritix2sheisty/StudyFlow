/**
 * src/focus/complete.ts
 * Marking a session complete. One call to POST /api/focus/complete for
 * the block the student just did (a session record, never the whole
 * assignment), then Today, Progress and History refresh so the tick,
 * the count and the hours agree everywhere. A refusal from the API (stale plan,
 * unknown block) is rethrown untouched so the screen shows its words;
 * a failed refresh is swallowed, the recording already happened.
 */

import type { TodaySession } from "../today/view";

export interface Block {
  date: string;
  start: string;
  end: string;
}

export interface CompleteAnswer {
  recorded: boolean;
  already_recorded: boolean;
  session: TodaySession;
  assignment: { id: number | null; name: string; required_hours: number; done_hours: number; done_percent: number };
}

export interface CompleteDeps {
  api: { focusComplete(block: Block): Promise<CompleteAnswer> };
  today: { load(): Promise<void> };
  progress: { load(): Promise<void> };
  history: { load(): Promise<void> };
}

export async function completeSession(deps: CompleteDeps, block: Block): Promise<CompleteAnswer> {
  const answer = await deps.api.focusComplete(block);
  await Promise.allSettled([deps.today.load(), deps.progress.load(), deps.history.load()]);
  return answer;
}
