/**
 * src/focus/timer.ts
 * The Focus countdown as a value. Timestamp-based: a running timer knows
 * when it ends, and remaining is always endAt minus now. Nothing here
 * counts ticks, so a locked phone, a backgrounded app or a skipped
 * interval cannot drift it; the screen only re-renders and reads.
 *
 *   idle      full length, not started
 *   running   endAt is set
 *   paused    heldMs is what was left when paused
 *
 * Every function returns a new value; the wrong-phase ones return the
 * same value untouched.
 */

export type TimerPhase = "idle" | "running" | "paused";

export interface Timer {
  phase: TimerPhase;
  durationMs: number;
  endAt: number | null;
  heldMs: number | null;
}

export function createTimer(durationMs: number): Timer {
  return { phase: "idle", durationMs, endAt: null, heldMs: null };
}

export function start(t: Timer, now: number): Timer {
  if (t.phase !== "idle") return t;
  return { ...t, phase: "running", endAt: now + t.durationMs, heldMs: null };
}

export function pause(t: Timer, now: number): Timer {
  if (t.phase !== "running") return t;
  return { ...t, phase: "paused", endAt: null, heldMs: remainingMs(t, now) };
}

export function resume(t: Timer, now: number): Timer {
  if (t.phase !== "paused") return t;
  return { ...t, phase: "running", endAt: now + (t.heldMs ?? 0), heldMs: null };
}

export function reset(t: Timer): Timer {
  return createTimer(t.durationMs);
}

export function remainingMs(t: Timer, now: number): number {
  switch (t.phase) {
    case "idle":
      return t.durationMs;
    case "paused":
      return Math.max(0, t.heldMs ?? 0);
    case "running":
      return Math.max(0, (t.endAt ?? now) - now);
  }
}

export function isFinished(t: Timer, now: number): boolean {
  return t.phase !== "idle" && remainingMs(t, now) === 0;
}

/** "mm:ss" for the clock face; hours fold into minutes (125:00 is fine). */
export function formatClock(ms: number): string {
  const total = Math.ceil(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}
