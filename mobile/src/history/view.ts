/**
 * src/history/view.ts
 * What History and Progress show, computed from /api/focus/history.
 * Pure: the API answer in, display values out. The server already did
 * the counting (per day, per subject, streak, today's plan); this file
 * only formats and groups, and writes the two motivation sentences.
 */

export interface HistorySession {
  id: number;
  assignment_id: number | null;
  assignment: string;
  subject: string;
  date: string;
  start: string;
  end: string;
  minutes: number;
  completed_at: string;
}

export interface HistoryToday {
  minutes: number;
  sessions: number;
  planned_minutes: number;
  planned_sessions: number;
}

export interface HistoryAnswer {
  days: number;
  from: string;
  to: string;
  sessions: HistorySession[];
  minutes: number;
  sessions_count: number;
  by_day: { date: string; minutes: number; sessions: number }[];
  by_subject: { subject: string; minutes: number; sessions: number }[];
  streak_days: number;
  today: HistoryToday;
}

export interface DayGroup {
  date: string;
  label: string;
  minutes: number;
  sessions: HistorySession[];
}

export interface WeekSummary {
  minutes: number;
  sessions: number;
  streak: number;
  subjects: number;
  activeDays: number;
  daysInWindow: number;
  today: { done: number; planned: number; sessionsDone: number; sessionsPlanned: number; percent: number };
}

/** "45 min", "1h", "2h 15m": the way a student says it. */
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function dayLabel(iso: string, today: string): string {
  if (iso === today) return "Today";
  const yesterday = parseIso(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (iso === isoDate(yesterday)) return "Yesterday";
  return parseIso(iso).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
}

/** Sessions grouped by day, newest day first; the API already orders sessions newest first. */
export function groupByDay(sessions: HistorySession[], today: string): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const s of sessions) {
    const last = groups[groups.length - 1];
    if (last && last.date === s.date) {
      last.sessions.push(s);
      last.minutes += s.minutes;
    } else {
      groups.push({ date: s.date, label: dayLabel(s.date, today), minutes: s.minutes, sessions: [s] });
    }
  }
  return groups;
}

export function weekSummary(h: HistoryAnswer): WeekSummary {
  const t = h.today;
  const percent = t.planned_minutes > 0 ? Math.min(100, Math.round((100 * t.minutes) / t.planned_minutes)) : 0;
  return {
    minutes: h.minutes,
    sessions: h.sessions_count,
    streak: h.streak_days,
    subjects: h.by_subject.length,
    activeDays: h.by_day.filter((d) => d.sessions > 0).length,
    daysInWindow: h.days,
    today: { done: t.minutes, planned: t.planned_minutes, sessionsDone: t.sessions, sessionsPlanned: t.planned_sessions, percent },
  };
}

/** The mentor's two sentences, or nothing before the first session of the day. */
export function todayLines(t: HistoryToday): string[] {
  if (t.sessions === 0) return [];
  const many = t.sessions > 1;
  const first = `${t.sessions} session${many ? "s" : ""} completed today${many ? " 🎉" : ""}`;
  if (t.planned_minutes === 0) return [first, `You completed ${formatMinutes(t.minutes)} of study.`];
  if (t.minutes >= t.planned_minutes) {
    return [first, `You completed all ${formatMinutes(t.planned_minutes)} of planned study. Done for today.`];
  }
  return [first, `You completed ${formatMinutes(t.minutes)} of planned study.`];
}
