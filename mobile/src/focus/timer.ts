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

/** How far through the session, 0 to 100, from the same clock reads as remaining. */
export function progressPercent(t: Timer, now: number): number {
  if (t.durationMs <= 0) return 0;
  const elapsed = t.durationMs - remainingMs(t, now);
  return Math.min(100, Math.max(0, Math.round((100 * elapsed) / t.durationMs)));
}

/** The clock face: "1:42:18" past an hour, "25:00" below it; a partial second still shows. */
export function formatClock(ms: number): string {
  const total = Math.ceil(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = m.toString().padStart(2, "0");
  const ss = s.toString().padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}
